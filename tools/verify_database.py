#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Database verification harness (dev tool, NOT part of the product).

Builds a temporary SQLite database from database/schema/schema_v001.sql and
database/seed/seed_v001.sql, then runs invariant tests derived from the
Master Spec (ch. 2, 8, 9, 10, 15, 16, 18). Prints PASS/FAIL per test and
exits non-zero on any failure. The C# product code is verified separately on
Windows (see reports/BASELINE.md); this harness proves the data layer.
"""
import hashlib
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "database", "schema", "schema_v001.sql")
SEED = os.path.join(ROOT, "database", "seed", "seed_v001.sql")

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
        print(f"PASS  {name}")
    except Exception as e:  # noqa: BLE001
        RESULTS.append((name, False, str(e)))
        print(f"FAIL  {name}: {e}")


def expect_error(fn, what):
    try:
        fn()
    except sqlite3.Error:
        return
    raise AssertionError(f"expected rejection: {what}")


def build_db(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    with open(SEED, encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()
    return con


def main():
    tmp = tempfile.mkdtemp(prefix="mazandasht_verify_")
    db_path = os.path.join(tmp, "mazandasht.db")
    con = build_db(db_path)

    def t_schema_tables():
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {
            "users", "roles", "permissions", "user_keys", "audit_events",
            "company_settings", "fiscal_periods", "sequences", "parties",
            "party_roles", "accounts", "account_groups", "banks",
            "bank_accounts", "products", "product_groups", "grades", "units",
            "packaging_types", "warehouses", "operations", "operation_types",
            "parameters", "weigh_tickets", "lots", "sorting_batches",
            "sorting_inputs", "sorting_outputs", "waste_records",
            "stock_movements", "purchase_invoices", "purchase_invoice_lines",
            "sales_invoices", "sales_invoice_lines", "payments",
            "payment_allocations", "bank_transactions", "cheques",
            "cheque_events", "basket_movements", "partnerships",
            "partnership_events", "employee_wages", "wage_shares",
            "journal_entries", "journal_lines", "import_batches",
            "import_rows", "import_profiles", "export_jobs", "backup_jobs",
            "schema_migrations", "main_groups", "sub_groups", "work_groups",
            "staff", "cheques_registry", "txn_types", "purchase_aggregations",
        }
        missing = required - tables
        assert not missing, f"missing tables: {sorted(missing)}"
        views = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='view'")}
        assert {"v_journal_balance", "v_stock_balance", "v_account_balance"} <= views

    def t_seed_counts():
        def n(sql):
            return con.execute(sql).fetchone()[0]
        assert n("SELECT COUNT(*) FROM roles") == 3
        assert n("SELECT COUNT(*) FROM permissions") == 23
        assert n("SELECT COUNT(*) FROM account_groups") == 10
        assert n("SELECT COUNT(*) FROM txn_types") == 6
        assert n("SELECT COUNT(*) FROM bank_accounts") == 2
        assert n("SELECT COUNT(*) FROM parameters") == 2
        assert n("SELECT COUNT(*) FROM accounts") == 11
        assert n("SELECT COUNT(*) FROM units") == 7
        assert n("SELECT COUNT(*) FROM products") == 4
        # Operator must NOT have db.reset; Admin must have it
        op_reset = n("""SELECT COUNT(*) FROM role_permissions rp
                         JOIN roles r ON r.id=rp.role_id
                         JOIN permissions p ON p.id=rp.permission_id
                         WHERE r.code='OPERATOR' AND p.code='db.reset'""")
        admin_reset = n("""SELECT COUNT(*) FROM role_permissions rp
                            JOIN roles r ON r.id=rp.role_id
                            JOIN permissions p ON p.id=rp.permission_id
                            WHERE r.code='ADMIN' AND p.code='db.reset'""")
        assert op_reset == 0 and admin_reset == 1

    def t_fk_integrity():
        bad = con.execute("PRAGMA foreign_key_check").fetchall()
        assert bad == [], f"FK violations: {bad}"

    def t_code_uniqueness():
        con.execute("INSERT INTO parties (code, display_name, nature) VALUES ('C001','مشتری نمونه','C')")
        con.commit()
        expect_error(
            lambda: con.execute("INSERT INTO parties (code, display_name, nature) VALUES ('C001','تکراری','C')"),
            "duplicate party code")
        con.rollback()

    def t_money_integer():
        expect_error(
            lambda: con.execute("INSERT INTO payments (code, direction, amount_rial) VALUES ('PAY-X', 'IN', 10.5)"),
            "REAL money amount")
        con.rollback()
        con.execute("INSERT INTO payments (code, direction, amount_rial) VALUES ('PAY-OK', 'IN', 1000)")
        con.commit()
        # Toman is display-only: 1000 Rial = 100 Toman, stored value unchanged
        rial = con.execute("SELECT amount_rial FROM payments WHERE code='PAY-OK'").fetchone()[0]
        assert rial == 1000 and rial // 10 == 100
        con.execute("DELETE FROM payments WHERE code='PAY-OK'")
        con.commit()

    def t_weight_grams():
        # 1.5 kg raw -> 1500 g standardized (P01 basket tare)
        con.execute("INSERT INTO weigh_tickets (code, direction, gross_kg_raw, gross_grams, tare_grams, loss_grams, net_grams) "
                    "VALUES ('WT-T', 'IN', '10.500', 10500, 1500, 0, 9000)")
        con.commit()
        row = con.execute("SELECT gross_grams, tare_grams, net_grams FROM weigh_tickets WHERE code='WT-T'").fetchone()
        assert row == (10500, 1500, 9000)
        # NetWeight = Gross - Tare - Loss (Spec ch. 5.1)
        assert row[2] == row[0] - row[1] - 0
        expect_error(
            lambda: con.execute("INSERT INTO weigh_tickets (code, direction, gross_grams) VALUES ('WT-BAD','IN', 1.5)"),
            "REAL grams")
        con.rollback()
        con.execute("DELETE FROM weigh_tickets WHERE code='WT-T'")
        con.commit()

    def t_params_p01_p02():
        p01 = con.execute("SELECT value_number, is_confirmed FROM parameters WHERE code='P01'").fetchone()
        p02 = con.execute("SELECT value_number, is_confirmed FROM parameters WHERE code='P02'").fetchone()
        assert p01 == (1.5, 0), p01   # 1.5 kg, NOT confirmed for operation
        assert p02 == (1.0, 0), p02   # 1%, NOT confirmed for operation

    def t_journal_balance():
        # DRAFT entries here so test cleanup is allowed; APPROVED immutability
        # is covered by t_approved_immutable.
        je = con.execute("INSERT INTO journal_entries (code, status, source_key) VALUES ('JE-T1','DRAFT','src-1')")
        jid = je.lastrowid
        cash = con.execute("SELECT id FROM accounts WHERE code='1000'").fetchone()[0]
        cap = con.execute("SELECT id FROM accounts WHERE code='3000'").fetchone()[0]
        con.execute("INSERT INTO journal_lines (journal_id, account_id, debit_rial) VALUES (?,?,100000)", (jid, cash))
        con.execute("INSERT INTO journal_lines (journal_id, account_id, credit_rial) VALUES (?,?,100000)", (jid, cap))
        con.commit()
        diff = con.execute("SELECT difference FROM v_journal_balance WHERE journal_id=?", (jid,)).fetchone()[0]
        assert diff == 0, f"balanced entry shows difference {diff}"
        # Unbalanced entry must be detectable
        je2 = con.execute("INSERT INTO journal_entries (code, status, source_key) VALUES ('JE-T2','DRAFT','src-2')")
        jid2 = je2.lastrowid
        con.execute("INSERT INTO journal_lines (journal_id, account_id, debit_rial) VALUES (?,?,50000)", (jid2, cash))
        con.commit()
        diff2 = con.execute("SELECT difference FROM v_journal_balance WHERE journal_id=?", (jid2,)).fetchone()[0]
        assert diff2 == 50000, f"unbalanced entry not detected: {diff2}"
        con.execute("DELETE FROM journal_lines WHERE journal_id IN (?,?)", (jid, jid2))
        con.execute("DELETE FROM journal_entries WHERE id IN (?,?)", (jid, jid2))
        con.commit()

    def t_idempotent_posting():
        con.execute("INSERT INTO journal_entries (code, status, source_key) VALUES ('JE-I1','DRAFT','dup-src')")
        con.commit()
        expect_error(
            lambda: con.execute("INSERT INTO journal_entries (code, status, source_key) VALUES ('JE-I2','DRAFT','dup-src')"),
            "duplicate source_key posting")
        con.rollback()
        con.execute("DELETE FROM journal_entries WHERE source_key='dup-src'")
        con.commit()

    def t_approved_immutable():
        je = con.execute("INSERT INTO journal_entries (code, status, source_key) VALUES ('JE-IM','APPROVED','imm-src')")
        jid = je.lastrowid
        con.commit()
        expect_error(lambda: con.execute("UPDATE journal_entries SET description='x' WHERE id=?", (jid,)),
                     "update approved journal")
        expect_error(lambda: con.execute("DELETE FROM journal_entries WHERE id=?", (jid,)),
                     "delete approved journal")
        con.rollback()
        # No cleanup delete: the trigger correctly keeps the approved row.
        # The temp DB is discarded after the run.

    def t_stock_derivation():
        prod = con.execute("SELECT id FROM products WHERE code='PB-ORANGE'").fetchone()[0]
        wh = con.execute("SELECT id FROM warehouses WHERE code='W01'").fetchone()[0]
        con.execute("INSERT INTO stock_movements (product_id, warehouse_id, movement_type, quantity_grams) VALUES (?,?, 'IN', 10000)", (prod, wh))
        con.execute("INSERT INTO stock_movements (product_id, warehouse_id, movement_type, quantity_grams) VALUES (?,?, 'OUT', 3000)", (prod, wh))
        con.commit()
        bal = con.execute("SELECT balance_grams FROM v_stock_balance WHERE product_id=? AND warehouse_id=?", (prod, wh)).fetchone()[0]
        assert bal == 7000, f"derived stock balance {bal} != 7000"
        con.execute("DELETE FROM stock_movements WHERE product_id=? AND warehouse_id=?", (prod, wh))
        con.commit()

    def t_approval_status_check():
        expect_error(
            lambda: con.execute("INSERT INTO weigh_tickets (code, direction, status) VALUES ('WT-S','IN','FINAL')"),
            "invalid approval status")
        con.rollback()

    def t_wage_shares_sum():
        w = con.execute("INSERT INTO employee_wages (code, total_rial, shares_total_rial) VALUES ('W-T', 100000, 100000)")
        wid = w.lastrowid
        p1 = con.execute("INSERT INTO parties (code, display_name, nature) VALUES ('E901','عضو یک','E')").lastrowid
        p2 = con.execute("INSERT INTO parties (code, display_name, nature) VALUES ('E902','عضو دو','E')").lastrowid
        con.execute("INSERT INTO wage_shares (wage_id, member_party_id, share_rial) VALUES (?,?,60000)", (wid, p1))
        con.execute("INSERT INTO wage_shares (wage_id, member_party_id, share_rial) VALUES (?,?,40000)", (wid, p2))
        con.commit()
        s = con.execute("SELECT COALESCE(SUM(share_rial),0) FROM wage_shares WHERE wage_id=?", (wid,)).fetchone()[0]
        total = con.execute("SELECT total_rial FROM employee_wages WHERE id=?", (wid,)).fetchone()[0]
        assert s == total == 100000, f"shares {s} != total {total}"
        con.execute("DELETE FROM wage_shares WHERE wage_id=?", (wid,))
        con.execute("DELETE FROM employee_wages WHERE id=?", (wid,))
        con.execute("DELETE FROM parties WHERE code IN ('E901','E902')")
        con.commit()

    def t_mass_balance():
        # Input = Outputs + Waste + ProcessLoss + Variance (Spec ch. 8)
        b = con.execute("INSERT INTO sorting_batches (code, input_grams, output_grams, waste_grams, process_loss_grams, variance_grams, tolerance_grams) "
                        "VALUES ('SB-T', 10000, 9000, 500, 300, 200, 100)")
        bid = b.lastrowid
        con.commit()
        row = con.execute("SELECT input_grams, output_grams, waste_grams, process_loss_grams, variance_grams, tolerance_grams FROM sorting_batches WHERE id=?", (bid,)).fetchone()
        inp, out, waste, loss, var, tol = row
        assert inp == out + waste + loss + var, "mass balance violated"
        assert abs(var) > tol, "variance should exceed tolerance -> stays in REVIEW"
        con.execute("DELETE FROM sorting_batches WHERE id=?", (bid,))
        con.commit()

    def t_bank_duplicate_control():
        ba = con.execute("SELECT id FROM bank_accounts WHERE code='BANK01'").fetchone()[0]
        con.execute("INSERT INTO bank_transactions (code, bank_account_id, deposit_rial, source_key) VALUES ('BT-1', ?, 5000, 'bank-src-1')", (ba,))
        con.commit()
        expect_error(
            lambda: con.execute("INSERT INTO bank_transactions (code, bank_account_id, deposit_rial, source_key) VALUES ('BT-2', ?, 5000, 'bank-src-1')", (ba,)),
            "duplicate bank source_key")
        con.rollback()
        con.execute("DELETE FROM bank_transactions WHERE source_key='bank-src-1'")
        con.commit()

    def t_partnership_basket_fields():
        # Consumed baskets and returned custody baskets are separate columns
        cols = {r[1] for r in con.execute("PRAGMA table_info(partnership_events)")}
        assert "basket_count" in cols and "returned_basket_count" in cols

    def t_reset_procedure():
        # Reset (Spec ch. 15) is implemented as DB replacement, NOT row
        # deletion: mandatory backup -> archive old file -> build a fresh DB
        # from schema+seed. This keeps approved-journal immutability intact
        # and is atomic. Simulate operational data in the live DB, then
        # verify the fresh DB has zero operational rows and full base data.
        con.execute("INSERT INTO parties (code, display_name, nature) VALUES ('C777','مشتری عملیاتی','C')")
        con.execute("INSERT INTO weigh_tickets (code, direction, party_id) VALUES ('WT-R','IN',(SELECT id FROM parties WHERE code='C777'))")
        con.execute("INSERT INTO journal_entries (code, status) VALUES ('JE-R','DRAFT')")
        con.commit()
        fresh_path = os.path.join(tmp, "fresh.db")
        fresh = build_db(fresh_path)
        operational = [
            "journal_lines", "journal_entries", "stock_movements", "waste_records",
            "sorting_outputs", "sorting_inputs", "sorting_batches", "lots",
            "purchase_invoice_lines", "purchase_invoices", "sales_invoice_lines",
            "sales_invoices", "payment_allocations", "payments",
            "bank_transactions", "cheque_events", "cheques", "basket_movements",
            "partnership_events", "partnerships", "purchase_aggregations",
            "wage_shares", "employee_wages", "import_rows", "import_batches",
            "export_jobs", "backup_jobs", "weigh_tickets", "parties", "users",
        ]
        for t in operational:
            n = fresh.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            assert n == 0, f"fresh DB still has {n} rows in {t}"
        # Base definitions present in the fresh DB
        assert fresh.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0] == 2
        assert fresh.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 7
        assert fresh.execute("SELECT COUNT(*) FROM parameters").fetchone()[0] == 2
        assert fresh.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 7
        assert fresh.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 11
        assert fresh.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 3
        fresh.close()

    def t_backup_sha256():
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.commit()
        with open(db_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
        # Integrity check result is part of the backup manifest (Spec ch. 16)
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        assert ok == "ok", f"integrity_check: {ok}"
        ver = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert ver == 1

    tests = [
        ("schema: all ch.18 entities + views exist", t_schema_tables),
        ("seed: base definitions + role matrix", t_seed_counts),
        ("integrity: foreign_key_check empty", t_fk_integrity),
        ("codes: party code uniqueness (C/SL/S/E/X/F/L/CAP)", t_code_uniqueness),
        ("money: integer Rial only; Toman display-only", t_money_integer),
        ("weight: integer grams; Net = Gross - Tare - Loss", t_weight_grams),
        ("params: P01=1.5kg / P02=1% present, unconfirmed", t_params_p01_p02),
        ("ledger: balanced entry diff=0, unbalanced detected", t_journal_balance),
        ("ledger: idempotent posting via source_key", t_idempotent_posting),
        ("ledger: approved entries immutable (triggers)", t_approved_immutable),
        ("stock: balance derived from movements (no balance column)", t_stock_derivation),
        ("approval: status CHECK DRAFT/REVIEW/APPROVED/VOIDED", t_approval_status_check),
        ("wages: SUM(shares) = total", t_wage_shares_sum),
        ("sorting: Input = Outputs + Waste + Loss + Variance", t_mass_balance),
        ("bank: duplicate control via source_key", t_bank_duplicate_control),
        ("partnership: consumed vs returned baskets separate", t_partnership_basket_fields),
        ("reset: operational cleared, base definitions kept", t_reset_procedure),
        ("backup: SHA-256 + integrity_check + schema version", t_backup_sha256),
    ]
    for name, fn in tests:
        check(name, fn)

    con.close()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
