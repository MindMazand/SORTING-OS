#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — dashboard parity: Python reference vs the C# shipping copy.

WHY THIS EXISTS

The nineteen dashboard KPIs exist twice, on purpose:

  agents/A_dashboard_queries.py      the Python reference, PROVEN by execution
  src/.../SqliteDashboardStore.cs    the C# that actually ships

Two implementations of "today's sales" will disagree the moment one is edited.
When they disagree, nobody can tell which number on the owner's screen is wrong
— and a wrong number on a financial dashboard is worse than no number.

So the SQL is compared mechanically. Not the C# syntax, the SQL semantics:
every SQL statement in the Python file must have a counterpart in the C# file
with the same normalised text.

    python3 tools/check_dashboard_parity.py

What this does NOT prove: that the C# compiles, or that its decimal handling is
right. Those need the Windows toolchain. This gate only stops silent drift.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_FILE = os.path.join(ROOT, "agents", "A_dashboard_queries.py")
CS_FILE = os.path.join(ROOT, "src", "Mazandasht.Persistence",
                       "SqliteDashboardStore.cs")

# Tokens that are equivalent across the two languages and must not count as a
# difference: the parameter placeholder differs because ADO.NET needs @d.
EQUIV = [
    (re.compile(r"@d\b"), "?"),
    (re.compile(r"@dir\b"), "?"),
]


def normalise(sql):
    """Fold whitespace, quote style, and parameter syntax to one canonical form."""
    s = sql
    for pat, repl in EQUIV:
        s = pat.sub(repl, s)
    # C# string concatenation leaves a space before/after; SQL does not care.
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    # Trailing semicolons are noise.
    s = s.rstrip(";").strip()
    return s.lower()


def _compute_body(text):
    """The `compute()` function only.

    The tests at the bottom of the reference file contain SQL too (INSERT,
    SELECT id ...), and those are fixtures, not KPIs. Comparing them would
    report permanent false failures. Scope the comparison to what actually
    produces dashboard numbers.
    """
    start = text.find("def compute(")
    if start < 0:
        raise SystemExit("FAIL  تابع compute در فایل پایتون پیدا نشد")
    end = text.find("\nKPI_ORDER", start)
    if end < 0:
        end = len(text)
    return text[start:end]


def py_statements():
    """Every SQL string literal inside compute() in the Python reference."""
    with open(PY_FILE, encoding="utf-8") as fh:
        full = fh.read()
    body = _compute_body(full)
    out = []
    # A literal is one or more adjacent "..." fragments inside a call; the
    # reference file uses implicit concatenation exactly as a human would.
    # Collect runs of adjacent string literals that contain SELECT.
    offset = full.count("\n", 0, full.find(body))
    for m in re.finditer(r'((?:"(?:[^"\\]|\\.)*"\s*)+)', body):
        run = m.group(1)
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', run)
        joined = "".join(parts)
        if "select" in joined.lower():
            out.append((normalise(joined),
                        offset + body.count("\n", 0, m.start()) + 1))
    return out


def cs_statements():
    """Every SQL string literal in the C# implementation."""
    with open(CS_FILE, encoding="utf-8") as fh:
        text = fh.read()
    out = []
    for m in re.finditer(r'((?:"(?:[^"\\]|\\.)*"\s*\+?\s*){1,})', text):
        run = m.group(1)
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', run)
        joined = "".join(parts)
        if "select" in joined.lower():
            out.append((normalise(joined), text.count("\n", 0, m.start()) + 1))
    return out


def main():
    for path in (PY_FILE, CS_FILE):
        if not os.path.exists(path):
            print("FAIL  فایل موجود نیست: %s" % os.path.relpath(path, ROOT))
            return 1

    py_sql = py_statements()
    cs_sql = cs_statements()

    py_set = {}
    for sql, line in py_sql:
        py_set.setdefault(sql, line)
    cs_set = {}
    for sql, line in cs_sql:
        cs_set.setdefault(sql, line)

    print("کوئری‌های پایتون: %d یکتا از %d" % (len(py_set), len(py_sql)))
    print("کوئری‌های C#    : %d یکتا از %d" % (len(cs_set), len(cs_sql)))

    missing = sorted(set(py_set) - set(cs_set))
    extra = sorted(set(cs_set) - set(py_set))

    ok = True
    for sql in missing:
        ok = False
        print("ERROR  در C# نیست (پایتون خط %d): %s" % (py_set[sql], sql[:110]))
    for sql in extra:
        ok = False
        print("ERROR  در پایتون نیست (C# خط %d): %s" % (cs_set[sql], sql[:110]))

    print()
    if not ok:
        print("FAIL  SQL داشبورد بین پایتون و C# یکی نیست")
        return 1
    print("PASS  هر %d کوئری داشبورد در هر دو زبان یکسان است" % len(py_set))
    return 0


if __name__ == "__main__":
    sys.exit(main())
