#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — run every check that can run without .NET.

This is the gate before any claim of "done". Each step prints its own
evidence; if one fails the exit code is non-zero and nothing should be
reported as complete.

    python3 tools/verify_all.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("اسکیما و داده", ["tools/verify_database.py"]),
    ("موتور واردسازی (Python)", ["tools/test_import.py"]),
    ("زنجیره ۱۱ قالب سرتاسری", ["tools/test_chain.py"]),
    ("قالب‌های واقعی مالک (فایل‌های Drive)", ["tools/test_owner_templates.py"]),
    ("بردارهای طلایی در برابر اجرای واقعی", ["tools/check_golden_vectors.py"]),
    ("قرارداد C# ↔ Python", ["tools/check_contract_parity.py"]),
    ("ستون‌های C# ↔ اسکیما", ["tools/check_csharp_schema.py"]),
    ("ستون‌های قرارداد ↔ اسکیما", ["tools/check_contract_schema.py"]),
    ("گراف ارجاع پروژه‌ها", ["tools/check_project_refs.py"]),
    # --- dashboard round: the UI layer, which has no compiler here ---
    ("نوزده KPI داشبورد روی اسکیمای واقعی", ["agents/A_dashboard_queries.py"]),
    ("SQL داشبورد: پایتون ↔ C# یکسان", ["tools/check_dashboard_parity.py"]),
    ("اعداد SQL استخراج‌شده از C#", ["tools/test_dashboard_cs_sql.py"]),
    ("سالم‌بودن XAML (بدون کامپایلر)", ["tools/check_xaml.py", "--strict"]),
    # --- import centre round ---
    ("دامنه بررسی تأیید در برگشت دسته", ["tools/test_import_batch_scope.py"]),
    ("جریان مرکز واردسازی سرتاسری", ["tools/test_import_centre_flow.py"]),
    ("ردپای حسابرسی (فصل ۱۰)", ["tools/test_audit_trail.py"]),
    ("کوئری‌های صفحه ابزارها", ["tools/test_tools_probe.py"]),
    ("مهاجرت ۰۰۶ — ستون پولی nullable", ["tools/test_migration_006.py"]),
    ("شش گزارش مالی", ["tools/test_reports.py"]),
]


def main():
    failures = []
    for label, cmd in STEPS:
        print("=" * 70)
        print("» " + label)
        print("=" * 70)
        result = subprocess.run([sys.executable] + cmd, cwd=ROOT)
        if result.returncode != 0:
            failures.append(label)

    print("=" * 70)
    if failures:
        print("شکست در: " + " · ".join(failures))
        return 1
    print("همه بررسی‌های ممکن بدون .NET با موفقیت گذشت.")
    print("توجه: تست‌های xUnit و build پروژه‌های C# اینجا اجرا نمی‌شوند —")
    print("آن‌ها به Windows 8.1+ x64 با SDK نیاز دارند (reports/BASELINE.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
