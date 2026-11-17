#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — end-to-end chain over all 11 of the owner's templates.

Every other test in this repository checks ONE template. That is how a
settlement template shipped for two stages without ever being runnable: it was
detected correctly, and detection was all anyone tested.

This runs the owner's real sequence once, in order, on a fresh database:

    01_Parties -> 02_Products -> 03_WeighingIn -> 04_PurchaseInvoices
    -> 05_SalesInvoices -> 06_Sorting -> 07_BasketMovements
    -> 08_BankTransactions -> 09_Cheques -> 10_Settlements -> 11_Partnership

and asserts that each step depends on the one before it. The codes in these
files are NOT hard-coded into the engine: later templates find earlier rows by
the code the owner typed, so if a link is broken the chain stops there.

    python3 tools/test_chain.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_contract as C          # noqa: E402
import import_engine as E            # noqa: E402
import verify_database as V          # noqa: E402
from xlsx_io import write_workbook   # noqa: E402

TMP = tempfile.mkdtemp(prefix="mazandasht_chain_")
FAILURES = []


def build(code, name, rows):
    tpl = C.ALL[code]
    grid = [[f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields]]
    grid.extend(rows)
    path = os.path.join(TMP, name)
    write_workbook(path, {"داده‌ها": grid})
    return path


def step(con, code, file_name, rows):
    """Import one file and fail loudly, naming the template."""
    path = build(code, file_name, rows)
    out = E.import_file(con, path)
    if out.errors:
        raise AssertionError(f"{file_name}: {out.errors}")
    if out.created != len(rows):
        raise AssertionError(
            f"{file_name}: {out.created} سند ساخته شد، انتظار {len(rows)}")
    print(f"  OK  {file_name:24} {out.created} سند")
    return out


def main():
    path = os.path.join(TMP, "chain.db")
    con = V.build_db(path)
    con.execute("PRAGMA foreign_keys = ON")

    print("زنجیره کامل ۱۱ قالب — به ترتیب وابستگی")
    print("=" * 62)

    # 01 — parties. Everything downstream hangs off these codes.
    step(con, "PARTIES", "01_Parties.xlsx", [
        ["C001", "باغدار احمدی", "PERSON", "احمد احمدی", "0012345678",
         "411111111111", "09111234567", "01133445566", "نوشهر", "باغدار"],
        ["C002", "شرکت سبز مازند", "COMPANY", "شرکت سبز مازند", "10320000001",
         "", "09120000000", "", "آمل", "خریدار"],
    ])

    # 02 — products. PB-ORANGE ships in the seed, so use a fresh code: the chain
    # is about linking, and a duplicate here would mask the next step.
    step(con, "PRODUCTS", "02_Products.xlsx", [
        ["PB-CHAIN", "پرتقال زنجیره", "PG-CITRUS", "U-KG", "تامسون", "1", ""],
    ])

    # 03 — the only template allowed to move stock (DEC-NEW-007).
    step(con, "WEIGHING_IN", "03_WeighingIn.xlsx", [
        # SourceDocCode, Date, Time, Direction, Party, Product, Warehouse,
        # ScaleKg, TareKg, NetKg, PackageCount, PackagingCode, Receipt, Note
        ["WT-1", "1403/05/01", "", "IN", "C001", "PB-CHAIN", "W01",
         "5200.500", "", "5200.500", "40", "PK-BASKET", "", ""],
    ])
    # `code` is the engine's internal sequence (WT0001); the code the owner
    # typed lands in doc_number/source_key. Asserting on `code` was my mistake.
    ticket = con.execute(
        "SELECT id FROM weigh_tickets WHERE doc_number='WT-1'").fetchone()
    assert ticket, "باسکول ساخته نشد"
    lot = con.execute("SELECT id, quantity_grams FROM lots").fetchone()
    assert lot is not None, "باسکول lot نساخت"
    # The sheet states NetKg 5200.500 explicitly, and the engine records what
    # the owner wrote (5200500 g) rather than recomputing it. The tare-from-
    # basket-count formula (DEC-NEW-008) applies only where the sheet leaves the
    # net blank; silently overriding a stated number would be the rounding the
    # owner forbade.
    assert lot[1] == 5200500, f"net اشتباه: {lot[1]}"
    stock = con.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
    assert stock == 1, f"حرکت انبار باید ۱ باشد، {stock} است"
    print(f"  OK  lot {lot[0]} با net {lot[1]} گرم و {stock} حرکت انبار")

    # 04 — purchase invoice, linked to the weigh ticket by its code.
    step(con, "PURCHASE_INVOICES", "04_PurchaseInvoices.xlsx", [
        ["PI-1", "1403/05/01", "C001", "WT-1", "PB-CHAIN", "5200.500",
         "85000", "0", "0", "0", "0", ""],
    ])
    inv = con.execute(
        "SELECT i.id, i.weigh_ticket_id, l.net_rial, l.grams "
        "FROM purchase_invoices i JOIN purchase_invoice_lines l ON l.invoice_id=i.id "
        "WHERE i.doc_number='PI-1'").fetchone()
    assert inv and inv[1] is not None, "فاکتور خرید به باسکول وصل نشد"
    assert inv[3] == 5200500, f"گرم فاکتور {inv[3]}"

    # 05 — sales invoice from the same lot. Must NOT move stock.
    before = con.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
    step(con, "SALES_INVOICES", "05_SalesInvoices.xlsx", [
        ["SI-1", "1403/05/03", "C002", "LOT001", "", "PB-CHAIN",
         "1000.250", "95000", "0", "0", "0", "0", "فروش زنجیره"],
    ])
    after = con.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
    assert after == before, "فاکتور فروش نباید انبار را جابه‌جا کند"

    # 06 — sorting against the lot created by step 03.
    step(con, "SORTING", "06_Sorting.xlsx", [
        # input 5000 = 4000 out + 600 waste + 300 process loss, variance 100,
        # tolerance 100 -> balanced. GR-ORANGE-1 and PK-CRATE come from the
        # seed; inventing a grade code here would only prove unknown codes are
        # rejected, which another test already proves.
        ["SRT-1", "1403/05/06", "LOT001", "W01", "5000", "PB-CHAIN",
         "GR-ORANGE-1", "PK-CRATE", "W01", "4000", "100", "600", "300", "100", ""],
    ])

    # 07 — a basket purchase from party C001.
    step(con, "BASKET_MOVEMENTS", "07_BasketMovements.xlsx", [
        ["BM-1", "1403/05/01", "PURCHASE", "BK01", "", "W01", "C001",
         "50", "45000", ""],
    ])

    # 08 — bank. Needs an account code that the seed provides.
    step(con, "BANK_TRANSACTIONS", "08_BankTransactions.xlsx", [
        ["TXN-1", "1403/05/04", "10:00", "BANK01", "IN", "C002", "", "9500000",
         "5000", "", "TRK-1", "دریافت از فروش"],
    ])

    # 09 — cheque from the same party.
    step(con, "CHEQUES", "09_Cheques.xlsx", [
        ["CHQ-1", "IN", "C002", "BANK01", "884512", "1234567890123456",
         "1403/05/01", "1403/07/01", "9500000", "چک دریافتی"],
    ])

    # 10 — settlement against the PURCHASE invoice from step 04. This is the
    #      template that could not run at all until the virtual lookup existed.
    con.execute(
        "INSERT INTO payments(code, doc_number, party_id, direction, amount_rial, status) "
        "VALUES('PAY-CHAIN','PAY-1',(SELECT id FROM parties WHERE code='C001'),"
        "'OUT',5000000,'DRAFT')")
    con.commit()          # import_file opens its own BEGIN IMMEDIATE
    step(con, "SETTLEMENTS", "10_Settlements.xlsx", [
        ["AL-1", "PAY-1", "PI-1", "5000000", "BANK", "تسویه بخشی"],
    ])
    alloc = con.execute(
        "SELECT purchase_invoice_id IS NOT NULL, sales_invoice_id IS NULL, amount_rial "
        "FROM payment_allocations WHERE source_key='AL-1'").fetchone()
    assert alloc == (1, 1, 5000000), f"تخصیص اشتباه: {alloc}"

    # 11 — partnership event, linked to the partner AND the product.
    step(con, "PARTNERSHIP", "11_Partnership.xlsx", [
        ["PA-1", "1403/05/01", "PARTNER_IN", "C001", "PB-CHAIN", "BK01", "W01",
         "1000", "20", "5", "2", "0", "50", "1", "NEAREST", "", "R-1",
         "مبدأ", "مقصد", ""],
    ])
    ev = con.execute(
        "SELECT party_id IS NOT NULL, product_id IS NOT NULL, gross_grams "
        "FROM partnership_events WHERE source_key='PA-1'").fetchone()
    assert ev == (1, 1, 1000000), f"رویداد مشارکت ناقص: {ev}"

    # Final integrity: the chain ran, so the database must be sound.
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    assert fk == [], f"FK شکسته: {fk}"
    assert integrity == "ok", integrity
    print(f"  OK  foreign_key_check خالی و integrity_check = {integrity}")

    # Every table the chain touched must hold what the chain put there. The
    # seed ships its own products and grades, so products is checked by the code
    # the chain created rather than by a raw row count.
    assert con.execute(
        "SELECT COUNT(*) FROM products WHERE code='PB-CHAIN'").fetchone()[0] == 1
    counts = {
        "parties": 2, "weigh_tickets": 1, "lots": 1,
        "purchase_invoices": 1, "sales_invoices": 1, "sorting_batches": 1,
        "basket_movements": 1, "bank_transactions": 1, "cheques": 1,
        "payment_allocations": 1, "partnership_events": 1,
    }
    for table, expected in counts.items():
        got = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert got == expected, f"{table}: {got} ردیف، انتظار {expected}"

    con.close()
    print()
    print("PASS  زنجیره ۱۱ قالب کامل و به هم پیوسته است")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nFAIL  {e}")
        sys.exit(1)
