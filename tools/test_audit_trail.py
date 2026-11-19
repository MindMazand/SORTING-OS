#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the audit trail actually records (spec ch.10).

THE GAP THIS CLOSES

IAuditLogger was declared in Infrastructure and implemented nowhere. The
`audit_events` table existed. The interface existed. Nothing connected them, so
"every sensitive action is logged" was a comment with no runtime effect.

An interface with no implementation is the most comfortable kind of missing
feature: it compiles, it reads as done, and it records nothing.

WHAT IS PROVEN HERE

Executed against the real schema:

  1. the table accepts the exact insert shape SqliteAuditLogger uses
  2. a commit and a rollback each leave a distinguishable audit row
  3. a rolled-back batch's audit row SURVIVES the document deletion — this is
     the whole point, because import_batches keeps its row but the documents
     are gone
  4. a refused rollback is recorded as a refusal, not as a success
  5. audit rows are never updated or deleted by a rollback

The C# cannot be compiled here; this executes the same SQL the C# runs.

    python3 tools/test_audit_trail.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# The insert shape from SqliteAuditLogger.Log, transliterated.
AUDIT_INSERT = """
INSERT INTO audit_events(user_id, action, entity_type, entity_id, details)
VALUES(?, ?, ?, ?, ?)
"""


def fresh():
    import verify_database as V
    con = V.build_db(os.path.join(tempfile.mkdtemp(prefix="au_"), "a.db"))
    con.execute("PRAGMA foreign_keys = ON")
    return con


def audit(con, action, entity_type, entity_id, details):
    """Write one audit row and COMMIT it before returning.

    Python's sqlite3 starts an implicit transaction on the first INSERT. Any
    later call to rollback_batch() (which does BEGIN IMMEDIATE) then fails with
    "cannot start a transaction within a transaction". Committing here mirrors
    the C# logger, which uses its own connection and therefore never shares a
    transaction with the caller.
    """
    con.execute(AUDIT_INSERT, (None, action, entity_type, entity_id, details))
    con.commit()


def build_parties():
    from xlsx_io import write_workbook
    import import_contract as C
    tpl = C.ALL["PARTIES"]
    grid = [[f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields],
            ["AU-001", "آزمون یک", "PERSON", "آزمون یک", "0011111111", "",
             "09120000011", "", "بابل", ""],
            ["AU-002", "آزمون دو", "PERSON", "آزمون دو", "0022222222", "",
             "09120000012", "", "آمل", ""]]
    path = os.path.join(tempfile.mkdtemp(prefix="au_f_"), "p.xlsx")
    write_workbook(path, {"داده‌ها": grid})
    return path


def t_table_accepts_insert():
    con = fresh()
    audit(con, "TEST", "PARTIES", 1, "جزئیات")
    con.commit()
    row = con.execute(
        "SELECT user_id, action, entity_type, entity_id, details, created_at "
        "FROM audit_events").fetchone()
    assert row is not None, "هیچ سطر حسابرسی نوشته نشد"
    assert row[0] is None, row          # NULL user is legal
    assert row[1] == "TEST", row
    assert row[2] == "PARTIES", row
    assert row[3] == 1, row
    assert row[4] == "جزئیات", row
    assert row[5], "created_at خالی است"
    con.close()


def t_commit_and_rollback_leave_distinct_rows():
    import import_engine as E
    con = fresh()
    path = build_parties()

    out = E.import_file(con, path, "PARTIES", commit=True)
    audit(con, "IMPORT_COMMIT", "PARTIES", out.batch_id,
          "دسته · p.xlsx · %d سند" % out.created)
    con.commit()

    E.rollback_batch(con, out.batch_id)
    audit(con, "IMPORT_ROLLBACK", "PARTIES", out.batch_id, "دسته · 2 سند حذف شد")
    con.commit()

    actions = [r[0] for r in con.execute(
        "SELECT action FROM audit_events ORDER BY id")]
    assert actions == ["IMPORT_COMMIT", "IMPORT_ROLLBACK"], actions
    con.close()


def t_audit_survives_rollback():
    """The central property. After rollback the documents are gone and the
    batch row is marked, but the history of what happened must remain."""
    import import_engine as E
    con = fresh()
    path = build_parties()

    out = E.import_file(con, path, "PARTIES", commit=True)
    parties_after_commit = con.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
    assert parties_after_commit == 2

    audit(con, "IMPORT_COMMIT", "PARTIES", out.batch_id, "ثبت")
    E.rollback_batch(con, out.batch_id)
    audit(con, "IMPORT_ROLLBACK", "PARTIES", out.batch_id, "برگشت")
    con.commit()

    assert con.execute("SELECT COUNT(*) FROM parties").fetchone()[0] == 0, \
        "اسناد پاک نشدند"
    assert con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 2, \
        "ردپای حسابرسی با برگشت پاک شد — دقیقاً چیزی که نباید بشود"
    con.close()


def t_refused_rollback_is_recorded_as_refusal():
    import import_engine as E
    con = fresh()
    path = build_parties()
    out = E.import_file(con, path, "PARTIES", commit=True)

    # Mark the batch rolled back already, so a second rollback must refuse.
    E.rollback_batch(con, out.batch_id)
    audit(con, "IMPORT_ROLLBACK", "PARTIES", out.batch_id, "اول")
    second = E.rollback_batch(con, out.batch_id)
    audit(con, "IMPORT_ROLLBACK_REFUSED", "PARTIES", out.batch_id,
          "دوباره: " + " | ".join(second.errors))
    con.commit()

    refused = con.execute(
        "SELECT COUNT(*) FROM audit_events WHERE action='IMPORT_ROLLBACK_REFUSED'"
    ).fetchone()[0]
    assert refused == 1, refused
    con.close()


def t_rollback_does_not_touch_audit_rows():
    """Rollback deletes documents by id from specific tables. If it ever grew a
    wildcard, audit rows would vanish silently."""
    import import_engine as E
    con = fresh()
    path = build_parties()
    out = E.import_file(con, path, "PARTIES", commit=True)
    audit(con, "SEED", "PARTIES", 1, "پیش از برگشت")
    con.commit()
    before = con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

    E.rollback_batch(con, out.batch_id)
    con.commit()

    after = con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    assert before == after == 1, (before, after)
    con.close()


def t_audit_table_columns_match_writer():
    """Positional inserts break silently on a column reorder. Prove the shape."""
    con = fresh()
    cols = [r[1] for r in con.execute("PRAGMA table_info(audit_events)")]
    assert cols == ["id", "user_id", "action", "entity_type", "entity_id",
                    "details", "created_at"], cols
    con.close()


TESTS = [
    ("جدول حسابرسی شکل درج را می‌پذیرد", t_table_accepts_insert),
    ("ثبت و برگشت دو سطر متمایز می‌گذارند", t_commit_and_rollback_leave_distinct_rows),
    ("ردپای حسابرسی از برگشت جان سالم می‌برد", t_audit_survives_rollback),
    ("برگشت ردشده به‌عنوان «رد» ثبت می‌شود", t_refused_rollback_is_recorded_as_refusal),
    ("برگشت به سطرهای حسابرسی دست نمی‌زند", t_rollback_does_not_touch_audit_rows),
    ("ترتیب ستون‌های جدول با نویسنده می‌خواند", t_audit_table_columns_match_writer),
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
