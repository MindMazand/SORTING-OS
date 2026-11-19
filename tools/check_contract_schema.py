#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the import contract's column names must exist in the schema.

Why this file exists: 24 of 129 contract fields pointed at columns that do not
exist. Nothing noticed, because the writer silently dropped unknown keys. The
result on the owner's machine would have been:

    a partnership event imported with NO partner attached, no error

`status` on the import batch said IMPORTED. The row was there. The link was not.
A silent NULL is the most expensive kind of bug in an accounting system, because
nothing ever fails — the numbers are simply wrong.

This guard reads `db_column` from every one of the 11 templates and checks it
against a database built from the real migrations.

    python3 tools/check_contract_schema.py
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_contract as C          # noqa: E402
import import_engine as E            # noqa: E402
import verify_database as V          # noqa: E402

# Where each template's fields actually land. Most templates write ONE row per
# source row, but an invoice writes a header plus a line, and sorting writes a
# batch plus inputs plus outputs. Without this map the check would look for
# `rate_rial_per_kg` on `purchase_invoices` and call a correct design a bug —
# which is exactly what it did on its first run, 23 times.
FIELD_TARGETS = {
    "PURCHASE_INVOICES": {
        "header": ["SourceInvoiceCode", "DateShamsi", "SupplierCode", "WeighCode",
                   "Note"],
        "line": ["ProductCode", "PurchaseKg", "RateRialPerKg", "DiscountRial",
                 "FreightRial", "CommissionRial", "OtherAdjustmentsRial"],
        "lineTable": "purchase_invoice_lines",
    },
    "SALES_INVOICES": {
        "header": ["SourceInvoiceCode", "DateShamsi", "BuyerCode", "LotCode",
                   "Note"],
        "line": ["SortOutputCode", "ProductCode", "SaleKg", "RateRialPerKg",
                 "DiscountRial", "FreightRial", "CommissionRial", "OtherCostsRial"],
        "lineTable": "sales_invoice_lines",
    },
    "SORTING": {
        "header": ["SortDocCode", "DateShamsi", "InputLotCode", "InputWarehouseCode",
                   "InputKg", "ToleranceKg", "WasteKg", "ProcessLossKg", "Note"],
        # InputWarehouseCode has no column anywhere: the lot already carries its
        # warehouse, so a second one could contradict it. The contract declares
        # db_column=None for it, which this check skips by design.
        "line": ["OutputProductCode", "GradeCode", "PackagingCode",
                 "OutputWarehouseCode", "OutputKg", "PackageCount"],
        "lineTable": "sorting_outputs",
    },
}

FAILURES = []


def fail(msg):
    FAILURES.append(msg)
    print("FAIL  " + msg)


def main():
    path = os.path.join(tempfile.mkdtemp(prefix="mazandasht_contract_"), "c.db")
    con = V.build_db(path)

    tables = {}
    for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"):
        tables[name] = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]

    checked = 0
    for code, tpl in C.ALL.items():
        table = E.CREATES.get(code)
        if table is None:
            fail(f"{code}: قالب جدول مقصد ندارد (CREATES)")
            continue
        if table not in tables:
            fail(f"{code}: جدول {table} در اسکیما نیست")
            continue
        targets = FIELD_TARGETS.get(code)
        for f in tpl.fields:
            col = f.db_column
            if not col or col.startswith("__"):
                continue
            checked += 1
            if targets and f.name_en in targets["line"]:
                home = targets["lineTable"]
            elif targets and f.name_en in targets["header"]:
                home = table
            elif targets:
                fail(f"{code}.{f.name_en}: در هیچ‌یک از دو گروه هدر/سطر نیست — "
                     "یا نگاشت جایش مانده یا این تست به‌روز نشده")
                continue
            else:
                home = table
            if home not in tables:
                fail(f"{code}.{f.name_en}: جدول {home} در اسکیما نیست")
            elif col not in tables[home]:
                fail(f"{code}.{f.name_en}: ستون «{col}» در جدول {home} نیست")

    # A template that maps several fields onto ONE column silently overwrites
    # earlier values, which is another way to lose data without an error.
    for code, tpl in C.ALL.items():
        seen = {}
        for f in tpl.fields:
            col = f.db_column
            if not col or col.startswith("__"):
                continue
            if col in seen:
                fail(f"{code}: «{seen[col]}» و «{f.name_en}» هر دو به ستون {col} "
                     "نوشته می‌شوند؛ دومی اولی را بازنویسی می‌کند")
            seen[col] = f.name_en

    # And the reverse: a writer that names a column the contract never declares.
    # Those are invisible to parity checks that only walk the contract.
    for code, tpl in C.ALL.items():
        table = E.CREATES.get(code)
        if table not in tables:
            continue
        declared = {f.db_column for f in tpl.fields if f.db_column}
        for col in tables[table]:
            if col in ("id", "created_at") or col in declared:
                continue
            # Columns the schema fills by itself are fine; the writer is not
            # required to know them. Report only, do not fail.
            print(f"NOTE  {code}: ستون {table}.{col} توسط قرارداد پر نمی‌شود")

    # Every lookup spec the contract declares must actually resolve. A lookup
    # pointing at a table that does not exist is invisible until a real file is
    # imported; `invoices:doc_number` sat broken for two stages that way.
    VIRTUALS = {"invoices:doc_number": "v_invoice_lookup",
                "lots:code": "v_lot_lookup"}
    views = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    specs = sorted({f.lookup for t in C.ALL.values() for f in t.fields if f.lookup})
    for spec in specs:
        home = VIRTUALS.get(spec)
        if home is None:
            table, _, column = spec.partition(":")
            column = column or "code"
            home = table
        elif home == "v_invoice_lookup":
            column = "doc_number"
        else:
            column = "ref"
        if home not in views:
            fail(f"مرجع «{spec}» به {home} اشاره می‌کند که وجود ندارد")
        elif column not in [r[1] for r in con.execute(f"PRAGMA table_info({home})")]:
            fail(f"مرجع «{spec}»: ستون {column} در {home} نیست")
    if not FAILURES:
        print(f"PASS  هر {len(specs)} مرجع قرارداد در اسکیما قابل حل است")

    con.close()
    print()
    print(f"بررسی‌شده: {checked} ستون قرارداد در {len(C.ALL)} قالب")
    print()
    if FAILURES:
        print(f"{len(FAILURES)} مورد — نگاشت قرارداد با اسکیما نمی‌خواند")
        return 1
    print("PASS  نگاشت ستون‌های قرارداد با اسکیما می‌خواند")
    return 0


if __name__ == "__main__":
    sys.exit(main())
