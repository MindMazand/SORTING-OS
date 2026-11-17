#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASH — prove the C# import writer only touches columns that exist.

The C# writer builds INSERT dictionaries by hand. A typo there (say
"variety" instead of "variety_name") is invisible until a user imports a file
and the whole batch dies at runtime — on their machine, not here.

This script reads every `_store.Insert("table", new Dictionary ... { "col", ... })`
call, every `PRAGMA table_info` lookup target and every lookup spec, and
checks them against a database built from schema_v001 + migrations. It then
repeats the check for the SQLite store's table whitelist.

Run: python3 tools/check_csharp_schema.py
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import verify_database as V  # noqa: E402

WRITER = os.path.join(ROOT, "src", "Mazandasht.Application", "Import", "ImportWriter.cs")
STORE = os.path.join(ROOT, "src", "Mazandasht.Persistence", "SqliteImportStore.cs")
CONTRACT_CS = os.path.join(ROOT, "src", "Mazandasht.Application", "Import",
                           "ImportContract.cs")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL  {msg}")


def columns(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def main():
    tmp = tempfile.mkdtemp(prefix="mazandasht_cs_schema_")
    con = V.build_db(os.path.join(tmp, "chk.db"))

    all_tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    writer = open(WRITER, encoding="utf-8").read()
    checked = 0

    # 1. every Insert(table, { "col": ... }) -------------------------------
    pattern = re.compile(
        r'_store\.Insert\("(\w+)",\s*new Dictionary<string, object>\s*\{(.*?)\n\s*\}\);',
        re.S)
    for m in pattern.finditer(writer):
        table, body = m.group(1), m.group(2)
        if table not in all_tables:
            fail(f"جدول در اسکیما نیست: {table}")
            continue
        cols = columns(con, table)
        for col in re.findall(r'\{\s*"([a-z_0-9]+)"\s*,', body):
            checked += 1
            if col not in cols:
                fail(f"{table}.{col} در اسکیما نیست (نویسنده C# به ستون ناموجود می‌نویسد)")
    print(f"PASS  {checked} ستون نوشته‌شده توسط C# با اسکیما سنجیده شد" if not FAILURES
          else f"     {checked} ستون سنجیده شد")

    # 2. lookup specs ("table:column") -------------------------------------
    specs = set()
    for path in (WRITER, CONTRACT_CS):
        text = open(path, encoding="utf-8").read()
        specs.update(re.findall(r'lookup:\s*"([\w]+:[\w]+)"', text))
        specs.update(re.findall(r'Lookup\("([\w]+:[\w]+)"', text))
    # "invoices:doc_number" is intentionally virtual: one column in the
    # template must resolve across BOTH invoice tables. It is backed by
    # v_invoice_lookup (migration 004) rather than by a real table.
    VIRTUAL = {"invoices:doc_number"}
    # lookups that legitimately point at a VIEW rather than a table
    VIEWS = {"v_invoice_lookup": {"kind", "doc_number", "id", "code", "date_shamsi", "party_id"}}
    for spec in sorted(specs):
        if spec in VIRTUAL:
            views = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='view'")}
            if "v_invoice_lookup" not in views:
                fail(f"{spec} مجازی است اما v_invoice_lookup وجود ندارد")
            else:
                print(f"PASS  {spec} مجازی است و v_invoice_lookup پشت آن است")
            continue
        table, _, col = spec.partition(":")
        if table in VIEWS:
            if col not in VIEWS[table]:
                fail(f"ستون در ویو نیست: {spec}")
            else:
                print(f"PASS  {spec} روی ویو معتبر است")
            continue
        if table not in all_tables:
            fail(f"جدول مرجع در اسکیما نیست: {spec}")
            continue
        if col not in columns(con, table):
            fail(f"ستون مرجع در اسکیما نیست: {spec}")
    print(f"PASS  {len(specs)} مشخصه مرجع (table:column) معتبر است")

    # 3. tables the store whitelists --------------------------------------
    store = open(STORE, encoding="utf-8").read()
    m = re.search(r'AllowedTables\s*=\s*new HashSet<string>\(StringComparer\.Ordinal\)\s*'
                  r'\{(.*?)\};', store, re.S)
    allowed = re.findall(r'"(\w+)"', m.group(1)) if m else []
    if not allowed:
        fail("لیست AllowedTables در SqliteImportStore پیدا نشد")
    for t in allowed:
        if t not in all_tables:
            fail(f"AllowedTables شامل جدول ناموجود است: {t}")
    print(f"PASS  {len(allowed)} جدول در لیست مجاز، همه در اسکیما موجود")

    # 4. DocumentTable() targets ------------------------------------------
    doc = re.search(r'private static Tuple<string, string> DocumentTable.*?switch \(template\.Code\)'
                    r'\s*\{(.*?)\n\s*\}', writer, re.S)
    if doc:
        for table, col in re.findall(r'Tuple\.Create\("(\w+)",\s*"(\w+)"\)', doc.group(1)):
            if table not in all_tables:
                fail(f"جدول idempotency ناموجود: {table}")
            elif col not in columns(con, table):
                fail(f"ستون idempotency ناموجود: {table}.{col}")
        print("PASS  جدول/ستون‌های idempotency همگی موجودند")

    # 5. rollback plan parity: the C# plan and the Python plan describe the
    #    same deletion graph. These two drifted apart once and the result was a
    #    foreign-key failure only a real import could expose.
    import import_engine as IE
    plan_src = open(os.path.join(ROOT, "src", "Mazandasht.Application", "Import",
                                 "ImportRunner.cs"), encoding="utf-8").read()
    # The switch body contains nested braces (new[] { ... }), so a non-greedy
    # match to the first '}' truncates it. Anchor on the method's own closing
    # brace: the line that starts with exactly 8 spaces and '}'.
    block = re.search(r'private static IReadOnlyList<Tuple<string, string, string>> '
                      r'RollbackPlan.*?switch \(templateCode\)\s*\{(.*?)\n        \}',
                      plan_src, re.S)
    if not block:
        fail("RollbackPlan در ImportRunner.cs پیدا نشد")
    else:
        cs_plans = {}
        for m in re.finditer(r'case "(\w+)":(.*?)(?=case "|default:)', block.group(1), re.S):
            # the third argument is either (string)null or "tableName"
            steps = re.findall(
                r'Tuple\.Create\("(\w+)",\s*"(\w+)",\s*(?:\(string\)null|"(\w+)")',
                m.group(2))
            cs_plans[m.group(1)] = [(t, c, (p or None)) for t, c, p in steps]
        # Single("x") helper form
        for m in re.finditer(r'case "(\w+)": return Single\("(\w+)"\);', block.group(1)):
            cs_plans[m.group(1)] = [(m.group(2), "id", None)]

        py_plans = IE.ROLLBACK_PLAN
        mismatched = []
        for code in sorted(set(py_plans) | set(cs_plans)):
            py = [(t, c, p) for t, c, p in py_plans.get(code, [])]
            cs = cs_plans.get(code, [])
            if py != cs:
                mismatched.append(f"{code}: C#={cs} PY={py}")
        for m in mismatched:
            fail("طرح برگشت یکی نیست — " + m)
        if not mismatched:
            print(f"PASS  طرح برگشت {len(py_plans)} قالب در C# و Python یکسان است")

    con.close()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} مورد — پورت C# به ستونی اشاره می‌کند که وجود ندارد")
        return 1
    print("PASS  هر ستون و جدولی که پورت C# لمس می‌کند در اسکیما وجود دارد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
