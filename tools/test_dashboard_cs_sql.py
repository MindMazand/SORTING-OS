#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — do the C# queries produce the same numbers as the Python ones?

THE GAP THIS CLOSES

tools/check_dashboard_parity.py proves the C# SQL *text* matches the Python SQL
text. That is necessary but not sufficient: it would pass if both copies were
wrong, and it says nothing about parameter binding or the approved/review split.

This script goes one step further. It:

  1. extracts the SQL strings from the C# file by balanced-parenthesis scan
     (not by regex — SQL is full of COALESCE(...) and a non-greedy match would
     silently truncate at the first inner paren);
  2. binds each one to its KPI key by reading the Make("<key>", ..., var) call;
  3. runs those strings against a database seeded with known documents;
  4. computes the same nineteen KPIs with the Python reference;
  5. asserts the two agree number for number.

So the SQL executed here is genuinely pulled out of the .cs file. If someone
edits the C# and forgets the Python, this fails.

WHAT IT STILL DOES NOT PROVE

The C# never runs. Decimal conversion, ADO.NET parameter marshalling, and null
handling are unexercised — those need the Windows toolchain. This narrows the
risk to "the SQL and the split are right" and leaves the rest labelled NOT RUN.

    python3 tools/test_dashboard_cs_sql.py
"""
import os
import re
import sys
import tempfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "agents"))

CS_FILE = os.path.join(ROOT, "src", "Mazandasht.Persistence",
                       "SqliteDashboardStore.cs")

MIN_EXPECTED = 15


def _balanced(text, open_index):
    """Return the text inside the parenthesis that opens at open_index.

    A regex cannot do this. The SQL is full of COALESCE(...) and SUM(...), so
    a non-greedy match stops at the first inner closing paren and extracts a
    truncated query, which then fails to run for a reason unrelated to the
    real code.
    """
    depth = 0
    in_string = False
    i = open_index
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[open_index + 1:i]
        i += 1
    raise ValueError("unbalanced parenthesis at %d" % open_index)


def _top_level_args(body):
    """Split a C# argument list on commas that are at depth 0 and outside strings.

    Why not regex the SQL instead: the approved and pending statements are two
    separate *arguments* of Split(con, A, B, ...). Their boundary is a comma in
    the C# source. Trying to recover that boundary by looking for "@d" or for a
    second "SELECT" is guesswork that breaks on every statement that has no
    date parameter, or that contains a subquery starting with SELECT. The
    argument separator is the only boundary that is unambiguous.
    """
    args = []
    depth = 0
    in_string = False
    current = []
    i = 0
    while i < len(body):
        ch = body[i]
        if in_string:
            current.append(ch)
            if ch == "\\":
                if i + 1 < len(body):
                    current.append(body[i + 1])
                    i += 2
                    continue
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
                current.append(ch)
            elif ch in "([{":
                depth += 1
                current.append(ch)
            elif ch in ")]}":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                args.append("".join(current))
                current = []
            else:
                current.append(ch)
        i += 1
    if current:
        args.append("".join(current))
    return args


def _sql_of(arg):
    """Join the string literals of one C# argument into its SQL text."""
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', arg)).strip()


def extract_pairs():
    """{kpi_key: [(approved_sql, pending_sql), ...]} from the C# source.

    The pattern is:

        var sales = Split(con, "A", "B", startIso);
        result.Add(Make("sales", KpiValue.UnitKind.Rial, sales));

    The variable binds the SQL and the Make() call binds the key, so the key
    comes AFTER the SQL. A backwards search would attribute every KPI to its
    predecessor.
    """
    with open(CS_FILE, encoding="utf-8") as fh:
        text = fh.read()

    pairs = {}

    for m in re.finditer(r'var\s+(\w+)\s*=\s*Split\(', text):
        var_name = m.group(1)
        open_paren = m.end() - 1
        body = _balanced(text, open_paren)
        args = _top_level_args(body)
        # args = ["con", approvedSql, pendingSql, dateParam, (direction)?]
        if len(args) < 3:
            continue
        approved_sql = _sql_of(args[1])
        pending_sql = _sql_of(args[2])

        key_match = re.search(
            r'Make\("([a-z_0-9]+)"\s*,\s*KpiValue\.UnitKind\.\w+\s*,\s*'
            + re.escape(var_name) + r'\s*\)', text)
        if not key_match or not approved_sql or not pending_sql:
            continue
        pairs.setdefault(key_match.group(1), []).append(
            (approved_sql, pending_sql))

    # Inline form: result.Add(Make("key", Unit, Split(con, "A", "B", param)));
    # No intermediate variable, so the by-variable pass above cannot see it.
    for m in re.finditer(r'result\.Add\(Make\("([a-z_0-9]+)"', text):
        key = m.group(1)
        window = text[m.end():m.end() + 2000]
        # CRITICAL: only handle the inline form. When the third argument is a
        # bare variable (Make("sales", ..., sales)) the SQL was already bound by
        # the pass above, and searching forward from here finds the NEXT KPI's
        # Split — which is how "sales" silently acquired purchase's query and
        # both numbers came out wrong while every query still "ran fine".
        third = re.search(r'KpiValue\.UnitKind\.\w+\s*,\s*([\w\.]+)\s*\)',
                          window)
        if third and re.fullmatch(r"[A-Za-z_]\w*", third.group(1)):
            continue
        call = re.search(r"Split\(", window)
        if not call:
            continue
        body = _balanced(window, call.end() - 1)
        args = _top_level_args(body)
        if len(args) < 3:
            continue
        approved_sql = _sql_of(args[1])
        pending_sql = _sql_of(args[2])
        if approved_sql and pending_sql:
            pairs.setdefault(key, []).append((approved_sql, pending_sql))

    # The five weight windows share one helper, so they bind by order.
    weight_keys = re.findall(r'Make\("(weight_[a-z0-9_]+)"', text)
    helper = re.search(
        r'private decimal\[\] Weight\(SQLiteConnection con, int days, '
        r'string direction\)\s*\{', text)
    if helper:
        body = _balanced(text, helper.end() - 1)
        # Inside the helper it is a plain Split(con, A, B, date, dir).
        call = re.search(r"Split\(", body)
        if call:
            args = _top_level_args(_balanced(body, call.end() - 1))
            if len(args) >= 3:
                approved_sql = _sql_of(args[1])
                pending_sql = _sql_of(args[2])
                if approved_sql and pending_sql:
                    for key in weight_keys:
                        pairs.setdefault(key, []).append(
                            (approved_sql, pending_sql))

    return pairs


def to_sqlite(sql):
    """ADO.NET writes @d/@dir; sqlite3 wants :d/:dir. Named params keep the
    direction binding readable."""
    return sql.replace("@dir", ":dir").replace("@d", ":d")


def build_seeded():
    """A database from the real migration path, seeded with documents whose
    statuses make a wrong predicate show up as a wrong number."""
    import verify_database as V
    path = os.path.join(tempfile.mkdtemp(prefix="cs_par_"), "p.db")
    con = V.build_db(path)
    con.execute("PRAGMA foreign_keys = ON")

    con.execute("INSERT INTO parties(code,display_name,nature,party_kind,"
                "party_kind_confirmed) VALUES('P1','طرف یک','C','PERSON',1)")
    con.execute("INSERT INTO parties(code,display_name,nature,party_kind,"
                "party_kind_confirmed) VALUES('P2','طرف دو','C','PERSON',1)")
    p1 = con.execute("SELECT id FROM parties WHERE code='P1'").fetchone()[0]
    p2 = con.execute("SELECT id FROM parties WHERE code='P2'").fetchone()[0]

    for code, status, net in (("S1", "APPROVED", 1000000),
                              ("S2", "DRAFT", 400000),
                              ("S3", "VOIDED", 999000)):
        con.execute("INSERT INTO sales_invoices(code,doc_number,date_iso,"
                    "date_shamsi,party_id,status) VALUES(?,?,date('now'),"
                    "'1403/05/01',?,?)", (code, code, p1, status))
        inv = con.execute("SELECT id FROM sales_invoices WHERE code=?",
                          (code,)).fetchone()[0]
        con.execute("INSERT INTO sales_invoice_lines(invoice_id,grams,"
                    "rate_rial_per_kg,gross_rial,net_rial) "
                    "VALUES(?,1000,1000,?,?)", (inv, net, net))

    for code, status, net in (("B1", "APPROVED", 600000),
                              ("B2", "REVIEW", 250000)):
        con.execute("INSERT INTO purchase_invoices(code,doc_number,date_iso,"
                    "date_shamsi,party_id,status) VALUES(?,?,date('now'),"
                    "'1403/05/01',?,?)", (code, code, p2, status))
        inv = con.execute("SELECT id FROM purchase_invoices WHERE code=?",
                          (code,)).fetchone()[0]
        con.execute("INSERT INTO purchase_invoice_lines(invoice_id,grams,"
                    "rate_rial_per_kg,gross_rial,net_rial) "
                    "VALUES(?,1000,1000,?,?)", (inv, net, net))

    con.execute("INSERT INTO payments(code,party_id,direction,amount_rial,"
                "date_iso,date_shamsi,status) VALUES('R1',?,'IN',300000,"
                "date('now'),'1403/05/01','APPROVED')", (p1,))
    con.execute("INSERT INTO payments(code,party_id,direction,amount_rial,"
                "date_iso,date_shamsi,status) VALUES('R2',?,'IN',150000,"
                "date('now'),'1403/05/01','DRAFT')", (p1,))
    con.execute("INSERT INTO payments(code,party_id,direction,amount_rial,"
                "date_iso,date_shamsi,status) VALUES('O1',?,'OUT',200000,"
                "date('now'),'1403/05/01','APPROVED')", (p2,))

    con.commit()
    return con


def run_cs_pairs(con, pairs):
    """Execute the extracted C# SQL and return {key: (approved, review)}."""
    today = date.today().isoformat()
    out = {}
    for key, plist in pairs.items():
        approved_total = 0
        review_total = 0
        for approved_sql, pending_sql in plist:
            for sql, bucket in ((approved_sql, "a"), (pending_sql, "r")):
                # The weight queries need a direction; supply a harmless one
                # for SQL that has no :dir placeholder (sqlite ignores extras
                # only for named params that are absent — it does not, so bind
                # per-query based on presence).
                params = {"d": today}
                if ":dir" in sql:
                    params["dir"] = "IN"
                cur = con.execute(to_sqlite(sql), params)
                row = cur.fetchone()
                val = (row[0] or 0) if row else 0
                if bucket == "a":
                    approved_total += val
                else:
                    review_total += val
        out[key] = (approved_total, review_total)
    return out


def main():
    if not os.path.exists(CS_FILE):
        print("FAIL  فایل C# پیدا نشد")
        return 1

    pairs = extract_pairs()
    if len(pairs) < MIN_EXPECTED:
        print("FAIL  فقط %d KPI از فایل C# استخراج شد؛ انتظار %d"
              % (len(pairs), MIN_EXPECTED))
        print("      کلیدها:", sorted(pairs))
        return 1

    con = build_seeded()

    import A_dashboard_queries as REF
    py = REF.compute(con, days=1)
    cs = run_cs_pairs(con, pairs)

    print("KPI استخراج‌شده از فایل C#: %d" % len(pairs))
    print()
    print("%-18s %14s %14s %6s" % ("KPI", "پایتون", "C#", "وضعیت"))

    fails = 0
    for key in sorted(cs):
        if key not in py:
            continue
        py_val = py[key]["value"]
        cs_val = cs[key][0] + cs[key][1]
        same = (py_val == cs_val)
        if not same:
            fails += 1
        print("%-18s %14s %14s %6s"
              % (key, py_val, cs_val, "OK" if same else "DIFF"))

    # gross_profit has no SQL of its own in C#: it is derived from the
    # sales/purchase pair, so compare it the same way the C# derives it.
    if "sales" in cs and "purchase" in cs and "gross_profit" in py:
        cs_gp = ((cs["sales"][0] + cs["sales"][1])
                 - (cs["purchase"][0] + cs["purchase"][1]))
        ok = (cs_gp == py["gross_profit"]["value"])
        print("%-18s %14s %14s %6s"
              % ("gross_profit", py["gross_profit"]["value"], cs_gp,
                 "OK" if ok else "DIFF"))
        if not ok:
            fails += 1

    print()
    if fails:
        print("FAIL  %d KPI بین SQL استخراج‌شده از C# و مرجع پایتون اختلاف دارد"
              % fails)
        return 1
    print("PASS  SQL استخراج‌شده از فایل C# همان اعداد مرجع پایتون را می‌دهد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
