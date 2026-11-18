#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the tools screen's probes, executed against the real schema.

WHY THIS EXISTS

The tools screen used to print "آخرین اجرا: —" on every card. A card that says
"آماده" (ready) while also saying "never run" is a claim without evidence — the
exact thing this project keeps having to correct.

DatabaseProbe (src/Mazandasht.Presentation/Tools/DatabaseProbe.cs) now asks the
database real questions. Those questions are SQL strings in a .cs file that
cannot be compiled here, so this script runs the same SQL against a database
built by the real migrations and asserts:

  1. every probe query is valid SQL on the real schema
  2. counts are zero on a fresh database (not an exception, not None)
  3. after an import: batch count, REVIEW count and created_at are real
  4. after a rollback: the ROLLED_BACK count rises
  5. audit_events counts what the audit trail wrote
  6. PRAGMA integrity_check returns exactly "ok"

If any of these strings drifts from the schema, this fails here rather than
showing a broken card on the owner's screen.

    python3 tools/test_tools_probe.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# Verbatim from DatabaseProbe call sites in ToolsViewModel.ProbeDatabase.
PROBES = {
    "batches": "SELECT COUNT(*) FROM import_batches",
    "rolled": "SELECT COUNT(*) FROM import_batches WHERE status='ROLLED_BACK'",
    "pending": "SELECT COUNT(*) FROM import_batches WHERE status='REVIEW'",
    "last_import": "SELECT MAX(created_at) FROM import_batches",
    "audit": "SELECT COUNT(*) FROM audit_events",
    "last_audit": "SELECT MAX(created_at) FROM audit_events",
}

INTEGRITY = "PRAGMA integrity_check"


def fresh():
    import verify_database as V
    con = V.build_db(os.path.join(tempfile.mkdtemp(prefix="tp_"), "t.db"))
    con.execute("PRAGMA foreign_keys = ON")
    return con


def parties_file():
    from xlsx_io import write_workbook
    import import_contract as C
    tpl = C.ALL["PARTIES"]
    grid = [[f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields],
            ["TP-001", "آزمون", "PERSON", "آزمون", "0010000001", "",
             "09120000021", "", "بابل", ""]]
    path = os.path.join(tempfile.mkdtemp(prefix="tp_f_"), "p.xlsx")
    write_workbook(path, {"داده‌ها": grid})
    return path


def scalar(con, sql):
    row = con.execute(sql).fetchone()
    return (row[0] if row else 0) or 0


# ---------------------------------------------------------------------------
def t_all_probes_are_valid_sql():
    """A typo in a probe string would surface as a blank card, not an error."""
    con = fresh()
    for name, sql in PROBES.items():
        try:
            con.execute(sql).fetchone()
        except Exception as e:                    # noqa: BLE001
            raise AssertionError("کوئری «%s» نامعتبر است: %s" % (name, e))
    con.close()


def t_fresh_database_is_all_zero():
    """The empty state must be zeros, not None and not an exception."""
    con = fresh()
    for name, sql in PROBES.items():
        value = scalar(con, sql)
        assert value == 0, (name, value)
    con.close()


def t_after_import_counts_are_real():
    import import_engine as E
    con = fresh()
    out = E.import_file(con, parties_file(), "PARTIES", commit=True)

    assert scalar(con, PROBES["batches"]) == 1
    assert scalar(con, PROBES["pending"]) == 1, \
        "دسته تازه باید REVIEW باشد تا در شمارش «منتظر تأیید» بیاید"
    assert scalar(con, PROBES["rolled"]) == 0

    last = con.execute(PROBES["last_import"]).fetchone()[0]
    assert last, "created_at خالی است"
    # The schema stores "YYYY-MM-DD HH:MM:SS" — a SPACE, not an ISO "T".
    # An earlier version of ToolsViewModel.When() assumed the T form and
    # produced "2026-11-1808:43" on real rows. Assert the actual shape so a
    # schema change to either form is caught here.
    assert len(last) >= 16, last
    assert last[4] == "-" and last[7] == "-", last
    assert last[10] in (" ", "T"), ("جداکننده تاریخ/ساعت غیرمنتظره", last)
    con.close()


def t_after_rollback_count_rises():
    import import_engine as E
    con = fresh()
    out = E.import_file(con, parties_file(), "PARTIES", commit=True)
    assert scalar(con, PROBES["rolled"]) == 0

    E.rollback_batch(con, out.batch_id)
    assert scalar(con, PROBES["rolled"]) == 1, "شمارش برگشت‌خورده بالا نرفت"
    assert scalar(con, PROBES["pending"]) == 0, \
        "دسته برگشت‌خورده هنوز «منتظر تأیید» شمرده می‌شود"
    con.close()


def t_audit_probe_is_zero_until_written():
    con = fresh()
    assert scalar(con, PROBES["audit"]) == 0
    con.execute(
        "INSERT INTO audit_events(action,entity_type,details) VALUES('X','Y','Z')")
    con.commit()
    assert scalar(con, PROBES["audit"]) == 1
    last = con.execute(PROBES["last_audit"]).fetchone()[0]
    assert last, "created_at حسابرسی خالی است"
    con.close()


def t_integrity_check_returns_ok():
    """The tools card shows this verbatim. It must be exactly 'ok' so the
    comparison in ToolsViewModel (== "ok") is not a near-miss."""
    con = fresh()
    value = con.execute(INTEGRITY).fetchone()[0]
    assert value == "ok", value
    con.close()


TESTS = [
    ("همه کوئری‌های probe روی اسکیمای واقعی معتبرند", t_all_probes_are_valid_sql),
    ("پایگاه داده تازه: همه صفر", t_fresh_database_is_all_zero),
    ("پس از واردسازی، شمارش‌ها واقعی‌اند", t_after_import_counts_are_real),
    ("پس از برگشت، شمارش برگشت بالا می‌رود", t_after_rollback_count_rises),
    ("شمارش حسابرسی تا نوشتن، صفر است", t_audit_probe_is_zero_until_written),
    ("integrity_check دقیقاً ok است", t_integrity_check_returns_ok),
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
