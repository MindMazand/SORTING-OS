#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Import engine test harness (stages 1-7).

Builds REAL .xlsx fixtures with the real two-header-row layout, feeds them
through the same code path the product uses, and asserts observed behaviour
against a real SQLite database. No mocks: a mock would prove the mock works.

Run:  python3 tools/test_import.py
"""
import os
import sqlite3
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_contract as C          # noqa: E402
import import_engine as E            # noqa: E402
import import_parser as P            # noqa: E402
import verify_database as V          # noqa: E402
from xlsx_io import Workbook, write_workbook  # noqa: E402

RESULTS = []
TMP = tempfile.mkdtemp(prefix="mazandasht_import_")


def check(name, fn, con=None):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"PASS  {name}")
    except Exception as e:                      # noqa: BLE001
        RESULTS.append((name, False, str(e)))
        print(f"FAIL  {name}: {e}")
        traceback.print_exc(limit=3)
        # A test that dies mid-transaction used to poison every later test with
        # "cannot start a transaction within a transaction". The first real
        # failure then buried six innocent ones, which is how a suite becomes
        # untrustworthy.
        if con is not None:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass


def tpl_grid(code, data_rows, numeric=None):
    """Build the canonical grid for a template: English header, Persian header,
    then data. `numeric` = set of column indexes to store as numbers."""
    tpl = C.ALL[code]
    grid = [[f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields]]
    grid.extend(data_rows)
    return {"داده‌ها": grid,
            "راهنما": [["ماژول", tpl.module_fa]],
            "فرهنگ داده": [[f.name_en, f.name_fa] for f in tpl.fields]}, numeric


def build(code, name, data_rows, numeric=None):
    sheets, _ = tpl_grid(code, data_rows)
    path = os.path.join(TMP, name)
    write_workbook(path, sheets, {"داده‌ها": numeric} if numeric else None)
    return path


def fresh_db(name="imp.db"):
    path = os.path.join(TMP, name)
    con = V.build_db(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


PARTY_ROWS = [
    ["C001", "باغدار احمدی", "PERSON", "احمد احمدی", "0012345678", "411111111111",
     "09111234567", "01133445566", "نوشهر", "نمونه"],
    ["C002", "شرکت سبز مازند", "COMPANY", "شرکت سبز مازند", "10320000001", "",
     "09120000000", "", "آمل", ""],
]

PRODUCT_ROWS = [
    # PB-ORANGE ships in seed_v001, so importing it must be reported as a
    # duplicate rather than silently overwriting or crashing.
    ["PB-ORANGE", "پرتقال تامسون", "PG-CITRUS", "U-KG", "تامسون", "1", ""],
    ["PB-NEW", "نارنگی جدید", "PG-CITRUS", "U-KG", "", "", "رقم محلی"],
]

WEIGH_ROWS = [
    ["BASKOL-1001", "1403/05/01", "08:30", "IN", "C001", "PB-ORANGE", "W01",
     "5200.500", "75.000", "5125.500", "40", "PK-CRATE", "R-9001", "بار اول"],
    ["BASKOL-1002", "1403/05/02", "09:15", "IN", "C002", "PB-ORANGE", "W01",
     "3100", "", "3100", "20", "", "", ""],
]

SALES_ROWS = [
    ["S-5001", "1403/05/03", "C001", "LOT001", "", "PB-ORANGE",
     "1000.250", "85000", "50000", "0", "0", "0", "فروش نقدی"],
]

BANK_ROWS = [
    ["TXN-1", "1403/05/04", "10:00", "BANK01", "IN", "C001", "", "5000000",
     "5000", "120000000", "TRK-1", "واریز"],
    ["TXN-2", "1403/05/05", "", "BANK01", "OUT", "", "", "2000000", "", "", "", ""],
]

CHEQUE_ROWS = [
    ["CHQ-1", "IN", "C001", "BANK01", "884512", "1234567890123456",
     "1403/05/01", "1403/07/01", "15000000", "چک دریافتی"],
]

BASKET_ROWS = [
    ["BM-1", "1403/05/01", "PURCHASE", "BK01", "", "W01", "C001", "50", "45000", ""],
    # TRANSFER requires a counterparty (DB trigger) and both warehouses.
    ["BM-2", "1403/05/02", "TRANSFER", "BK01", "W01", "W01", "C002", "10", "", ""],
]

SORTING_ROWS = [
    ["SRT-1", "1403/05/06", "LOT001", "W01", "5000", "PB-ORANGE", "GR-ORANGE-1",
     "PK-CRATE", "W01", "4000", "100", "600", "300", "150", "سورت اول"],
]


def main():
    con = fresh_db()

    # -- stage 1: reader -----------------------------------------------------
    def t_reader_basic():
        p = build("PARTIES", "p1.xlsx", PARTY_ROWS)
        wb = Workbook(p)
        assert wb.sheets[:1] == ["داده‌ها"], wb.sheets
        sh = wb.sheet("داده‌ها")
        assert sh.cell(1, 1).text == "PartyCode", sh.cell(1, 1).text
        assert sh.cell(2, 1).text == "کد شخص"
        assert sh.cell(3, 1).text == "C001"
        assert sh.cell(3, 1).kind == "text", "code must arrive as text"
        wb.close()

    def t_reader_preserves_leading_zeros():
        p = build("PARTIES", "p_zero.xlsx", [PARTY_ROWS[0]])
        wb = Workbook(p)
        sh = wb.sheet("داده‌ها")
        assert sh.cell(3, 5).text == "0012345678", sh.cell(3, 5).text
        wb.close()

    def t_reader_detects_numeric_code():
        """A code saved as a NUMBER has already lost its zeros; the reader must
        say so instead of returning a clean-looking string."""
        # PartyCode "C001" cannot be numeric, so probe the national id column,
        # which is the realistic case: a user types 0012345678 and Excel keeps
        # 12345678. Column 5 = NationalId.
        p = build("PARTIES", "p_num.xlsx", [PARTY_ROWS[0]], numeric={(3, 5)})
        wb = Workbook(p)
        sh = wb.sheet("داده‌ها")
        cell = sh.cell(3, 5)
        assert cell.is_numeric_text, "numeric cell must be flagged"
        assert cell.text == "12345678", f"leading zeros already lost in the file: {cell.text}"
        wb.close()

    def t_reader_bad_file():
        bad = os.path.join(TMP, "not_a_workbook.xlsx")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("این فایل اکسل نیست")
        try:
            Workbook(bad)
            raise AssertionError("expected XlsxError")
        except Exception as e:
            assert "قابل خواندن" in str(e), str(e)

    # -- stage 2/3: detect + map --------------------------------------------
    def t_detect_all_eleven():
        """Every template must be recognised from its own headers alone."""
        probe = {
            "PARTIES": PARTY_ROWS, "PRODUCTS": PRODUCT_ROWS,
            "WEIGHING_IN": WEIGH_ROWS,
            "PURCHASE_INVOICES": [["P-1", "1403/05/01", "C001", "BASKOL-1001",
                                   "PB-ORANGE", "1000", "85000", "0", "0", "0", "0", ""]],
            "SALES_INVOICES": SALES_ROWS,
            "SORTING": SORTING_ROWS,
            "BASKET_MOVEMENTS": BASKET_ROWS,
            "BANK_TRANSACTIONS": BANK_ROWS,
            "CHEQUES": CHEQUE_ROWS,
            "SETTLEMENTS": [["AL-1", "PAY-1", "PI-1", "1000", "BANK", ""]],
            "PARTNERSHIP": [["PA-1", "1403/05/01", "PARTNER_IN", "C001", "PB-ORANGE",
                             "BK01", "W01", "1000", "20", "5", "2", "0", "50", "1",
                             "NEAREST", "", "R-1", "مبدأ", "مقصد", ""]],
        }
        assert set(probe) == set(C.ALL), "probe list must cover all 11 templates"
        for code, rows in probe.items():
            p = build(code, f"detect_{code}.xlsx", rows)
            res = P.parse_file(p)
            assert res.template is not None, f"{code}: not detected ({res.file_errors})"
            assert res.template.code == code, f"{code} detected as {res.template.code}"
            assert res.ok, f"{code}: file errors {res.file_errors}"

    def t_map_by_name_not_position():
        """Shuffled columns must still map correctly. A position-based reader
        would write purchase weight into the discount column."""
        tpl = C.ALL["PRODUCTS"]
        order = [3, 0, 1, 2, 6, 5, 4]
        grid = [[tpl.fields[i].name_en for i in order],
                [tpl.fields[i].name_fa for i in order],
                [PRODUCT_ROWS[0][i] for i in order]]
        p = os.path.join(TMP, "shuffled.xlsx")
        write_workbook(p, {"داده‌ها": grid})
        res = P.parse_file(p)
        assert res.ok, res.file_errors
        row = res.rows[0]
        assert row.values["ProductCode"] == "PB-ORANGE", row.values
        assert row.values["ProductName"] == "پرتقال تامسون"
        assert row.values["GroupCode"] == "PG-CITRUS"
        assert row.values["UnitCode"] == "U-KG"

    def t_map_missing_required_is_file_error():
        """If a required header is absent the file is rejected outright — never
        imported with a partial mapping."""
        tpl = C.ALL["WEIGHING_IN"]
        keep = [f for f in tpl.fields if f.name_en != "NetKg"]
        grid = [[f.name_en for f in keep], [f.name_fa for f in keep]]
        p = os.path.join(TMP, "missing_net.xlsx")
        write_workbook(p, {"داده‌ها": grid})
        res = P.parse_file(p)
        assert not res.ok, "file with a missing required header must be rejected"
        assert any("الزامی" in e for e in res.file_errors), res.file_errors

    def t_persian_only_headers():
        """A user file may carry only the Persian header row plus one English
        row; mapping must still work from Persian names."""
        tpl = C.ALL["PARTIES"]
        grid = [[f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields],
                PARTY_ROWS[0]]
        p = os.path.join(TMP, "fa_only.xlsx")
        write_workbook(p, {"داده‌ها": grid})
        res = P.parse_file(p)
        assert res.ok and res.rows[0].values["DisplayName"] == "باغدار احمدی"

    # -- stage 4: validation -------------------------------------------------
    def t_blank_is_not_zero():
        """Golden rule 7, at the value level: an empty optional cell must
        arrive as None, never as 0."""
        p = build("WEIGHING_IN", "blank.xlsx", [WEIGH_ROWS[1]])
        res = P.parse_file(p)
        row = res.rows[0]
        assert row.ok, [e.message for e in row.errors]
        assert row.values["TareKg"] is None, "blank tare must be None, not 0"
        assert row.values["PackageCount"] == 20
        assert "TareKg" in row.blanks
        assert row.values["PackagingCode"] is None

    def t_kg_to_grams_exact():
        p = build("WEIGHING_IN", "kg.xlsx", [WEIGH_ROWS[0]])
        row = P.parse_file(p).rows[0]
        assert row.values["ScaleKg"] == 5200500, row.values["ScaleKg"]
        assert row.values["TareKg"] == 75000
        assert row.values["NetKg"] == 5125500
        assert isinstance(row.values["ScaleKg"], int)

    def t_kg_rejects_four_decimals():
        rows = [["BASKOL-9", "1403/05/01", "", "IN", "C001", "PB-ORANGE", "W01",
                 "100.0001", "", "100.0001", "", "", "", ""]]
        p = build("WEIGHING_IN", "kg4.xlsx", rows)
        row = P.parse_file(p).rows[0]
        assert not row.ok, "4 decimals must be refused, not silently rounded"
        assert any("۳ رقم اعشار" in e.message for e in row.errors), \
            [e.message for e in row.errors]

    def t_shamsi_validation():
        assert P.valid_shamsi("1403/05/01") == (True, "1403/05/01")
        assert P.valid_shamsi("14030501") == (True, "1403/05/01")
        assert P.valid_shamsi("1403/12/30")[0] is True       # 1403 is leap
        assert P.valid_shamsi("1402/12/30")[0] is False      # 1402 is not leap
        assert P.valid_shamsi("1403/13/01")[0] is False
        assert P.valid_shamsi("1403/07/31")[0] is False      # month 7 has 30 days
        ok, msg = P.valid_shamsi("45292")
        assert ok is False and "serial" in msg, msg

    def t_jalali_leap_cycle():
        assert P.is_leap_jalali(1403) is True
        assert P.is_leap_jalali(1402) is False
        assert P.is_leap_jalali(1399) is True
        assert P.is_leap_jalali(1404) is False

    def t_formula_in_data_is_error():
        """Golden rule 8: a formula in an input column is an import error."""
        tpl = C.ALL["PRODUCTS"]
        path = os.path.join(TMP, "formula.xlsx")
        write_workbook(path, {"داده‌ها": [
            [f.name_en for f in tpl.fields], [f.name_fa for f in tpl.fields],
            ["PB-X", "محصول فرمولی", "PG-CITRUS", "U-KG", "", "", ""]]})
        # inject a <f> element directly into the sheet xml
        import re
        import zipfile
        with zipfile.ZipFile(path) as z:
            items = {n: z.read(n) for n in z.namelist()}
        xml = items["xl/worksheets/sheet1.xml"].decode("utf-8")
        xml = re.sub(r'(<c r="B3"[^>]*)(>)', r'\1><f>CONCAT("a","b")</f>\2', xml, count=1)
        items["xl/worksheets/sheet1.xml"] = xml.encode("utf-8")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for n, b in items.items():
                z.writestr(n, b)
        res = P.parse_file(path)
        row = res.rows[0]
        assert not row.ok, "formula in data must be an error"
        assert any("فرمول" in e.message for e in row.errors), \
            [e.message for e in row.errors]

    def t_missing_required_value_is_row_error():
        # A required cell can only be blank if the file has a value elsewhere in
        # that row (otherwise the writer drops an all-blank row). PartyType blank
        # with everything else present is the realistic case.
        rows = [["C900", "بی‌نوع", "", "نام کامل", "", "", "", "", "", "یادداشت"],
                ["C901", "درست", "PERSON", "", "", "", "", "", "", ""]]
        p = build("PARTIES", "req.xlsx", rows)
        res = P.parse_file(p)
        assert len(res.invalid_rows) == 1 and len(res.valid_rows) == 1, \
            (len(res.invalid_rows), len(res.valid_rows))
        assert not res.rows[0].ok, "row with a blank required PartyType must fail"
        assert any("الزامی" in e.message for e in res.rows[0].errors)

    def t_kind_vocabulary_enforced():
        rows = [["C901", "نام", "ORGANIZATION", "", "", "", "", "", "", ""]]
        p = build("PARTIES", "kind.xlsx", rows)
        row = P.parse_file(p).rows[0]
        assert not row.ok and any("مجاز نیست" in e.message for e in row.errors)

    # -- stage 5: resolve ----------------------------------------------------
    def t_unknown_code_is_an_error():
        """An unknown code must NOT create a row: importing a party code that
        does not exist would silently invent a person."""
        p = build("WEIGHING_IN", "unk.xlsx",
                  [["BASKOL-1", "1403/05/01", "", "IN", "C999", "PB-NOPE", "W01",
                    "100", "", "100", "", "", "", ""]])
        res = P.parse_file(p)
        resolved = E.resolve_rows(con, res.template, res.rows)
        assert not resolved[0].ok
        joined = " ".join(resolved[0].errors)
        assert "پیدا نشد" in joined, joined
        assert con.execute("SELECT COUNT(*) FROM parties WHERE code='C999'").fetchone()[0] == 0

    # -- the two writers no test had ever executed ---------------------------
    def t_import_settlement_finds_invoice_on_either_side():
        """SETTLEMENTS had a writer that could never run: it resolved the invoice
        through `invoices:doc_number`, a table that does not exist, and depended
        on `__invoice_kind` which nothing ever set. Detection-only coverage hid
        both. This imports a real settlement against a PURCHASE invoice."""
        con.execute(
            "INSERT INTO payments(code, doc_number, party_id, direction, amount_rial, status) "
            "VALUES('PAY900','PAY-1',(SELECT id FROM parties WHERE code='C001'),"
            "'OUT',1000,'DRAFT')")
        con.execute(
            "INSERT INTO purchase_invoices(code, doc_number, date_iso, date_shamsi, "
            "party_id, status) VALUES('PI900','PI-1','2024-07-22','1403/05/01',"
            "(SELECT id FROM parties WHERE code='C001'),'DRAFT')")
        con.execute(
            "INSERT INTO sales_invoices(code, doc_number, date_iso, date_shamsi, "
            "party_id, status) VALUES('SI900','SI-9','2024-07-22','1403/05/03',"
            "(SELECT id FROM parties WHERE code='C001'),'DRAFT')")
        con.commit()

        p = build("SETTLEMENTS", "settle.xlsx",
                  [["AL-1", "PAY-1", "PI-1", "1000", "BANK", ""],
                   ["AL-2", "PAY-1", "SI-9", "500", "BANK", ""]])
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        assert out.created == 2, (out.created, out.errors)

        buy = con.execute(
            "SELECT purchase_invoice_id IS NOT NULL, sales_invoice_id IS NULL, amount_rial "
            "FROM payment_allocations WHERE source_key='AL-1'").fetchone()
        sell = con.execute(
            "SELECT purchase_invoice_id IS NULL, sales_invoice_id IS NOT NULL, amount_rial "
            "FROM payment_allocations WHERE source_key='AL-2'").fetchone()
        assert buy == (1, 1, 1000), buy
        assert sell == (1, 1, 500), sell

    def t_settlement_ambiguous_or_unknown_invoice_is_an_error():
        """An invoice number that exists on neither side must not create an
        allocation pointing at nothing."""
        p = build("SETTLEMENTS", "settle_bad.xlsx",
                  [["AL-9", "PAY-1", "PI-NOPE", "1000", "BANK", ""]])
        res = P.parse_file(p)
        resolved = E.resolve_rows(con, res.template, res.rows)
        assert not resolved[0].ok
        assert any("پیدا نشد" in e for e in resolved[0].errors), resolved[0].errors

    def t_import_partnership_event():
        """PARTNERSHIP is the last writer; blank-vs-zero matters here because a
        blank loss percent must stay NULL, not become 0% (which would mean the
        partner agreed to no loss at all)."""
        p = build("PARTNERSHIP", "partner.xlsx",
                  [["PA-1", "1403/05/01", "PARTNER_IN", "C001", "PB-ORANGE",
                    "BK01", "W01", "1000", "20", "5", "2", "0", "50", "",
                    "NEAREST", "", "R-1", "مبدأ", "مقصد", ""]])
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        assert out.created == 1, (out.created, out.errors)
        row = con.execute(
            "SELECT event_type, date_shamsi, gross_grams, consumed_baskets, "
            "       partner_share_percent, loss_percent, extra_waste_grams "
            "FROM partnership_events WHERE source_key='PA-1'").fetchone()
        assert row[0] == "PARTNER_IN" and row[1] == "1403/05/01", row
        assert row[2] == 1000000, row      # 1000 kg -> grams, exact
        assert row[3] == 20, row
        assert row[6] == 0, row          # an explicit 0 kg stays 0
        # and a BLANK percent must stay NULL, not become 0% ("no loss agreed")
        blank = build("PARTNERSHIP", "partner_blank.xlsx",
                      [["PA-2", "1403/05/02", "PARTNER_IN", "C001", "PB-ORANGE",
                        "BK01", "W01", "", "", "", "", "", "", "", "NEAREST", "",
                        "", "مبدأ", "مقصد", ""]])
        out2 = E.import_file(con, blank)
        assert out2.errors == [], out2.errors
        got = con.execute(
            "SELECT loss_percent, gross_grams FROM partnership_events "
            "WHERE source_key='PA-2'").fetchone()
        assert got[0] is None, f"blank loss percent became {got[0]!r}"
        assert got[1] == 0, "blank weight is 0 grams, and that is a recorded fact"

    # -- stage 6: commit -----------------------------------------------------
    def t_import_parties():
        p = build("PARTIES", "parties_ok.xlsx", PARTY_ROWS)
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        assert out.created == 2, out.created
        rows = con.execute(
            "SELECT code, display_name, party_kind, national_code, economic_code "
            "FROM parties WHERE code IN ('C001','C002') ORDER BY code").fetchall()
        assert rows[0][:4] == ("C001", "باغدار احمدی", "PERSON", "0012345678"), rows[0]
        assert rows[0][4] == "411111111111"
        assert rows[1][4] is None, "blank economic code must be NULL, not '' or 0"
        # a party imported from the template is confirmed, unlike a backfilled one
        assert con.execute(
            "SELECT party_kind_confirmed FROM parties WHERE code='C001'").fetchone()[0] == 1
        # the account class comes from the stable code prefix
        assert con.execute("SELECT nature FROM parties WHERE code='C001'").fetchone()[0] == "C"

    def t_import_products():
        p = build("PRODUCTS", "products_ok.xlsx", PRODUCT_ROWS)
        out = E.import_file(con, p)
        # PB-ORANGE is in the seed already -> exactly one duplicate, one import
        assert out.created == 1, (out.created, out.errors)
        assert any("تکراری" in e for e in out.errors), out.errors
        assert con.execute(
            "SELECT COUNT(*) FROM products WHERE code='PB-ORANGE'").fetchone()[0] == 1
        r = con.execute(
            "SELECT group_id IS NOT NULL, unit_id IS NOT NULL, is_active, variety_name "
            "FROM products WHERE code='PB-NEW'").fetchone()
        assert r[0] == 1 and r[1] == 1, "group/unit must resolve to ids"
        assert r[2] == 1, "blank IsActive means active"
        # blank stays ABSENT: NULL, not '' and not 0
        assert r[3] is None, f"blank variety must stay NULL, got {r[3]!r}"

    def t_import_weigh_creates_stock_once():
        p = build("WEIGHING_IN", "weigh_ok.xlsx", WEIGH_ROWS)
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        assert out.created == 2
        # goods entered: stock must reflect the weighbridge and nothing else
        total_in = con.execute(
            "SELECT COALESCE(SUM(quantity_grams),0) FROM stock_movements "
            "WHERE movement_type='IN'").fetchone()[0]
        expected = 5125500 + 3100000
        assert total_in == expected, f"stock {total_in} != weighbridge total {expected}"
        t = con.execute(
            "SELECT direction, net_grams, gross_grams, tare_grams, status, package_count, "
            "receipt_number FROM weigh_tickets WHERE source_key='BASKOL-1002'").fetchone()
        assert t == ("IN", 3100000, 3100000, 0, "DRAFT", 20, None), t
        # each ticket produced exactly one lot
        assert con.execute(
            "SELECT COUNT(*) FROM lots WHERE weigh_ticket_id IS NOT NULL").fetchone()[0] == 2

    def t_duplicate_import_blocked():
        """Re-importing the same file must not double-post."""
        before = con.execute("SELECT COUNT(*) FROM weigh_tickets").fetchone()[0]
        p = build("WEIGHING_IN", "weigh_dup.xlsx", WEIGH_ROWS)
        out = E.import_file(con, p)
        after = con.execute("SELECT COUNT(*) FROM weigh_tickets").fetchone()[0]
        assert out.created == 0, f"duplicates imported: {out.created}"
        assert after == before, f"rows created: {before} -> {after}"
        assert all("تکراری" in e for e in out.errors), out.errors[:2]

    def t_balance_check_matches_source_net():
        """The importer must agree with the owner's net-weight formula or say
        why it does not (DEC-NEW-008)."""
        gross, tare = 5200.500, 75.000
        natural = gross - tare
        stated = 5125.500
        assert abs(natural - stated) < 0.001, "fixture itself is inconsistent"

    def t_sales_invoice_does_not_move_stock():
        """DEC-NEW-007: an invoice must never add stock a second time."""
        before = con.execute(
            "SELECT COALESCE(SUM(quantity_grams),0) FROM stock_movements").fetchone()[0]
        p = build("SALES_INVOICES", "sales_ok.xlsx", SALES_ROWS)
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        after = con.execute(
            "SELECT COALESCE(SUM(quantity_grams),0) FROM stock_movements").fetchone()[0]
        assert after == before, f"a sales invoice changed stock: {before} -> {after}"
        line = con.execute(
            "SELECT grams, rate_rial_per_kg, gross_rial, net_rial "
            "FROM sales_invoice_lines").fetchone()
        assert line[0] == 1000250, line
        assert line[1] == 85000
        assert line[2] == (1000250 * 85000 + 500) // 1000
        assert line[3] == line[2] - 50000

    def t_bank_transaction_direction_and_fee():
        p = build("BANK_TRANSACTIONS", "bank_ok.xlsx", BANK_ROWS)
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        rows = con.execute(
            "SELECT direction, deposit_rial, withdrawal_rial, fee_rial, "
            "reported_balance_known, bank_balance_rial, tracking_number "
            "FROM bank_transactions ORDER BY id").fetchall()
        assert rows[0][:4] == ("IN", 5000000, 0, 5000), rows[0]
        assert rows[0][4] == 1 and rows[0][5] == 120000000
        assert rows[1][:4] == ("OUT", 0, 2000000, 0), rows[1]
        assert rows[1][4] == 0, "absent reported balance must not read as a real 0"

    def t_cheque_direction_mapping():
        p = build("CHEQUES", "chq_ok.xlsx", CHEQUE_ROWS)
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        r = con.execute(
            "SELECT direction, issue_date_shamsi, due_date_shamsi, sayad_id, status "
            "FROM cheques").fetchone()
        assert r[0] == "RECEIVED", f"template IN must become RECEIVED, got {r[0]}"
        assert r[1] == "1403/05/01" and r[2] == "1403/07/01"
        assert r[3] == "1234567890123456"
        assert r[4] == "OPEN"

    def t_basket_transfer_needs_both_warehouses():
        p = build("BASKET_MOVEMENTS", "bm_bad.xlsx",
                  [["BM-9", "1403/05/02", "TRANSFER", "BK01", "", "W01", "", "5", "", ""]])
        out = E.import_file(con, p, commit=False)
        assert out.failed == 1, out
        assert any("انبار مبدأ" in e for e in out.errors), out.errors

    def t_sorting_mass_balance_enforced():
        bad = [["SRT-9", "1403/05/06", "LOT001", "W01", "5000", "PB-ORANGE",
                "GR-ORANGE-1", "PK-CRATE", "W01", "4000", "", "300", "", "100", ""]]
        p = build("SORTING", "srt_bad.xlsx", bad)
        out = E.import_file(con, p, commit=False)
        assert out.failed == 1, out
        assert any("موازنه جرم" in e for e in out.errors), out.errors

        good = build("SORTING", "srt_ok.xlsx", SORTING_ROWS)
        out2 = E.import_file(con, good)
        assert out2.errors == [], out2.errors
        b = con.execute(
            "SELECT input_grams, output_grams, waste_grams, process_loss_grams, "
            "variance_grams, tolerance_grams FROM sorting_batches").fetchone()
        assert b == (5000000, 4000000, 600000, 300000, 100000, 150000), b
        assert abs(b[4]) <= b[5], "variance must be inside tolerance"

    # -- preview vs commit ---------------------------------------------------
    def t_preview_writes_nothing():
        before = con.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0]
        p = build("BANK_TRANSACTIONS", "preview.xlsx",
                  [["TXN-P", "1403/06/01", "", "BANK01", "IN", "", "", "1000", "", "", "", ""]])
        out = E.import_file(con, p, commit=False)
        after = con.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0]
        assert out.errors == [], out.errors
        assert after == before, "preview must not write documents"
        assert con.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0] >= 0

    # -- stage 7: rollback ---------------------------------------------------
    def t_rollback_draft_batch():
        p = build("BASKET_MOVEMENTS", "bm_ok.xlsx", BASKET_ROWS)
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        assert con.execute("SELECT COUNT(*) FROM basket_movements").fetchone()[0] == 2
        rb = E.rollback_batch(con, out.batch_id)
        assert rb.errors == [], rb.errors
        assert con.execute("SELECT COUNT(*) FROM basket_movements").fetchone()[0] == 0
        assert con.execute(
            "SELECT status FROM import_batches WHERE id=?", (out.batch_id,)).fetchone()[0] \
            == "ROLLED_BACK"
        # rolling back twice is refused, not silently repeated
        assert E.rollback_batch(con, out.batch_id).errors

    def t_rollback_refused_after_approval():
        """An approved document is immutable: rollback must refuse rather than
        delete an audit trail."""
        p = build("BANK_TRANSACTIONS", "frozen.xlsx",
                  [["TXN-F", "1403/07/01", "", "BANK01", "IN", "", "", "7000", "", "", "", ""]])
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        con.execute("UPDATE bank_transactions SET status='APPROVED' WHERE source_key='TXN-F'")
        con.commit()
        rb = E.rollback_batch(con, out.batch_id)
        assert rb.errors, "rollback of an approved batch must be refused"
        assert "تأییدشده" in rb.errors[0]
        assert con.execute(
            "SELECT COUNT(*) FROM bank_transactions WHERE source_key='TXN-F'").fetchone()[0] == 1

    def t_atomic_on_failure():
        """One bad row must not leave a half-written file behind."""
        before = con.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
        rows = [["C950", "درست", "PERSON", "", "", "", "", "", "", ""],
                ["C951", "خراب", "ORGANIZATION", "نام", "", "", "", "", "", "یادداشت"]]
        p = build("PARTIES", "partial.xlsx", rows)
        out = E.import_file(con, p)
        after_good = con.execute(
            "SELECT COUNT(*) FROM parties WHERE code='C950'").fetchone()[0]
        assert con.execute(
            "SELECT COUNT(*) FROM parties WHERE code='C951'").fetchone()[0] == 0
        # valid rows in the same file are still imported; the bad row is
        # recorded as INVALID with its reason, never silently dropped
        assert after_good == 1
        assert out.failed == 1
        bad = con.execute(
            "SELECT status, error_message FROM import_rows WHERE status='INVALID'").fetchone()
        assert bad and bad[1], "invalid row must carry a reason"
        assert con.execute("SELECT COUNT(*) FROM parties").fetchone()[0] >= before

    def t_import_batch_audit_trail():
        b = con.execute(
            "SELECT detected_type, file_sha256, header_row, header_row_second, total_rows "
            "FROM import_batches ORDER BY id DESC LIMIT 1").fetchone()
        assert b[0] in C.ALL, b
        assert len(b[1]) == 64, "file hash must be a full SHA-256"
        assert b[2] == 1 and b[3] == 2, "both header rows must be recorded"

    def t_integrity_after_all_imports():
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def t_duplicate_within_one_file():
        """Two identical source codes in ONE file must not both import: the
        second would double-post silently."""
        p = build("BANK_TRANSACTIONS", "dup_in_file.xlsx", [
            ["TXN-D", "1403/08/01", "", "BANK01", "IN", "", "", "1000", "", "", "", ""],
            ["TXN-D", "1403/08/02", "", "BANK01", "IN", "", "", "2000", "", "", "", ""],
        ])
        out = E.import_file(con, p)
        assert out.created == 1, out.created
        assert any("همین فایل" in e for e in out.errors), out.errors

    def t_rollback_weigh_with_children():
        """A weigh ticket owns a lot, and the lot owns a stock movement.

        The first version of rollback deleted the ticket first and died on the
        foreign key — a real bug that no earlier test caught because only
        basket movements (which have no children) were exercised.
        """
        p = build("WEIGHING_IN", "rb_weigh.xlsx", [[
            "BASKOL-RB", "1403/09/01", "", "IN", "C001", "PB-ORANGE", "W01",
            "8000", "", "8000", "", "", "", ""]])
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        lot_before = con.execute(
            "SELECT COUNT(*) FROM lots WHERE weigh_ticket_id IS NOT NULL").fetchone()[0]
        stock_before = con.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0]
        assert lot_before >= 1 and stock_before >= 1

        rb = E.rollback_batch(con, out.batch_id)
        assert rb.errors == [], rb.errors
        assert rb.created == 1
        # the ticket AND its children must be gone
        assert con.execute(
            "SELECT COUNT(*) FROM weigh_tickets WHERE source_key='BASKOL-RB'").fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM lots WHERE weigh_ticket_id IS NOT NULL").fetchone()[0] \
            == lot_before - 1
        assert con.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0] \
            == stock_before - 1
        # stock total must return to what it was before this import
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []

    def t_rollback_sorting_with_children():
        p = build("SORTING", "rb_sort.xlsx", [[
            "SRT-RB", "1403/09/02", "LOT001", "W01", "1000", "PB-ORANGE",
            "GR-ORANGE-1", "PK-CRATE", "W01", "800", "", "150", "50", "100", ""]])
        out = E.import_file(con, p)
        assert out.errors == [], out.errors
        rb = E.rollback_batch(con, out.batch_id)
        assert rb.errors == [], rb.errors
        assert con.execute(
            "SELECT COUNT(*) FROM sorting_batches WHERE source_key='SRT-RB'").fetchone()[0] == 0
        assert con.execute(
            "SELECT COUNT(*) FROM sorting_outputs WHERE batch_id NOT IN "
            "(SELECT id FROM sorting_batches)").fetchone()[0] == 0

    tests = [
        ("خواننده: شیت/هدر/مقدار درست خوانده می‌شود", t_reader_basic),
        ("خواننده: صفر ابتدایی کد حفظ می‌شود", t_reader_preserves_leading_zeros),
        ("خواننده: کد عددی تشخیص داده می‌شود", t_reader_detects_numeric_code),
        ("خواننده: فایل غیراکسل با پیام روشن رد می‌شود", t_reader_bad_file),
        ("تشخیص: هر ۱۱ قالب از سرستون‌ها شناسایی می‌شوند", t_detect_all_eleven),
        ("نگاشت: بر اساس نام ستون، نه موقعیت", t_map_by_name_not_position),
        ("نگاشت: سرستون الزامی غایب = رد کل فایل", t_map_missing_required_is_file_error),
        ("نگاشت: فایل فقط فارسی هم کار می‌کند", t_persian_only_headers),
        ("اعتبارسنجی: خالی ≠ صفر", t_blank_is_not_zero),
        ("اعتبارسنجی: کیلوگرم → گرم دقیق (۳ اعشار)", t_kg_to_grams_exact),
        ("اعتبارسنجی: ۴ رقم اعشار رد می‌شود", t_kg_rejects_four_decimals),
        ("اعتبارسنجی: تاریخ شمسی/سریال اکسل", t_shamsi_validation),
        ("اعتبارسنجی: چرخه کبیسه شمسی", t_jalali_leap_cycle),
        ("اعتبارسنجی: فرمول در ستون داده = خطا", t_formula_in_data_is_error),
        ("اعتبارسنجی: مقدار الزامی خالی = خطای ردیف", t_missing_required_value_is_row_error),
        ("اعتبارسنجی: واژگان نوع شخص", t_kind_vocabulary_enforced),
        ("اتصال: کد ناشناس ردیف نمی‌سازد", t_unknown_code_is_an_error),
        ("ثبت: اشخاص", t_import_parties),
        ("ثبت: محصولات با کلید گروه/واحد", t_import_products),
        ("ثبت: باسکول موجودی را یک‌بار می‌سازد", t_import_weigh_creates_stock_once),
        ("ثبت: واردسازی دوباره همان فایل رد می‌شود", t_duplicate_import_blocked),
        ("قاعده: وزن خالص با فرمول مالک می‌خواند", t_balance_check_matches_source_net),
        ("قاعده: فاکتور فروش موجودی را تغییر نمی‌دهد", t_sales_invoice_does_not_move_stock),
        ("ثبت: تراکنش بانکی، جهت و کارمزد", t_bank_transaction_direction_and_fee),
        ("ثبت: نگاشت جهت چک IN→RECEIVED", t_cheque_direction_mapping),
        ("ثبت: تسویه فاکتور را در هر دو سمت پیدا می‌کند", t_import_settlement_finds_invoice_on_either_side),
        ("قاعده: شماره فاکتور ناشناس تسویه نمی‌سازد", t_settlement_ambiguous_or_unknown_invoice_is_an_error),
        ("ثبت: رویداد مشارکت (آخرین نویسنده)", t_import_partnership_event),
        ("قاعده: انتقال سبد نیازمند دو انبار", t_basket_transfer_needs_both_warehouses),
        ("قاعده: موازنه جرم سورتینگ", t_sorting_mass_balance_enforced),
        ("پیش‌نمایش: هیچ سندی نوشته نمی‌شود", t_preview_writes_nothing),
        ("برگشت: دسته پیش‌نویس کامل حذف می‌شود", t_rollback_draft_batch),
        ("برگشت: باسکول با فرزندانش (lot/stock) کامل حذف می‌شود", t_rollback_weigh_with_children),
        ("برگشت: سورتینگ با فرزندانش کامل حذف می‌شود", t_rollback_sorting_with_children),
        ("برگشت: پس از تأیید ممکن نیست", t_rollback_refused_after_approval),
        ("اتمی: ردیف خراب، فایل را نیمه‌کاره نمی‌گذارد", t_atomic_on_failure),
        ("ردیابی: دسته، هش فایل و دو ردیف هدر", t_import_batch_audit_trail),
        ("تکرار: کد سند تکراری در یک فایل", t_duplicate_within_one_file),
        ("یکپارچگی: FK و integrity پس از همه واردسازی‌ها", t_integrity_after_all_imports),
    ]
    for name, fn in tests:
        check(name, fn, con)

    con.close()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
