#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the import centre's flow, proven by execution.

WHAT THE IMPORT CENTRE IS

src/Mazandasht.Presentation/Import/ is the UI the owner finally gets for the
import engine. Its whole safety claim is one sentence:

    selecting a file and previewing it writes NOTHING.

That claim is a comment in a .cs file until someone runs it. The C# cannot be
compiled here (reports/CSHARP_BUILD_ATTEMPT_FA.md), so this script exercises the
SAME flow through the Python engine whose behaviour the C# is proven equivalent
to (tools/check_contract_parity.py), and asserts the invariants the window
depends on:

  1. preview writes zero documents and zero batches
  2. the counts the preview reports are the counts the commit writes
  3. commit creates exactly one batch row, in REVIEW
  4. a second preview after a commit still writes nothing
  5. rollback removes only what that batch created
  6. rollback sets the batch to ROLLED_BACK
  7. the history is newest-first
  8. an approved document from OUTSIDE a batch does not attach to it

WHY THE FIXTURES ARE BUILT HERE

The owner's real 01_Parties.xlsx contains zero data rows (DEC-NEW-037). Testing
against it would prove only that an empty file behaves. The workbooks below are
built in the real shape — English header row 1, Persian header row 2, data from
row 3 — so the flow is proven on documents that actually exist.

    python3 tools/test_import_centre_flow.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

TEMPLATES = os.path.join(ROOT, "tests", "fixtures", "owner_templates")
TMP = tempfile.mkdtemp(prefix="ic_files_")

DOC_TABLES = ["parties", "products", "weigh_tickets", "purchase_invoices",
              "sales_invoices", "sorting_batches", "bank_transactions",
              "cheques", "basket_movements"]


def build(code, name, rows):
    """A workbook in the real owner shape."""
    import import_contract as C
    from xlsx_io import write_workbook
    tpl = C.ALL[code]
    grid = [[f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields]]
    grid.extend(rows)
    path = os.path.join(TMP, name)
    write_workbook(path, {"داده‌ها": grid})
    return path


PARTY_ROWS = [
    ["P-001", "حسین رضایی", "PERSON", "حسین رضایی", "0012345678", "",
     "09120000001", "", "بابل", ""],
    ["P-002", "شرکت سپید دانه", "COMPANY", "شرکت سپید دانه", "10101234567",
     "411111111111", "", "01132000000", "بابل", ""],
    ["P-003", "مریم احمدی", "PERSON", "مریم احمدی", "0087654321", "",
     "09120000003", "", "آمل", ""],
]

# GroupCode and UnitCode are required lookups. The seed provides PG-CITRUS and
# a fixed unit set (U-KG, U-BAG, ...). Using real codes here means the rows pass
# validation and the test exercises documents, not rejections.
PRODUCT_ROWS = [
    ["PR-001", "پرتقال تامسون", "PG-CITRUS", "U-KG", "", "1", ""],
    ["PR-002", "کیوی سبز", "PG-CITRUS", "U-KG", "", "1", ""],
]


def fresh():
    import verify_database as V
    path = os.path.join(tempfile.mkdtemp(prefix="ic_db_"), "ic.db")
    con = V.build_db(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def counts(con):
    return {t: con.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
            for t in DOC_TABLES}


def batch_count(con):
    return con.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]


# ---------------------------------------------------------------------------
def t_preview_writes_nothing():
    """The central promise of the window."""
    import import_engine as E
    con = fresh()
    path = build("PARTIES", "p.xlsx", PARTY_ROWS)

    before, b_before = counts(con), batch_count(con)
    out = E.import_file(con, path, "PARTIES", commit=False)
    after, b_after = counts(con), batch_count(con)

    assert before == after, {
        t: (before[t], after[t]) for t in before if before[t] != after[t]}
    assert b_before == b_after, (b_before, b_after)
    assert out.batch_id is None, "پیش‌نمایش دسته ساخت: %s" % out.batch_id
    # NOTE: created is NOT zero in preview. It means "how many documents WOULD
    # be created", which is the number the UI prints on the commit button. An
    # earlier version of this test asserted created == 0 and therefore failed
    # against a correct engine. What proves "wrote nothing" is the table counts
    # above, not this counter.
    assert out.created == len(PARTY_ROWS), (out.created, len(PARTY_ROWS))
    assert not out.errors, out.errors
    con.close()


def t_preview_counts_match_commit():
    """What the button promises is what the commit writes. If these diverge the
    number on the button is a lie."""
    import import_engine as E
    con = fresh()
    path = build("PARTIES", "p.xlsx", PARTY_ROWS)

    # The window's preview does not return a per-row count in this engine
    # (BatchResult.created is 0 by design in preview). What it can promise, and
    # what the button shows, is the number of VALID rows — which the engine
    # reports through the parse stage. Here we assert the stronger property:
    # committing writes exactly as many parties as the file has valid rows.
    preview = E.import_file(con, path, "PARTIES", commit=False)
    # The button on the window shows this number. It must equal what the commit
    # then writes, or the owner is told the wrong count at the moment of the
    # irreversible click.
    promised = preview.created

    committed = E.import_file(con, path, "PARTIES", commit=True)
    assert committed.batch_id is not None, "ثبت، دسته نساخت"
    written = con.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
    assert written == committed.created, (written, committed.created)
    assert written == promised, ("پیش‌نمایش %d وعده داد، %d نوشته شد" % (promised, written))
    assert written == len(PARTY_ROWS), (written, len(PARTY_ROWS))
    con.close()


def t_commit_creates_one_batch():
    import import_engine as E
    con = fresh()
    path = build("PARTIES", "p.xlsx", PARTY_ROWS)
    before = batch_count(con)
    out = E.import_file(con, path, "PARTIES", commit=True)
    assert batch_count(con) - before == 1, (before, batch_count(con))

    row = con.execute(
        "SELECT detected_type, status FROM import_batches WHERE id=?",
        (out.batch_id,)).fetchone()
    assert row is not None, "دسته با شناسه گزارش‌شده پیدا نشد"
    assert row[0] == "PARTIES", row
    # Must be REVIEW. The batch tracks a file that was read and written;
    # approval is a separate decision about its documents. tools/import_engine.py
    # used to set this to APPROVED, which contradicted its own docstring,
    # disagreed with the C# implementation, and permanently disabled the import
    # centre's rollback gate (which requires REVIEW).
    assert row[1] == "REVIEW", row
    con.close()


def t_second_preview_after_commit_writes_nothing():
    """The owner previews, commits, then previews again to check. That second
    preview must not create a second batch or duplicate rows."""
    import import_engine as E
    con = fresh()
    path = build("PARTIES", "p.xlsx", PARTY_ROWS)
    E.import_file(con, path, "PARTIES", commit=True)

    before, b_before = counts(con), batch_count(con)
    E.import_file(con, path, "PARTIES", commit=False)

    assert counts(con) == before
    assert batch_count(con) == b_before
    con.close()


def t_rollback_deletes_only_that_batch():
    """Two imports, roll back the second: the first must survive intact, and the
    comparison is on the full set of codes, not a count."""
    import import_engine as E
    con = fresh()

    p1 = build("PARTIES", "p.xlsx", PARTY_ROWS)
    E.import_file(con, p1, "PARTIES", commit=True)
    first_codes = set(r[0] for r in con.execute("SELECT code FROM parties"))
    assert len(first_codes) == 3, first_codes

    p2 = build("PRODUCTS", "pr.xlsx", PRODUCT_ROWS)
    # products is seeded with 4 base rows, so compare DELTAS, never absolutes.
    products_before = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    second = E.import_file(con, p2, "PRODUCTS", commit=True)
    products_after = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    written = products_after - products_before
    assert written > 0, ("هیچ محصولی نوشته نشد", second.errors)

    rolled = E.rollback_batch(con, second.batch_id)
    assert not rolled.errors, rolled.errors

    products_final = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert products_final == products_before, \
        ("برگشت، %d محصول باقی گذاشت" % (products_final - products_before))
    after = set(r[0] for r in con.execute("SELECT code FROM parties"))
    assert after == first_codes, "برگشت دسته دوم به اشخاص دست زد"
    con.close()


def t_rollback_marks_batch_status():
    import import_engine as E
    con = fresh()
    path = build("PARTIES", "p.xlsx", PARTY_ROWS)
    out = E.import_file(con, path, "PARTIES", commit=True)
    E.rollback_batch(con, out.batch_id)
    status = con.execute("SELECT status FROM import_batches WHERE id=?",
                         (out.batch_id,)).fetchone()[0]
    assert status == "ROLLED_BACK", status
    con.close()


def t_batch_list_newest_first():
    import import_engine as E
    con = fresh()
    first = E.import_file(con, build("PARTIES", "p.xlsx", PARTY_ROWS),
                          "PARTIES", commit=True).batch_id
    second = E.import_file(con, build("PRODUCTS", "pr.xlsx", PRODUCT_ROWS),
                           "PRODUCTS", commit=True).batch_id

    rows = con.execute(
        "SELECT id FROM import_batches ORDER BY id DESC LIMIT 10").fetchall()
    ids = [r[0] for r in rows]
    assert ids[0] == second, (ids, second)
    assert ids[1] == first, (ids, first)
    con.close()


def t_foreign_approved_never_attaches():
    """An approved document that no batch created must never be counted as part
    of a batch. This is the SQL the rollback guard now uses."""
    import import_engine as E
    con = fresh()
    out = E.import_file(con, build("PARTIES", "p.xlsx", PARTY_ROWS),
                        "PARTIES", commit=True)

    # A sales invoice approved outside any batch.
    con.execute(
        "INSERT INTO sales_invoices(code,doc_number,date_iso,date_shamsi,"
        "party_id,status) SELECT 'OUT','OUT',date('now'),'1403/01/01',"
        "MIN(id),'APPROVED' FROM parties")
    con.commit()

    scoped = con.execute(
        "SELECT COUNT(*) FROM sales_invoices t "
        "JOIN import_rows r ON r.mapped_json LIKE '{\"new_id\":' || t.id || '%' "
        "WHERE r.batch_id=? AND t.status='APPROVED'", (out.batch_id,)).fetchone()[0]
    assert scoped == 0, "سند تأییدشده بیگانه به دسته نسبت داده شد"

    # And the batch's own documents, if approved, DO count.
    mine = con.execute("SELECT id FROM parties LIMIT 1").fetchone()[0]
    con.execute(
        "INSERT INTO sales_invoices(code,doc_number,date_iso,date_shamsi,"
        "party_id,status) VALUES('MINE','MINE',date('now'),'1403/01/01',?,"
        "'APPROVED')", (mine,))
    con.commit()
    # mapped_json is a JSON STRING. Putting a SQL subquery inside it does not
    # evaluate: the literal text "(SELECT MAX(id)...)" is stored and the LIKE
    # join never matches. An earlier version of this test did exactly that and
    # reported a false failure. Resolve the id in Python first.
    mine_doc = con.execute(
        "SELECT id FROM sales_invoices WHERE code='MINE'").fetchone()[0]
    con.execute(
        "INSERT INTO import_rows(batch_id,source_row_number,raw_json,mapped_json,"
        "blank_fields_json,status,error_message) VALUES(?,9,'r',?,'','IMPORTED','')",
        (out.batch_id, '{"new_id":' + str(mine_doc) + '}'))
    con.commit()

    scoped2 = con.execute(
        "SELECT COUNT(*) FROM sales_invoices t "
        "JOIN import_rows r ON r.mapped_json LIKE '{\"new_id\":' || t.id || '%' "
        "WHERE r.batch_id=? AND t.status='APPROVED'", (out.batch_id,)).fetchone()[0]
    assert scoped2 == 1, ("سند تأییدشده خود دسته شمرده نشد", scoped2)
    con.close()


TESTS = [
    ("پیش‌نمایش هیچ چیز نمی‌نویسد", t_preview_writes_nothing),
    ("اعداد پیش‌نمایش با ثبت می‌خواند", t_preview_counts_match_commit),
    ("ثبت دقیقاً یک دسته می‌سازد", t_commit_creates_one_batch),
    ("پیش‌نمایش دوم پس از ثبت چیزی نمی‌نویسد",
     t_second_preview_after_commit_writes_nothing),
    ("برگشت فقط سندهای همان دسته را حذف می‌کند", t_rollback_deletes_only_that_batch),
    ("برگشت وضعیت دسته را عوض می‌کند", t_rollback_marks_batch_status),
    ("تاریخچه از جدید به قدیم", t_batch_list_newest_first),
    ("سند تأییدشده بیگانه به دسته نسبت داده نمی‌شود",
     t_foreign_approved_never_attaches),
]


def main():
    if not os.path.isdir(TEMPLATES):
        print("FAIL  پوشه قالب‌های مالک پیدا نشد: " + TEMPLATES)
        return 1
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
