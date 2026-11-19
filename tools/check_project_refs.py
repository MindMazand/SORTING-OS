#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — prove every C# namespace used is actually reachable.

A missing <ProjectReference> does not fail a test; it fails the BUILD, on the
owner's machine, after the file has already been "finished". This script maps
each project's using directives to the assembly that defines them and checks
the reference graph and for cycles.

Run: python3 tools/check_project_refs.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

# Namespace -> project that defines it (by our own naming convention).
OWN = {
    "Mazandasht.Domain": "Mazandasht.Domain",
    "Mazandasht.Application": "Mazandasht.Application",
    "Mazandasht.Infrastructure": "Mazandasht.Infrastructure",
    "Mazandasht.Persistence": "Mazandasht.Persistence",
    "Mazandasht.Presentation": "Mazandasht.Presentation",
    "Mazandasht.Tests": "Mazandasht.Tests",
}

# Third-party / BCL namespaces that need a PackageReference or nothing at all.
EXTERNAL = {
    "System", "System.Collections.Generic", "System.Linq", "System.IO",
    "System.Text", "System.Globalization", "System.Data.SQLite",
    "System.Security.Cryptography", "System.IO.Compression", "System.Xml.Linq",
    "System.Threading", "System.Threading.Tasks", "System.ComponentModel",
    "System.Windows", "System.Windows.Controls", "System.Windows.Media",
    "System.Windows.Input", "System.Windows.Data", "Xunit",
}

FAILURES = []


def fail(m):
    FAILURES.append(m)
    print(f"FAIL  {m}")


def main():
    projects = {}
    for name in os.listdir(SRC):
        d = os.path.join(SRC, name)
        if not os.path.isdir(d):
            continue
        csproj = os.path.join(d, name + ".csproj")
        if not os.path.isfile(csproj):
            continue
        text = open(csproj, encoding="utf-8").read()
        refs = set()
        for m in re.finditer(r'ProjectReference\s+Include="([^"]+)"', text):
            # csproj paths are Windows-style even on Linux; basename() would
            # return the whole string, which made every reference look missing.
            refs.add(m.group(1).replace("\\", "/").split("/")[-1].replace(".csproj", ""))
        usings = set()
        for base, _, files in os.walk(d):
            for f in files:
                if not f.endswith(".cs"):
                    continue
                body = open(os.path.join(base, f), encoding="utf-8").read()
                for m in re.finditer(r'^using\s+(Mazandasht[\w.]*)\s*;', body, re.M):
                    ns = m.group(1)
                    for prefix, proj in OWN.items():
                        if ns == prefix or ns.startswith(prefix + "."):
                            usings.add(proj)
                            break
        projects[name] = {"refs": refs, "uses": usings}

    # 1. every used project is referenced (or is the project itself)
    for name, info in sorted(projects.items()):
        for used in sorted(info["uses"]):
            if used == name:
                continue
            if used not in info["refs"]:
                fail(f"{name} از {used} استفاده می‌کند اما ارجاع نداده است")

    # 2. declared references that are never used
    for name, info in sorted(projects.items()):
        for ref in sorted(info["refs"]):
            if ref not in info["uses"]:
                print(f"NOTE  {name} به {ref} ارجاع داده اما استفاده نمی‌کند")

    # 3. cycles
    def visit(node, stack):
        if node in stack:
            fail("چرخه ارجاع: " + " -> ".join(stack[stack.index(node):] + [node]))
            return
        stack.append(node)
        for ref in projects.get(node, {}).get("refs", ()):
            if ref in projects:
                visit(ref, stack)
        stack.pop()

    for name in projects:
        visit(name, [])

    print(f"\nPASS  {len(projects)} پروژه، گراف ارجاع کامل و بی‌چرخه"
          if not FAILURES else f"\n{len(FAILURES)} مورد")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
