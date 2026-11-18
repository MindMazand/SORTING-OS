#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the Python report engine and the C# report store must agree.

WHY THIS EXISTS

The report rules exist twice: `tools/reports_engine.py` (proven by
`tools/test_reports.py`, 13/13 on a real database) and
`src/Mazandasht.Persistence/SqliteReportStore.cs` (the production path, which
cannot be compiled here). Two implementations of the same rule WILL drift, and
the drift is invisible: both compilers are happy, both look right, and the
owner sees a report whose columns do not match the workbook.

This gate reads the C# column arrays out of the source and compares them, name
by name, with the Python engine's. A column added on one side and not the other
fails here.

WHAT IS CHECKED

  1. the same six report ids exist on both sides
  2. the same column COUNT per report
  3. the same column NAMES per report, in the same order
  4. the C# unpaid report reuses the month report's columns rather than
     re-declaring them (the owner's workbook has one column set for both)
  5. the C# formatter renders an unknown value as a dash, matching Python
  6. every C# method the wiring calls exists in the store

    python3 tools/test_reports_parity.py
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import reports_engine as R                          # noqa: E402

CS = os.path.join(ROOT, "src", "Mazandasht.Persistence", "SqliteReportStore.cs")
WIRING = os.path.join(ROOT, "src", "Mazandasht.Presentation", "Reports",
                      "ReportWiring.cs")

# report id -> the C# method that builds it
METHODS = {
    "cheques_issues": "ChequesIssues",
    "cheques_month": "ChequesMonth",
    "cheques_unpaid": "ChequesUnpaid",       # reuses month's columns
    "baskets_report": "BasketsReport",
    "accounting_trial": "AccountingTrial",
    "accounting_balance": "AccountingBalance",
}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def fresh_with_seller():
    """A database that HAS the seller, so baskets_report returns a real table
    instead of its 'seller not found' early return."""
    import verify_database as V
    con = V.build_db(os.path.join(tempfile.mkdtemp(prefix="par_"), "p.db"))
    con.execute("INSERT INTO parties(code, display_name, nature) "
                "VALUES('S004','فروشنده آزمون','SL')")
    con.commit()
    return con


def python_report(con, rid):
    if rid == "baskets_report":
        return R.build(con, rid, party_code="S004")
    return R.build(con, rid)


def cs_columns(source, method):
    """The string literals inside `Columns = new[] { ... }` for a method."""
    start = source.index("public ReportResult %s(" % method)
    body = source[start:start + 6000]
    m = re.search(r"Columns = (new\[\]\s*\{.*?\}|month\.Columns)", body, re.S)
    if not m:
        return None
    if m.group(1).startswith("month."):
        return "REUSE"
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))


# ---------------------------------------------------------------------------
def t_same_report_ids_on_both_sides():
    py_ids = [rid for rid, _ in R.REPORTS]
    assert len(py_ids) == 6, py_ids
    source = read(CS)
    for rid in py_ids:
        assert '"%s"' % rid in source, "گزارش %s در C# نیست" % rid
        assert rid in METHODS, "نگاشت تست برای %s تعریف نشده" % rid


def t_same_column_count_per_report():
    con = fresh_with_seller()
    source = read(CS)
    problems = []
    for rid, method in METHODS.items():
        py = python_report(con, rid)
        cols = cs_columns(source, method)
        if cols == "REUSE":
            continue
        if cols is None:
            problems.append("%s: ستون‌ها در C# پیدا نشد" % rid)
            continue
        if len(cols) != len(py["columns"]):
            problems.append("%s: پایتون %d ستون، C# %d ستون"
                            % (rid, len(py["columns"]), len(cols)))
    assert not problems, " | ".join(problems)
    con.close()


def t_same_column_names_in_order():
    """Count parity is not enough: two reports could hold the same NUMBER of
    different columns and still be wrong."""
    con = fresh_with_seller()
    source = read(CS)
    problems = []
    for rid, method in METHODS.items():
        if rid == "cheques_unpaid":
            continue                     # checked by the reuse test
        py = python_report(con, rid)
        cols = cs_columns(source, method)
        if not cols or cols == "REUSE":
            continue
        if cols != py["columns"]:
            for a, b in zip(py["columns"], cols):
                if a != b:
                    problems.append("%s: «%s» ≠ «%s»" % (rid, a, b))
            if len(cols) != len(py["columns"]):
                problems.append("%s: طول متفاوت" % rid)
    assert not problems, " | ".join(problems)
    con.close()


def t_unpaid_reuses_the_month_columns():
    """The owner's Cheques.xlsx gives one column set for both Month and
    Unpaid. Re-declaring it invites the two to drift apart."""
    cols = cs_columns(read(CS), "ChequesUnpaid")
    assert cols == "REUSE", \
        "گزارش چک‌های پاس‌نشده باید ستون‌های گزارش گردش را دوباره استفاده کند"


def t_dash_for_unknown_on_both_sides():
    con = fresh_with_seller()
    source = read(CS)
    # C#: the whole-formatter method, not any stray literal.
    start = source.index("internal static string Show(Cell cell)")
    show = source[start:start + 800]
    assert '"—"' in show, "C# مقدار نامعلوم را خط تیره نشان نمی‌دهد"
    # Python: a report over no rows must total to None, not 0.
    r = python_report(con, "cheques_issues")
    assert r["totals"]["amount"] is None, r["totals"]
    con.close()


def t_wiring_cases_all_have_store_methods():
    wiring = read(WIRING)
    store = read(CS)
    called = re.findall(r"result = store\.(\w+)\(", wiring)
    assert called, "wiring هیچ متدی صدا نمی‌زند"
    for method in called:
        assert re.search(r"public ReportResult %s\(" % method, store), \
            "wiring متد %s را صدا می‌زند که در store نیست" % method


def t_cs_has_no_coalesce_to_zero_on_money():
    """
    The report layer must not turn an unknown amount into 0 on the way out.

    COALESCE(x, 0) is correct INSIDE a SUM over rows that exist; it is wrong
    when applied to a value that may be genuinely unknown. This check is
    deliberately narrow: it looks for COALESCE on a single money column that is
    NOT inside an aggregate, which is the shape that silently prints 0.
    """
    source = read(CS)
    # COALESCE(SUM(...)) is fine. COALESCE(<col>_rial, 0) on a bare column is not.
    bad = re.findall(r"COALESCE\(\s*(?!SUM|COUNT)(\w*_rial)\s*,\s*0\s*\)", source)
    assert not bad, "COALESCE مستقیم روی ستون پولی (خالی → صفر): %s" % sorted(set(bad))


TESTS = [
    ("همان شناسه گزارش‌ها در هر دو طرف", t_same_report_ids_on_both_sides),
    ("تعداد ستون‌ها یکسان", t_same_column_count_per_report),
    ("نام ستون‌ها و ترتیب یکسان", t_same_column_names_in_order),
    ("گزارش پاس‌نشده ستون‌های گردش را بازاستفاده می‌کند", t_unpaid_reuses_the_month_columns),
    ("خط تیره برای مقدار نامعلوم در هر دو", t_dash_for_unknown_on_both_sides),
    ("هر case در wiring متد store دارد", t_wiring_cases_all_have_store_methods),
    ("هیچ COALESCE خالی→صفر روی ستون پولی", t_cs_has_no_coalesce_to_zero_on_money),
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
