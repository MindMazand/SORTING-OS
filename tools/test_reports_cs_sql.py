#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the C# report SQL, executed against the real schema.

WHY THIS EXISTS

`src/Mazandasht.Persistence/SqliteReportStore.cs` cannot be compiled here (no
.NET toolchain on this sandbox; see reports/CSHARP_BUILD_ATTEMPT_FA.md). It is
therefore the easiest place in the project for SQL to be wrong: a column name
typo compiles fine in C# and only fails when a human opens the window.

So the SQL strings are EXTRACTED FROM THE .cs FILE — not retyped here — and run
against a database built by the real migrations. If the C# and the schema
disagree, this fails before the window is ever opened.

WHAT IS CHECKED

  1. every SELECT in the file runs on the real schema (no unknown column)
  2. the trial balance keeps the VOIDED filter inside the JOIN — the exact bug
     that made an account vanish, and the exact bug that would be easy to
     "fix" back
  3. the baskets report reads `payments`, NOT payments-out-of-basket_movements
  4. cheque status is never read from the `status` column
  5. an unknown value renders as a dash, never "0" (string-level check on Show)
  6. no SQL string concatenates a user value — parameters only

    python3 tools/test_reports_cs_sql.py
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

CS = os.path.join(ROOT, "src", "Mazandasht.Persistence", "SqliteReportStore.cs")


def source():
    with open(CS, encoding="utf-8") as f:
        return f.read()


def code_only(text):
    """The file with // comments removed.

    A test that greps raw source matches the EXPLANATION as often as the code:
    the trial-balance comment literally contains `WHERE j.status IS NULL OR
    j.status <> 'VOIDED'` while describing the bug that was fixed. Stripping
    comments first is the difference between testing the code and testing its
    documentation.
    """
    out = []
    for line in text.splitlines():
        stripped = line.split("//")[0]
        out.append(stripped)
    return "\n".join(out)


def string_literals(text):
    """
    Reconstruct every SQL statement the C# file will send.

    C# builds SQL as `"a" + "b" + "c"` across many lines, usually the first
    argument of Query(...). A naive scan for string literals stops early and
    returns a truncated statement that fails with "incomplete input" — a
    failure of the TEST, not of the code, and exactly the kind of false signal
    that wastes a debugging session.

    Method: find each `Query(` call, take the text up to its matching close
    paren by counting parens OUTSIDE string literals, then concatenate the
    literals in that span in order.
    """
    text = code_only(text)
    out = []
    for m in re.finditer(r"Query\(", text):
        i = m.end()
        depth = 1
        j = i
        in_str = False
        while j < len(text) and depth > 0:
            c = text[j]
            if c == '"' and text[j - 1] != "\\":
                in_str = not in_str
            elif not in_str:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        span = text[i:j]
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', span)
        sql = "".join(parts).strip()
        if re.match(r"SELECT\b", sql, re.I):
            out.append(sql)
    return out


def fresh():
    import verify_database as V
    return V.build_db(os.path.join(tempfile.mkdtemp(prefix="rcs_"), "r.db"))


# ---------------------------------------------------------------------------
def t_every_sql_statement_runs_on_the_real_schema():
    con = fresh()
    statements = string_literals(source())
    assert statements, "هیچ SQL‌ای در فایل C# پیدا نشد — تست بی‌اثر است"

    failures = []
    for sql in statements:
        # @0/@1 are SQLite's numbered parameters; give them dummies.
        probe = sql
        count = len(re.findall(r"@\d+", probe))
        args = [0] * count
        try:
            con.execute(probe, args).fetchall()
        except Exception as e:                # noqa: BLE001
            failures.append("%s -> %s" % (sql[:60].replace("\n", " "), e))
    assert not failures, "SQL نامعتبر در C#: " + " | ".join(failures[:4])
    print("      %d عبارت SQL از فایل C# استخراج و اجرا شد" % len(statements))
    con.close()


def t_trial_balance_filter_is_in_the_join():
    """The bug: `WHERE j.status ...` turns the LEFT JOIN into an inner join,
    the account with only a voided line loses its row, and the trial balance
    is quietly incomplete — while still balancing."""
    text = code_only(source())
    trial = text[text.index("public ReportResult AccountingTrial"):]
    trial = trial[:trial.index("AccountBalance")]
    assert "LEFT JOIN journal_lines" in trial, "join حذف شده است"
    # The filter must be part of the ON clause, as a subquery. Written as a
    # WHERE it would silently drop accounts that only have voided lines.
    assert "AND l.journal_id IN (SELECT id FROM journal_entries" in trial, \
        "شرط فیلتر داخل ON نیست"
    assert "WHERE j.status" not in trial.replace("\n", " "), \
        "فیلتر VOIDED در WHERE برگشته — حساب‌ها بی‌صدا ناپدید می‌شوند"
    assert "l.journal_id IN (SELECT id FROM journal_entries" in trial, \
        "join با journal_entries حذف شده"


def t_baskets_reads_payments_not_basket_events():
    """A money payment cannot live in basket_movements (event_type is CHECKed
    to basket events). Reading it from there returns nothing and the seller
    looks unpaid forever."""
    text = source()
    baskets = text[text.index("public ReportResult BasketsReport"):]
    baskets = baskets[:baskets.index("ParseFormatted")]
    assert "FROM payments p" in baskets, \
        "گزارش سبد دیگر از payments نمی‌خواند"
    assert "event_type = 'PAYMENT'" not in baskets, \
        "دوباره پرداخت را از basket_movements می‌خواند"
    assert "COALESCE(p.status, 'APPROVED') <> 'VOIDED'" in baskets, \
        "پرداخت ابطال‌شده نباید در مانده بیاید"


def t_cheque_status_is_never_read_from_the_column():
    text = source()
    cheques = text[text.index("private List<ChequeRow> Cheques()"):]
    cheques = cheques[:cheques.index("private static string Sum")]
    assert "c.status" not in cheques, \
        "وضعیت از ستون status خوانده می‌شود؛ باید از paid_date محاسبه شود"
    assert "PaidDate" in cheques and "IsCleared" in text, \
        "وضعیت محاسبه‌شده وجود ندارد"


def t_unknown_renders_as_dash_not_zero():
    """«خالی ≠ صفر» at the last possible moment: the formatter."""
    text = source()
    show = text[text.index("internal static string Show(Cell cell)"):]
    show = show[:show.index("private static long? AsLong")]
    assert '"—"' in show, "نمایش مقدار نامعلوم باید خط تیره باشد"
    assert '"0"' not in show, "مقدار نامعلوم نباید صفر نشان داده شود"


def t_no_user_value_is_concatenated_into_sql():
    """Parameters only. A party code pasted into SQL is an injection, and an
    injection in a report is still an injection."""
    text = source()
    # A '+' followed by anything that is NOT another string literal or a
    # newline-then-literal is a value being appended. Adjacent "..." + "..."
    # is how C# spells one long literal and is not an injection.
    bad = re.findall(r'"[^"]*(?:WHERE|AND)[^"]*"\s*\+\s*(?![\s"])(\S+)', text)
    assert not bad, "الحاق مقدار به SQL: %s" % bad[:3]
    assert "AddWithValue" in text, "پارامترها اضافه نمی‌شوند"


def t_every_report_in_the_python_engine_has_a_cs_counterpart():
    """Parity by name, so a report added to one side cannot be forgotten on
    the other. The seventh report is the known, documented exception."""
    import reports_engine as R
    text = source()
    for rid, title in R.REPORTS:
        # The id appears in Availability() and the method returns it.
        assert '"%s"' % rid in text, "گزارش %s در C# نیست" % rid
    assert '"financial_report"' in text, \
        "گزارش ناموجود باید در فهرست باشد تا دلیلش نشان داده شود"


def t_every_available_report_has_a_wiring_case():
    """
    A report can be listed as available and still throw when opened, if the
    ReportWiring switch has no case for it. That is the worst combination:
    the card looks openable and the button produces an exception.

    AccountingBalance was exactly this for one commit — listed in
    Availability(), listed as available in the wiring, and with no method
    behind it.
    """
    wiring = os.path.join(ROOT, "src", "Mazandasht.Presentation", "Reports",
                          "ReportWiring.cs")
    with open(wiring, encoding="utf-8") as f:
        text = code_only(f.read())

    catalogue = re.findall(r'Tuple\.Create\("(\w+)"', text)
    assert catalogue, "فهرست گزارش‌ها در ReportWiring پیدا نشد"

    cases = set(re.findall(r'case "(\w+)":', text))
    # Reports deliberately refusing must be explicit, with a reason on screen.
    refusals = set(re.findall(r'case "(\w+)":\s*\n\s*throw new ReportUnavailableException',
                              text))

    missing = [r for r in catalogue if r not in cases]
    assert not missing, "گزارش در فهرست هست ولی case ندارد: %s" % missing

    # The only report allowed to refuse is the one the owner has not defined.
    refusing = sorted(refusals)
    assert refusing == ["financial_report"], \
        "گزارش‌هایی که استثنا می‌اندازند: %s — تنها گزارش مالی مجاز است" % refusing

    # And every non-refusing case must call a store method that exists.
    store_cs = os.path.join(ROOT, "src", "Mazandasht.Persistence",
                            "SqliteReportStore.cs")
    with open(store_cs, encoding="utf-8") as f:
        store = code_only(f.read())
    for rid in catalogue:
        if rid in refusing:
            continue
        m = re.search(r'case "%s":\s*\n\s*result = store\.(\w+)\(' % rid, text)
        if m:
            method = m.group(1)
            assert re.search(r"public ReportResult %s\(" % method, store), \
                "case %s به متد %s اشاره می‌کند که وجود ندارد" % (rid, method)


TESTS = [
    ("هر گزارش موجود در wiring یک case دارد", t_every_available_report_has_a_wiring_case),
    ("هر SQL فایل C# روی اسکیمای واقعی اجرا می‌شود", t_every_sql_statement_runs_on_the_real_schema),
    ("فیلتر VOIDED در JOIN است نه WHERE", t_trial_balance_filter_is_in_the_join),
    ("گزارش سبد از payments می‌خواند", t_baskets_reads_payments_not_basket_events),
    ("وضعیت چک از ستون status خوانده نمی‌شود", t_cheque_status_is_never_read_from_the_column),
    ("مقدار نامعلوم خط تیره است نه صفر", t_unknown_renders_as_dash_not_zero),
    ("هیچ مقدار کاربر به SQL الحاق نمی‌شود", t_no_user_value_is_concatenated_into_sql),
    ("هر گزارش پایتون معادل C# دارد", t_every_report_in_the_python_engine_has_a_cs_counterpart),
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
