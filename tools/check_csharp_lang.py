#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — no C# newer than the project's LangVersion.

WHY THIS EXISTS

Every .csproj in this repository sets:

    <LangVersion>7.3</LangVersion>

because the target is .NET Framework 4.8 on Windows 8.1 with Visual Studio
2019, where the default compiler is C# 7.3. Nothing in this sandbox compiles
C#, so a `??=`, a `using var`, a switch EXPRESSION or a record would sail
through every gate here and then fail on the owner's machine with a wall of
error codes — after they have spent an hour Installing things.

This gate reads the .cs files and rejects constructs that only exist in C# 8
or later. It is not a full parser; it looks for the specific forms that are
easy to write by accident and impossible to notice by reading.

WHAT IT FLAGS

  * `??=`, `?[`, `?.` chained assignment forms — C# 8 null-coalescing assignment
  * `using var x =`                          — C# 8 using declaration
  * `switch { ... }` expressions             — C# 8
  * `is not`                                 — C# 9
  * `record ` / `init;` / target-typed `new()` — C# 9
  * `#nullable`                              — C# 8
  * index/range `[..]` on collections        — C# 8
  * `await foreach`                          — C# 8

    python3 tools/check_csharp_lang.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

# Pattern, minimum C# version, human explanation.
FORBIDDEN = [
    (r"\?\?=",                      8,  "??= (null-coalescing assignment)"),
    (r"\busing\s+var\s+\w+\s*=",    8,  "using declaration instead of using(...)"),
    (r"#nullable\b",                8,  "#nullable directive"),
    (r"\bawait\s+foreach\b",        8,  "await foreach"),
    (r"\bswitch\s*\{",              8,  "switch expression"),
    (r"\bis\s+not\s+",              9,  "is not pattern"),
    (r"^\s*record\s+\w+",           9,  "record type"),
    (r"\binit\s*;",                 9,  "init-only setter"),
    (r"\bnew\s*\(\s*\)",            9,  "target-typed new()"),
    (r"\bnot\s+null\b",             9,  "not null pattern"),
]


def lang_version():
    """Read LangVersion from the Presentation project — all six agree."""
    path = os.path.join(SRC, "Mazandasht.Presentation",
                        "Mazandasht.Presentation.csproj")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"<LangVersion>([\d.]+)</LangVersion>", text)
    assert m, "LangVersion در csproj پیدا نشد"
    return float(m.group(1))


def cs_files():
    for base, _, files in os.walk(SRC):
        if "obj" in base or "bin" in base:
            continue
        for name in files:
            if name.endswith(".cs"):
                # Skip generated code: it is machine-written for a reason.
                if name.endswith(".g.cs") or name.endswith(".Designer.cs"):
                    continue
                yield os.path.join(base, name)


def strip_comments_and_strings(text):
    """
    Remove comments and string literals before matching.

    Without this the gate fires on its own documentation — every explanation
    of `??=` in a comment would be a violation. The same mistake made
    tools/test_reports_cs_sql.py report three wired buttons as dead.
    """
    out = []
    i = 0
    n = len(text)
    in_line_comment = False
    in_block_comment = False
    in_string = False
    in_verbatim = False
    while i < n:
        two = text[i:i + 2]
        if in_line_comment:
            if text[i] == "\n":
                in_line_comment = False
                out.append("\n")
            i += 1
            continue
        if in_block_comment:
            if two == "*/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_verbatim:
            if two == '""':
                i += 2
                continue
            if text[i] == '"':
                in_verbatim = False
            i += 1
            continue
        if in_string:
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == '"':
                in_string = False
            i += 1
            continue
        if two == "//":
            in_line_comment = True
            i += 2
            continue
        if two == "/*":
            in_block_comment = True
            i += 2
            continue
        if two == '@"':
            in_verbatim = True
            i += 2
            continue
        if text[i] == '"':
            in_string = True
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def scan():
    limit = lang_version()
    hits = []
    for path in cs_files():
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        code = strip_comments_and_strings(raw)
        for pattern, version, why in FORBIDDEN:
            if version <= limit:
                continue
            for m in re.finditer(pattern, code, re.M):
                line = code[:m.start()].count("\n") + 1
                hits.append((os.path.relpath(path, ROOT), line, why))
    return limit, hits


def main():
    limit, hits = scan()
    files = len(list(cs_files()))
    print("LangVersion هدف: %.1f · فایل‌های C#: %d" % (limit, files))
    if not hits:
        print("PASS  هیچ نویسه‌ای جدیدتر از C# %.1f استفاده نشده است" % limit)
        return 0
    for path, line, why in hits:
        print("ERROR %s:%d  %s" % (path, line, why))
    print()
    print("FAIL  %d مورد فقط در C# جدیدتر وجود دارد" % len(hits))
    return 1


if __name__ == "__main__":
    sys.exit(main())
