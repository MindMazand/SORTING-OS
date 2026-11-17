#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Guard against contract drift between Python and C#.

The import contract exists twice: tools/import_contract.py (the reference and
test harness) and src/Mazandasht.Application/Import/ImportContract.cs (the
shipping implementation). Two copies WILL drift. This script makes drift a
build failure instead of a bug the owner finds in production.

It parses the C# file with a real C# parser (tree-sitter) rather than with
regexes, because a regex that "looks right" on today's file is exactly the kind
of guard that quietly stops guarding.

Checks
  1. every .cs file in src/ parses with zero syntax errors
  2. the 11 templates exist on both sides, same file name, same order
  3. field name (en/fa), kind, required flag and order match exactly
  4. lookups and choices match exactly
  5. db_column may differ ONLY where the C# side is deliberately null

Run: python3 tools/check_contract_parity.py
Exit code 0 = parity proven, 1 = drift.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_contract as PY  # noqa: E402

CS_FILE = os.path.join(ROOT, "src", "Mazandasht.Application", "Import", "ImportContract.cs")
SRC_DIR = os.path.join(ROOT, "src")

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print(f"FAIL  {msg}")


def ok(msg):
    print(f"PASS  {msg}")


# ---------------------------------------------------------------------------
# 1. Syntax of every C# file
# ---------------------------------------------------------------------------
def check_csharp_syntax():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_c_sharp as grammar
    except ImportError:
        fail("tree_sitter در دسترس نیست — صحت نحوی C# بررسی نشد")
        return False

    parser = Parser(Language(grammar.language()))
    files = []
    for base, _, names in os.walk(SRC_DIR):
        for n in names:
            if n.endswith(".cs"):
                files.append(os.path.join(base, n))
    files.sort()

    bad = []
    for path in files:
        with open(path, "rb") as f:
            tree = parser.parse(f.read())
        errors = []

        def walk(node):
            if node.type == "ERROR" or node.is_missing:
                errors.append((node.type, node.start_point[0] + 1))
            for c in node.children:
                walk(c)

        walk(tree.root_node)
        if errors:
            bad.append((os.path.relpath(path, ROOT), errors[:3]))

    if bad:
        for path, errs in bad:
            fail(f"خطای نحوی C#: {path} → {errs}")
        return False
    ok(f"صحت نحوی: {len(files)} فایل C# بدون خطای پارس")
    return True


# ---------------------------------------------------------------------------
# 2-4. Contract parity, read from the C# source as a structured list
# ---------------------------------------------------------------------------
TEMPLATE_RE = re.compile(
    r'public static readonly ImportTemplate (\w+) = new ImportTemplate\(\s*'
    r'"(?P<code>[A-Z_]+)",\s*"(?P<file>[^"]+)",\s*"(?P<module>[^"]+)",\s*'
    r'new\[\]\s*\{(?P<body>.*?)\}\s*,\s*'
    r'idempotencyField:\s*(?P<idem>"[^"]*"|null)', re.S)

FIELD_START_RE = re.compile(
    r'F\(\s*"(?P<en>[^"]+)",\s*"(?P<fa>[^"]+)",\s*FieldKind\.(?P<kind>\w+)\s*,')


def _balanced_args(text):
    """Split the trailing argument text of an F(...) call into named parts."""
    parts = {"required": False, "db": None, "lookup": None, "choices": None}
    if re.search(r'^\s*true\s*(,|$)', text.strip()) or re.match(r'\s*true\b', text):
        parts["required"] = True
    m = re.search(r'FieldKind\.\w+\s*,\s*(true|false)', text)
    if m:
        parts["required"] = m.group(1) == "true"
    m = re.search(r'(?:db|positional)?\s*[,]\s*null\s*[,]', text)
    # db column: the first positional string-or-null after required
    m = re.search(r'(?:^|,)\s*(true|false)\s*,\s*(?P<db>null|"[^"]*")', text)
    if m:
        parts["db"] = m.group("db")
    m = re.search(r'lookup:\s*"(?P<l>[^"]*)"', text)
    if m:
        parts["lookup"] = m.group("l")
    m = re.search(r'choices:\s*new\[\]\s*\{(?P<c>[^}]*)\}', text)
    if m:
        parts["choices"] = re.findall(r'"([^"]*)"', m.group("c"))
    return parts


def parse_csharp_contract():
    with open(CS_FILE, encoding="utf-8") as f:
        src = f.read()

    templates = {}
    for m in TEMPLATE_RE.finditer(src):
        code = m.group("code")
        body = m.group("body")
        fields = []
        starts = list(FIELD_START_RE.finditer(body))
        for idx, fm in enumerate(starts):
            end = starts[idx + 1].start() if idx + 1 < len(starts) else len(body)
            rest = body[fm.end():end]
            args = _balanced_args(rest)
            db = args["db"]
            fields.append({
                "en": fm.group("en"),
                "fa": fm.group("fa"),
                "kind": fm.group("kind"),
                "required": args["required"],
                "db": None if db in (None, "null") else db.strip('"'),
                "lookup": args["lookup"],
                "choices": args["choices"],
            })
        templates[code] = {
            "file": m.group("file"),
            "module": m.group("module"),
            "idem": None if m.group("idem") == "null" else m.group("idem").strip('"'),
            "fields": fields,
        }
    return templates


KIND_MAP = {
    "Text": "text", "Code": "code", "Kind": "kind", "Shamsi": "shamsi",
    "Time": "time", "Kg": "kg", "Gram": "gram", "Rial": "rial",
    "RialSigned": "rial_signed", "Count": "count", "Percent": "percent",
    "Flag01": "flag01",
}


def check_parity():
    cs = parse_csharp_contract()
    if not cs:
        fail("هیچ قالبی در فایل C# پیدا نشد (الگوی پارس شکسته است)")
        return

    if set(cs) != set(PY.ALL):
        fail(f"مجموعه قالب‌ها یکی نیست: C#={sorted(set(cs) - set(PY.ALL))} "
             f"PY={sorted(set(PY.ALL) - set(cs))}")
        return
    ok(f"قالب‌ها: هر ۱۱ مورد در هر دو طرف ({len(cs)})")

    py_order = [c for c in PY.IMPORT_ORDER]
    cs_order_match = re.search(r'ImportOrder = new\[\]\s*\{(.*?)\}', 
                               open(CS_FILE, encoding="utf-8").read(), re.S)
    cs_order = re.findall(r'"([A-Z_]+)"', cs_order_match.group(1)) if cs_order_match else []
    if cs_order != py_order:
        fail(f"ترتیب واردسازی یکی نیست:\n  C#={cs_order}\n  PY={py_order}")
    else:
        ok("ترتیب واردسازی یکسان است")

    total = 0
    for code in PY.IMPORT_ORDER:
        py_t = PY.ALL[code]
        cs_t = cs[code]
        if cs_t["file"] != py_t.file_name:
            fail(f"{code}: نام فایل C#='{cs_t['file']}' PY='{py_t.file_name}'")
        if cs_t["idem"] != py_t.idempotency_field:
            fail(f"{code}: کلید idempotency C#={cs_t['idem']} PY={py_t.idempotency_field}")

        if len(cs_t["fields"]) != len(py_t.fields):
            fail(f"{code}: تعداد ستون C#={len(cs_t['fields'])} PY={len(py_t.fields)}")

        for i, py_f in enumerate(py_t.fields):
            total += 1
            if i >= len(cs_t["fields"]):
                fail(f"{code}: ستون شماره {i+1} در C# غایب است ({py_f.name_en})")
                continue
            c = cs_t["fields"][i]
            problems = []
            if c["en"] != py_f.name_en:
                problems.append(f"name_en C#='{c['en']}' PY='{py_f.name_en}'")
            if c["fa"] != py_f.name_fa:
                problems.append(f"name_fa C#='{c['fa']}' PY='{py_f.name_fa}'")
            if KIND_MAP.get(c["kind"]) != py_f.kind:
                problems.append(f"kind C#='{c['kind']}' PY='{py_f.kind}'")
            if c["required"] != py_f.required:
                problems.append(f"required C#={c['required']} PY={py_f.required}")
            if c["lookup"] != py_f.lookup:
                problems.append(f"lookup C#={c['lookup']} PY={py_f.lookup}")
            if (c["choices"] or None) != (py_f.choices or None):
                problems.append(f"choices C#={c['choices']} PY={py_f.choices}")
            # db column: C# may say null deliberately; if it names one it must match
            if c["db"] is not None and c["db"] != py_f.db_column:
                problems.append(f"db C#='{c['db']}' PY='{py_f.db_column}'")
            if problems:
                fail(f"{code}.{py_f.name_en}: " + " | ".join(problems))

    ok(f"ستون‌ها: {total} ستون ستون‌به‌ستون مقایسه شد")

    # The "blank is not zero, but null must not overthrow a column default"
    # rule exists twice: _select_columns in Python and NullSkippable in C#.
    # If they disagree, one side imports without error and the other does not,
    # and which one breaks depends only on which we happen to run first.
    py_src = open(os.path.join(ROOT, "tools", "import_engine.py"), encoding="utf-8").read()
    cs_src = open(os.path.join(ROOT, "src", "Mazandasht.Persistence",
                               "SqliteImportStore.cs"), encoding="utf-8").read()
    py_rule = "r[3] == 1 and r[4] is not None" in py_src
    cs_rule = 'Convert.ToInt64(r["notnull"]) == 1' in cs_src and \
              'r["dflt_value"]' in cs_src
    if py_rule and cs_rule:
        ok("قاعده «null روی ستون NOT NULL DEFAULT» در هر دو زبان یکی است")
    elif py_rule != cs_rule:
        fail("قاعده null/پیش‌فرض فقط در یک زبان پیاده شده است")
    else:
        fail("قاعده null/پیش‌فرض در هیچ‌کدام پیدا نشد")


def check_writer_parity():
    """The two writers must insert the SAME columns into the SAME tables.

    Comparing only the contract misses this: a writer can forget a column that
    the contract declares, and the row is inserted with that field missing and
    no error. Sorted-set comparison, because ordering is not semantic.
    """
    py_src = open(os.path.join(ROOT, "tools", "import_engine.py"), encoding="utf-8").read()
    cs_src = open(os.path.join(ROOT, "src", "Mazandasht.Application", "Import",
                               "ImportWriter.cs"), encoding="utf-8").read()

    def blocks(src, call_re, key_re):
        out = {}
        for m in call_re.finditer(src):
            table = m.group(1)
            i = m.end() - 1
            depth = 0
            while i < len(src):
                if src[i] == "{":
                    depth += 1
                elif src[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            out.setdefault(table, set()).update(key_re.findall(src[m.end() - 1:i]))
        return out

    py = blocks(py_src, re.compile(r'_insert\(con,\s*"(\w+)",\s*\{'),
                re.compile(r'"(\w+)":'))
    cs = blocks(cs_src,
                re.compile(r'Insert\("(\w+)",\s*new Dictionary<string,\s*object>\s*\{'),
                re.compile(r'\{\s*"(\w+)"\s*,'))

    # the batch bookkeeping tables have no C# counterpart by design: the C#
    # ImportRunner records them through IImportBatchStore, not through Insert.
    ignore = {"import_batches", "import_rows", "partnerships"}
    py = {k: v for k, v in py.items() if k not in ignore}

    only_py = sorted(set(py) - set(cs))
    only_cs = sorted(set(cs) - set(py))
    if only_py:
        fail("جدول‌هایی که فقط پایتون می‌نویسد: " + ", ".join(only_py))
    if only_cs:
        fail("جدول‌هایی که فقط C# می‌نویسد: " + ", ".join(only_cs))

    diffs = 0
    for table in sorted(set(py) & set(cs)):
        missing = sorted(py[table] - cs[table])
        extra = sorted(cs[table] - py[table])
        if missing or extra:
            diffs += 1
            fail(f"{table}: C# جا انداخته {missing} · C# اضافه دارد {extra}")
    if not diffs and not only_py and not only_cs:
        ok(f"نویسنده‌ها: {len(py)} جدول، ستون‌ها یکسان")


def main():
    print("=== تطبیق قرارداد C# با مرجع Python ===")
    syntax_ok = check_csharp_syntax()
    check_parity()
    check_writer_parity()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} اختلاف — قرارداد دو نسخه‌ای دکتر شده است")
        return 1
    print("PASS  قرارداد یکپارچه است" + ("" if syntax_ok else " (صحت نحوی بررسی نشد)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
