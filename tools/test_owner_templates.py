#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the owner's REAL workbooks, not fixtures we wrote ourselves.

Every other test in this repository builds its own .xlsx. That is unavoidable
for exercising rules, and it is also a trap: a fixture encodes what we BELIEVE
the owner's file looks like. Two assumptions in this project had already
hardened into law that way:

  * that `داده‌ها` carries TWO header rows, English then Persian — the real
    files carry ONE, in Persian, and the English row lives in `فرهنگ داده`.
    Importing the owner's own 01_Parties.xlsx failed with "required headers are
    missing" while every column was present and correctly labelled.
  * that the sales invoice column is called «کد محصوله». It is «کد محموله».
    That was a typo of ours that no fixture could ever have caught.

The 11 files in tests/fixtures/owner_templates/ were downloaded from the
owner's Drive ("Templates" folder, 2026-11-16) and are kept as the authority.
If this test and the contract disagree, the CONTRACT is wrong.

    python3 tools/test_owner_templates.py
"""
import glob
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_contract as C          # noqa: E402
import import_engine as E            # noqa: E402
import import_parser as P            # noqa: E402
import verify_database as V          # noqa: E402
from xlsx_io import Workbook, write_workbook  # noqa: E402

build_db = V.build_db


def _raw_grid(path):
    """Read every cell as text so a rewritten file keeps its exact layout."""
    wb = Workbook(path)
    grid = {}
    for name in wb._sheet_paths:
        sh = wb.sheet(name)
        rows = []
        for r in range(1, sh.max_row + 1):
            rows.append(sh.row_values(r))
        grid[name] = rows
    wb.close()
    return grid

FIXTURES = os.path.join(ROOT, "tests", "fixtures", "owner_templates")


def main():
    files = sorted(glob.glob(os.path.join(FIXTURES, "*.xlsx")))
    if len(files) != 11:
        print(f"FAIL  انتظار ۱۱ قالب مالک، {len(files)} فایل پیدا شد")
        return 1

    failures = []
    print("قالب‌های واقعی مالک — تشخیص، نگاشت و تطبیق نام ستون‌ها")
    print("=" * 66)

    for path in files:
        name = os.path.basename(path)
        expected = {
            "01_Parties.xlsx": "PARTIES",
            "02_Products.xlsx": "PRODUCTS",
            "03_Weighing_In.xlsx": "WEIGHING_IN",
            "04_Purchase_Invoices.xlsx": "PURCHASE_INVOICES",
            "05_Sales_Invoices.xlsx": "SALES_INVOICES",
            "06_Sorting.xlsx": "SORTING",
            "07_Basket_Movements.xlsx": "BASKET_MOVEMENTS",
            "08_Bank_Transactions.xlsx": "BANK_TRANSACTIONS",
            "09_Cheques.xlsx": "CHEQUES",
            "10_Settlements.xlsx": "SETTLEMENTS",
            "11_Partnership.xlsx": "PARTNERSHIP",
        }[name]

        result = P.parse_file(path)

        if result.template is None:
            failures.append(f"{name}: شناسایی نشد — {result.file_errors}")
            print(f"FAIL  {name:26} شناسایی نشد")
            continue
        if result.template.code != expected:
            failures.append(
                f"{name}: به‌عنوان {result.template.code} شناسایی شد، انتظار {expected}")
            print(f"FAIL  {name:26} شناسایی اشتباه")
            continue
        if result.file_errors:
            failures.append(f"{name}: {result.file_errors}")
            print(f"FAIL  {name:26} {result.file_errors[0][:60]}")
            continue

        # Every required field must be mapped, and no header may go unmatched:
        # an unmatched header on the owner's own template means the contract
        # has drifted from the file they will actually import.
        missing = [f.name_fa for f in result.template.required
                   if f.name_en not in result.header_map]
        if missing:
            failures.append(f"{name}: ستون الزامی نگاشت نشد {missing}")
            print(f"FAIL  {name:26} نگاشت ناقص")
            continue
        if result.unmatched_headers:
            failures.append(
                f"{name}: سرستون ناشناخته {result.unmatched_headers}")
            print(f"FAIL  {name:26} سرستون ناشناخته")
            continue

        mapped = len(result.header_map)
        total = len(result.template.fields)
        print(f"OK    {name:26} {expected:18} {mapped}/{total} ستون، "
              f"{result.ignored_blank_rows} ردیف خالی")

    # The header text itself must match the contract exactly, so a future typo
    # in either place is caught by name rather than by import failure.
    print()
    for path in files:
        name = os.path.basename(path)
        wb = Workbook(path)
        sh = wb.sheet("داده‌ها")
        real = [sh.cell(1, c).text.strip()
                for c in range(1, sh.max_col + 1)]
        wb.close()
        best, score = None, 0
        for tpl in C.ALL.values():
            fa = {f.name_fa for f in tpl.fields}
            hit = sum(1 for h in real if h in fa)
            if hit > score:
                best, score = tpl, hit
        unknown = [h for h in real if h and h not in {f.name_fa for f in best.fields}]
        unused = [f.name_fa for f in best.fields if f.name_fa not in real]
        if unknown:
            failures.append(f"{name}: سرستون واقعی «{unknown}» در قرارداد نیست")
        if unused:
            failures.append(f"{name}: قرارداد ستون «{unused}» دارد که در فایل نیست")

    # ---------------------------------------------------------------------
    # And finally: take the owner's OWN file, append rows to the sheet the way
    # the owner would, and import it against a real database. This is the only
    # test where the bytes being read are the owner's layout end to end.
    # ---------------------------------------------------------------------
    print()
    tmp = tempfile.mkdtemp(prefix="owner_fill_")
    con = build_db(os.path.join(tmp, "owner.db"))
    con.execute("PRAGMA foreign_keys = ON")

    def filled(template_file, rows):
        """Copy the real workbook and append data rows to `داده‌ها`."""
        wb = Workbook(os.path.join(FIXTURES, template_file))
        wb.close()
        grid = _raw_grid(os.path.join(FIXTURES, template_file))
        grid["داده‌ها"] = grid["داده‌ها"] + rows
        path = os.path.join(tmp, template_file)
        write_workbook(path, grid)
        return path

    steps = [
        ("01_Parties.xlsx", [
            ["C001", "باغدار احمدی", "PERSON", "احمد احمدی", "0012345678",
             "411111111111", "09111234567", "", "نوشهر", ""],
            ["C002", "شرکت سبز مازند", "COMPANY", "شرکت سبز مازند", "10320000001",
             "", "", "", "آمل", ""],
        ]),
        ("02_Products.xlsx", [
            ["PB-OWN", "پرتقال مالک", "PG-CITRUS", "U-KG", "تامسون", "1", ""],
        ]),
        ("03_Weighing_In.xlsx", [
            ["WT-OWN", "1403/05/01", "", "IN", "C001", "PB-OWN", "W01",
             "5200.500", "", "5200.500", "40", "PK-BASKET", "", ""],
        ]),
        ("04_Purchase_Invoices.xlsx", [
            ["PI-OWN", "1403/05/01", "C001", "WT-OWN", "PB-OWN", "5200.500",
             "85000", "0", "0", "0", "0", ""],
        ]),
    ]
    for template_file, rows in steps:
        path = filled(template_file, rows)
        out = E.import_file(con, path)
        if out.errors or out.created != len(rows):
            failures.append(f"{template_file}: واردسازی واقعی — {out.errors}")
            print(f"FAIL  واردسازی {template_file}: {out.errors}")
        else:
            print(f"OK    واردسازی واقعی {template_file:26} {out.created} سند")

    if not failures:
        lot = con.execute("SELECT quantity_grams FROM lots").fetchone()
        inv = con.execute(
            "SELECT weigh_ticket_id IS NOT NULL FROM purchase_invoices").fetchone()
        assert lot and lot[0] == 5200500, lot
        assert inv and inv[0] == 1, inv
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        print(f"OK    زنجیره روی فایل‌های واقعی: lot {lot[0]} گرم، "
              "فاکتور به باسکول وصل، FK سالم")
    # ---------------------------------------------------------------------
    # Scale, and rollback precision, on the owner's real template shape.
    # 2,000 rows is well past anything the owner will type by hand, and it
    # checks the two properties that matter at size: rollback deletes EXACTLY
    # the batch's rows (no seed row, no row from another batch) and the
    # database still passes foreign_key_check afterwards.
    # ---------------------------------------------------------------------
    import time
    big_tmp = tempfile.mkdtemp(prefix="owner_scale_")
    grid = _raw_grid(os.path.join(FIXTURES, "01_Parties.xlsx"))
    n_rows = 2000
    grid["داده‌ها"] = grid["داده‌ها"] + [
        [f"S{i:05d}", f"شخص {i}", "PERSON", f"نام {i}", f"00{i:08d}",
         "", "", "", "نوشهر", ""] for i in range(1, n_rows + 1)]
    big = os.path.join(big_tmp, "01_Parties_big.xlsx")
    write_workbook(big, grid)

    con2 = build_db(os.path.join(big_tmp, "scale.db"))
    con2.execute("PRAGMA foreign_keys = ON")
    seed_codes = [r[0] for r in con2.execute(
        "SELECT code FROM parties ORDER BY code")]
    t0 = time.time()
    out = E.import_file(con2, big)
    elapsed = time.time() - t0
    if out.created != n_rows or out.errors:
        failures.append(f"مقیاس: {out.created}/{n_rows} سند، {out.errors[:2]}")
    else:
        print(f"OK    مقیاس: {out.created} شخص در {elapsed:.2f}s "
              f"({out.created / elapsed:.0f} ردیف/ثانیه)")

    rb = E.rollback_batch(con2, out.batch_id)
    left = con2.execute(
        "SELECT COUNT(*) FROM parties WHERE code LIKE 'S%'").fetchone()[0]
    after_codes = [r[0] for r in con2.execute(
        "SELECT code FROM parties ORDER BY code")]
    if left != 0:
        failures.append(f"برگشت: {left} ردیف از دسته باقی ماند")
    if after_codes != seed_codes:
        failures.append("برگشت ردیف‌های غیرِ دسته را هم دست زد")
    if rb.failed:
        failures.append(f"برگشت: {rb.failed} خطا")
    else:
        print(f"OK    برگشت دقیق: صفر ردیف باقی، داده پایه دست‌نخورده")
    if con2.execute("PRAGMA foreign_key_check").fetchall() != []:
        failures.append("پس از برگشت، FK شکسته است")
    con2.close()

    con.close()

    print()
    if failures:
        for f in failures:
            print("FAIL  " + f)
        print(f"\n{len(failures)} اختلاف بین قالب واقعی مالک و قرارداد")
        return 1
    print("PASS  ۱۱ قالب واقعی مالک با قرارداد می‌خوانند")
    return 0


if __name__ == "__main__":
    sys.exit(main())
