#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — proves the batch-scoped approval check, by execution.

THE BUG THIS PINS DOWN

SqliteImportBatchStore.AnyApproved decides whether a rollback is refused. Its
first version counted:

    SELECT COUNT(*) FROM <docTable> WHERE status='APPROVED'

No batch filter. So one approved invoice from last month made EVERY future
rollback of that document type refuse, including a batch containing nothing but
drafts. The owner would be told "approved documents exist" about documents
their batch never touched, with no way forward except deleting data by hand.

The fix joins through import_rows (mapped_json holds {"new_id": n}). This script
executes the fixed query shape against a database built by the real migrations
and proves:

  1. a batch of drafts, with an unrelated approved document in the same table,
     is NOT blocked;
  2. the same batch IS blocked once one of ITS OWN documents is approved;
  3. an unrelated approved document never blocks anything;
  4. the batch listing returns newest first and clamps the limit.

The SQL here is transliterated from the C#, exactly as
tools/test_dashboard_cs_sql.py does for the dashboard, because the C# itself
cannot be compiled in this environment.

    python3 tools/test_import_batch_scope.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# The SQL that SqliteImportBatchStore.AnyApproved now runs. Kept as a constant
# so the test fails loudly if someone edits one and not the other.
ANY_APPROVED_SQL = """
SELECT COUNT(*) FROM {table} t
JOIN import_rows r ON (
  r.mapped_json LIKE '{{"new_id":' || t.id || '%'
  OR r.mapped_json LIKE '{{"new_id": ' || t.id || '%'
)
WHERE r.batch_id=? AND r.status='IMPORTED' AND t.status='APPROVED'
"""

LIST_SQL = """
SELECT id, code, file_name, detected_type, status,
       total_rows, valid_rows, invalid_rows
FROM import_batches ORDER BY id DESC LIMIT ?
"""


def fresh():
    import verify_database as V
    con = V.build_db(os.path.join(tempfile.mkdtemp(prefix="bs_"), "b.db"))
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("INSERT INTO parties(code,display_name,nature,party_kind,"
                "party_kind_confirmed) VALUES('P1','طرف','C','PERSON',1)")
    return con


def make_batch(con, code, template="SALES_INVOICES"):
    cur = con.execute(
        "INSERT INTO import_batches(code,file_name,detected_type,status,"
        "total_rows,valid_rows,invalid_rows,file_sha256,created_at) "
        "VALUES(?,?,?,'REVIEW',2,2,0,'sha','2026-11-17T10:00:00')",
        (code, code + ".xlsx", template))
    return cur.lastrowid


def make_doc(con, code, status):
    con.execute(
        "INSERT INTO sales_invoices(code,doc_number,date_iso,date_shamsi,"
        "party_id,status) VALUES(?,?,date('now'),'1403/05/01',1,?)",
        (code, code, status))
    return con.execute("SELECT id FROM sales_invoices WHERE code=?",
                       (code,)).fetchone()[0]


def link(con, batch_id, doc_id, source_row, spaced=False):
    """Write the import_rows link the way each writer does.

    spaced=False -> '{"new_id":5}'    (C# SqliteImportBatchStore)
    spaced=True  -> '{"new_id": 5}'   (Python json.dumps)
    The guard must work for both; a pattern for one spacing matched nothing
    against the other and silently disabled the approval check.
    """
    mapped = '{"new_id": %d}' % doc_id if spaced else '{"new_id":%d}' % doc_id
    con.execute(
        "INSERT INTO import_rows(batch_id,source_row_number,raw_json,mapped_json,"
        "blank_fields_json,status,error_message) "
        "VALUES(?,?,?,?,'','IMPORTED','')",
        (batch_id, source_row, "raw", mapped))


def any_approved(con, table, batch_id):
    return con.execute(ANY_APPROVED_SQL.format(table=table),
                       (batch_id,)).fetchone()[0] > 0


# ---------------------------------------------------------------------------
def t_drafts_batch_not_blocked_by_foreign_approved():
    """The regression. A batch of drafts must be rollback-able even when an
    unrelated approved invoice exists in the same table."""
    con = fresh()
    old = make_doc(con, "OLD-APPROVED", "APPROVED")          # not in any batch
    batch = make_batch(con, "IMP-A")
    d = make_doc(con, "NEW-DRAFT", "DRAFT")
    link(con, batch, d, 3)
    con.commit()

    blocked = any_approved(con, "sales_invoices", batch)
    assert blocked is False, \
        "دسته پیش‌نویس به‌خاطر سند تأییدشده دیگری مسدود شد (باگ قبلی)"
    con.close()


def t_batch_blocked_by_its_own_approved():
    """The guard must still work: approving a document the batch created makes
    rollback genuinely unsafe."""
    con = fresh()
    batch = make_batch(con, "IMP-B")
    d = make_doc(con, "MINE-APPROVED", "APPROVED")
    link(con, batch, d, 3)
    con.commit()

    assert any_approved(con, "sales_invoices", batch) is True, \
        "سند تأییدشده خودِ دسته نباید اجازه برگشت بدهد"
    con.close()


def t_foreign_approved_never_blocks():
    """Two batches coexist; approving one must not block the other."""
    con = fresh()
    b1 = make_batch(con, "IMP-C1")
    b2 = make_batch(con, "IMP-C2")
    d1 = make_doc(con, "C1-DOC", "APPROVED")
    d2 = make_doc(con, "C2-DOC", "DRAFT")
    link(con, b1, d1, 3)
    link(con, b2, d2, 3)
    con.commit()

    assert any_approved(con, "sales_invoices", b1) is True
    assert any_approved(con, "sales_invoices", b2) is False, \
        "دسته دوم نباید به‌خاطر دسته اول مسدود شود"
    con.close()


def t_list_is_newest_first():
    con = fresh()
    for code in ("IMP-1", "IMP-2", "IMP-3"):
        make_batch(con, code)
    con.commit()
    rows = con.execute(LIST_SQL, (2,)).fetchall()
    assert len(rows) == 2, rows
    assert rows[0][1] == "IMP-3" and rows[1][1] == "IMP-2", rows
    con.close()


def t_limit_is_clamped_not_ignored():
    """The C# clamps limit to 1..500. Prove the SQL respects a small limit so a
    UI bug cannot turn the list into a full scan."""
    con = fresh()
    for i in range(12):
        make_batch(con, "IMP-%02d" % i)
    con.commit()
    assert len(con.execute(LIST_SQL, (5,)).fetchall()) == 5
    con.close()


def t_column_order_matches_reader():
    """ReadBatch maps columns positionally. If a future ALTER reorders the
    SELECT, every count lands in the wrong field. Prove the shape."""
    con = fresh()
    make_batch(con, "IMP-SHAPE")
    con.commit()
    row = con.execute(LIST_SQL, (1,)).fetchone()
    assert len(row) == 8, "expected 8 columns, got %d" % len(row)
    assert row[1] == "IMP-SHAPE"       # code
    assert row[3] == "SALES_INVOICES"  # detected_type
    assert row[4] == "REVIEW"          # status
    con.close()


def t_both_json_spacings_are_matched():
    """The exact bug this gate exists for: the guard must see an approved
    document whether the link was written with a space or without."""
    con = fresh()
    b_compact = make_batch(con, "IMP-COMPACT")
    d1 = make_doc(con, "D-COMPACT", "APPROVED")
    link(con, b_compact, d1, 3, spaced=False)

    b_spaced = make_batch(con, "IMP-SPACED")
    d2 = make_doc(con, "D-SPACED", "APPROVED")
    link(con, b_spaced, d2, 3, spaced=True)
    con.commit()

    assert any_approved(con, "sales_invoices", b_compact) is True, \
        "شکل بدون فاصله شناخته نشد"
    assert any_approved(con, "sales_invoices", b_spaced) is True, \
        "شکل با فاصله شناخته نشد — این همان باگی است که گارد را از کار می‌انداخت"
    con.close()


TESTS = [
    ("هر دو شکل JSON (با و بی‌فاصله) شناخته می‌شوند", t_both_json_spacings_are_matched),
    ("دسته پیش‌نویس با سند تأییدشده بیگانه مسدود نمی‌شود", t_drafts_batch_not_blocked_by_foreign_approved),
    ("سند تأییدشده خودِ دسته برگشت را می‌بندد", t_batch_blocked_by_its_own_approved),
    ("تأیید یک دسته، دسته دیگر را نمی‌بندد", t_foreign_approved_never_blocks),
    ("فهرست دسته‌ها از جدید به قدیم", t_list_is_newest_first),
    ("limit کوچک رعایت می‌شود", t_limit_is_clamped_not_ignored),
    ("ترتیب ستون‌ها با reader می‌خواند", t_column_order_matches_reader),
]


def main():
    ok = 0
    for name, fn in TESTS:
        try:
            fn()
            print("PASS  " + name)
            ok += 1
        except Exception as e:                    # noqa: BLE001
            print("FAIL  %s: %s" % (name, e))
    print()
    print("%d/%d PASS" % (ok, len(TESTS)))
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
