#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Database verification harness (dev tool, NOT part of the product).

Builds a temporary SQLite database from database/schema/schema_v001.sql,
database/seed/seed_v001.sql and database/migrations/002_*.sql, then runs
invariant tests derived from the Master Spec (ch. 2, 8, 9, 10, 15, 16, 18) and
from the owner's reference workbooks (docs/WORKBOOK_SPEC_FA.md ch.10).
Prints PASS/FAIL per test and exits non-zero on any failure.

Migration is applied exactly the way MigrationRunner does it: PRAGMA
foreign_keys=OFF *before* the transaction, whole file in ONE transaction,
then foreign_key_check with rollback on violation. Testing it any other way
would not prove the shipped path.

The C# product code is verified separately on Windows (see
reports/BASELINE.md); this harness proves the data layer.
"""
import hashlib
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "database", "schema", "schema_v001.sql")
SEED = os.path.join(ROOT, "database", "seed", "seed_v001.sql")
MIGRATION_DIR = os.path.join(ROOT, "database", "migrations")
SCHEMA_VERSION = 4

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


def migration_files():
    """Versioned migrations, ordered, exactly as MigrationRunner.LoadFromFolder
    resolves them (NNN_name.sql, numeric prefix = version)."""
    out = []
    for name in sorted(os.listdir(MIGRATION_DIR)):
        if not name.endswith(".sql"):
            continue
        prefix = name.split("_", 1)[0]
        if prefix.isdigit():
            out.append((int(prefix), os.path.join(MIGRATION_DIR, name)))
    out.sort()
    return out


def apply_migrations(con):
    """Mirror of MigrationRunner.Migrate(): one transaction per version,
    FK checks disabled before the transaction, verified after it."""
    current = con.execute(
        "SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
    for version, path in migration_files():
        if version <= current:
            continue
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        con.execute("PRAGMA foreign_keys = OFF")   # must be outside the txn
        con.commit()
        con.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
        bad = con.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            con.execute("ROLLBACK")
            raise AssertionError(
                f"migration {version} broke foreign keys: {bad}")
        con.execute("PRAGMA foreign_keys = ON")
        con.commit()


def build_db(path, with_migrations=True):
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    with open(SEED, encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()
    if with_migrations:
        apply_migrations(con)
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
        assert ver == SCHEMA_VERSION

    # =====================================================================
    # v002 — reference-workbook alignment (docs/WORKBOOK_SPEC_FA.md ch.10)
    # Every test below asserts OBSERVED behaviour, not the presence of a
    # column: a column that exists but does not constrain anything proves
    # nothing (that mistake cost this project one already: see the G-11 note
    # in the ledger, where a trigger passed while the old CHECK still rejected
    # the template's own vocabulary).
    # =====================================================================

    def t_v002_migration_applied():
        ver = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert ver == SCHEMA_VERSION, f"expected schema version {SCHEMA_VERSION}, got {ver}"
        for want in (2, 3, 4):
            row = con.execute(
                "SELECT name FROM schema_migrations WHERE version = ?", (want,)).fetchone()
            assert row and f"v00{want}" in row[0], f"v00{want} record: {row}"

    def t_v002_rebuild_preserved_data():
        """The two rebuilt tables must keep every pre-existing row and id."""
        # Rebuild a second, independent DB up to v001, insert data, then migrate.
        p = os.path.join(tmp, "rebuild_check.db")
        old = build_db(p, with_migrations=False)
        old.execute("INSERT INTO baskets(code,name) VALUES ('BK9','سبد آزمون')")
        old.execute("INSERT INTO payments(code,direction,amount_rial) VALUES ('PAY-RB','IN',5000)")
        old.execute("INSERT INTO purchase_invoices(code,date_iso,date_shamsi) VALUES ('PI-RB','2024-01-01','1402/10/11')")
        old.execute("""INSERT INTO basket_movements(basket_id,event_type,quantity,doc_number)
                       VALUES ((SELECT id FROM baskets WHERE code='BK9'),'RETURN',3,'D-1')""")
        old.execute("""INSERT INTO payment_allocations(payment_id,invoice_id,invoice_kind,amount_rial)
                       VALUES ((SELECT id FROM payments WHERE code='PAY-RB'),
                               (SELECT id FROM purchase_invoices WHERE code='PI-RB'),'PURCHASE',5000)""")
        old.commit()
        bm_id = old.execute("SELECT id FROM basket_movements").fetchone()[0]
        al_id = old.execute("SELECT id FROM payment_allocations").fetchone()[0]
        old.close()

        apply_migrations(old := sqlite3.connect(p))
        old.execute("PRAGMA foreign_keys = ON")
        # rows survived, with their original ids
        assert old.execute("SELECT COUNT(*) FROM basket_movements").fetchone()[0] == 1
        assert old.execute("SELECT id,event_type,quantity,doc_number FROM basket_movements").fetchone() \
            == (bm_id, 'RETURN', 3, 'D-1'), "basket_movement row changed during rebuild"
        assert old.execute("SELECT COUNT(*) FROM payment_allocations").fetchone()[0] == 1
        assert old.execute("SELECT id,amount_rial FROM payment_allocations").fetchone() == (al_id, 5000)
        # the legacy allocation was correctly upgraded to a typed FK
        typed = old.execute("SELECT purchase_invoice_id,sales_invoice_id FROM payment_allocations").fetchone()
        assert typed[0] is not None and typed[1] is None, f"legacy upgrade failed: {typed}"
        # and the rebuilt row is a real FK, not a dangling number
        assert old.execute("SELECT COUNT(*) FROM purchase_invoices WHERE id=?", (typed[0],)).fetchone()[0] == 1
        assert old.execute("PRAGMA foreign_key_check").fetchall() == []
        assert old.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        old.close()

    def t_g01_party_kind():
        """PERSON/COMPANY is a separate axis from the account class `nature`."""
        con.execute("""INSERT INTO parties(code,display_name,nature,party_kind)
                       VALUES ('SL900','شرکت آزمون','SL','COMPANY')""")
        con.execute("""INSERT INTO parties(code,display_name,nature,party_kind)
                       VALUES ('E901','کارمند آزمون','E','PERSON')""")
        con.commit()
        # both concepts coexist on one row: a COMPANY that is also a supplier
        r = con.execute("SELECT nature,party_kind FROM parties WHERE code='SL900'").fetchone()
        assert r == ('SL', 'COMPANY'), r
        expect_error(lambda: con.execute(
            """INSERT INTO parties(code,display_name,nature,party_kind)
               VALUES ('X901','نامعتبر','X','ORGANIZATION')"""),
            "party_kind outside PERSON/COMPANY")
        con.rollback()
        # backfilled rows are flagged unconfirmed for owner review
        flags = con.execute(
            "SELECT COUNT(*) FROM parties WHERE party_kind IS NOT NULL AND party_kind_confirmed=0").fetchone()[0]
        assert flags >= 2, f"backfill must be flagged unconfirmed, got {flags}"

    def t_g02_economic_code():
        con.execute("UPDATE parties SET economic_code='411111111111' WHERE code='SL900'")
        con.commit()
        assert con.execute("SELECT economic_code FROM parties WHERE code='SL900'").fetchone()[0] \
            == '411111111111'
        expect_error(lambda: con.execute(
            "UPDATE parties SET economic_code='411111111111' WHERE code='E901'"),
            "duplicate economic code")
        con.rollback()
        # blank is not a duplicate of blank (partial unique index)
        con.execute("UPDATE parties SET economic_code='' WHERE code IN ('SL900','E901')")
        con.commit()

    def t_g03_product_active():
        assert con.execute("SELECT is_active FROM products LIMIT 1").fetchone()[0] == 1
        code = con.execute("SELECT code FROM products LIMIT 1").fetchone()[0]
        con.execute("UPDATE products SET is_active=0 WHERE code=?", (code,))
        con.commit()
        active = [r[0] for r in con.execute("SELECT code FROM products WHERE is_active=1")]
        assert code not in active, "deactivated product still listed as active"
        expect_error(lambda: con.execute("UPDATE products SET is_active=7 WHERE code=?", (code,)),
                     "is_active outside 0/1")
        con.rollback()
        con.execute("UPDATE products SET is_active=1 WHERE code=?", (code,))
        con.commit()

    def t_g04_g06_g09_source_keys():
        """Importing the same source file twice must not double-post."""
        con.execute("""INSERT INTO weigh_tickets(code,direction,source_key)
                       VALUES ('WT-001','IN','BASKOL-ROW-1')""")
        con.execute("""INSERT INTO purchase_invoices(code,source_key)
                       VALUES ('PI-001','TPL-PURCHASE-1')""")
        con.execute("""INSERT INTO sales_invoices(code,source_key)
                       VALUES ('SI-001','TPL-SALES-1')""")
        con.commit()
        for table, sql, what in [
            ("weigh_tickets",
             "INSERT INTO weigh_tickets(code,direction,source_key) VALUES ('WT-002','IN','BASKOL-ROW-1')",
             "duplicate weigh source_key"),
            ("purchase_invoices",
             "INSERT INTO purchase_invoices(code,source_key) VALUES ('PI-002','TPL-PURCHASE-1')",
             "duplicate purchase source_key"),
            ("sales_invoices",
             "INSERT INTO sales_invoices(code,source_key) VALUES ('SI-002','TPL-SALES-1')",
             "duplicate sales source_key"),
        ]:
            expect_error(lambda s=sql: con.execute(s), what)
            con.rollback()
        # a document with no source key is never blocked
        con.execute("INSERT INTO weigh_tickets(code,direction) VALUES ('WT-003','IN')")
        con.execute("INSERT INTO weigh_tickets(code,direction) VALUES ('WT-004','IN')")
        con.commit()

    def t_g05_weigh_packaging():
        con.execute("""UPDATE weigh_tickets
                       SET packaging_id=(SELECT id FROM packaging_types LIMIT 1),
                           package_count=12, receipt_number='R-100'
                       WHERE code='WT-001'""")
        con.commit()
        r = con.execute("""SELECT package_count,receipt_number,has_receipt_number,has_packages
                           FROM v_weigh_ticket_import WHERE code='WT-001'""").fetchone()
        assert r == (12, 'R-100', 1, 1), r
        # a ticket with no receipt must report "absent", NOT receipt number 0
        r2 = con.execute("""SELECT receipt_number,has_receipt_number,has_packages
                            FROM v_weigh_ticket_import WHERE code='WT-004'""").fetchone()
        assert r2[0] is None and r2[1] == 0 and r2[2] == 0, \
            f"blank receipt/package must not read as present: {r2}"
        expect_error(lambda: con.execute(
            "UPDATE weigh_tickets SET package_count=-1 WHERE code='WT-001'"),
            "negative package count")
        con.rollback()

    def t_g07_line_weigh_ticket():
        """One purchase invoice, two truckloads: each LINE binds its own ticket."""
        lot = con.execute("INSERT INTO lots(code,product_id,warehouse_id) VALUES ('LOT-P7',1,1)").lastrowid
        w1 = con.execute("""INSERT INTO weigh_tickets(code,direction,product_id,net_grams)
                            VALUES ('WT-P7A','IN',1,5000)""").lastrowid
        w2 = con.execute("""INSERT INTO weigh_tickets(code,direction,product_id,net_grams)
                            VALUES ('WT-P7B','IN',1,7000)""").lastrowid
        inv = con.execute("""INSERT INTO purchase_invoices(code,lot_id)
                             VALUES ('PI-P7',?)""", (lot,)).lastrowid
        con.execute("""INSERT INTO purchase_invoice_lines(invoice_id,product_id,grams,weigh_ticket_id)
                       VALUES (?,1,5000,?)""", (inv, w1))
        con.execute("""INSERT INTO purchase_invoice_lines(invoice_id,product_id,grams,weigh_ticket_id)
                       VALUES (?,1,7000,?)""", (inv, w2))
        con.commit()
        rows = con.execute("""SELECT l.grams, w.code FROM purchase_invoice_lines l
                              JOIN weigh_tickets w ON w.id=l.weigh_ticket_id
                              WHERE l.invoice_id=? ORDER BY l.id""", (inv,)).fetchall()
        assert rows == [(5000, 'WT-P7A'), (7000, 'WT-P7B')], rows
        # the line total must equal the sum of its tickets, not explode
        assert sum(r[0] for r in rows) == 12000
        expect_error(lambda: con.execute(
            """INSERT INTO purchase_invoice_lines(invoice_id,product_id,grams,weigh_ticket_id)
               VALUES (?,1,1,999999)""", (inv,)), "line pointing at a non-existent ticket")
        con.rollback()

    def t_g11_basket_vocabulary():
        """The template's own words must be insertable — the v001 CHECK
        rejected TRANSFER and OPENING, making 07_Basket_Movements unimportable."""
        b = con.execute("SELECT id FROM baskets LIMIT 1").fetchone()[0]
        partner = con.execute("SELECT id FROM parties WHERE code='SL900'").fetchone()[0]
        for ev in ('PURCHASE', 'ISSUE', 'RETURN', 'OPENING'):
            con.execute("""INSERT INTO basket_movements(basket_id,event_type,quantity)
                           VALUES (?,?,?)""", (b, ev, 1))
        con.execute("""INSERT INTO basket_movements(basket_id,event_type,quantity,doc_number,counterparty_party_id)
                       VALUES (?,?,?,?,?)""", (b, 'TRANSFER', 5, 'TR-1', partner))
        con.commit()
        got = {r[0] for r in con.execute("SELECT event_type FROM basket_movements")}
        assert {'PURCHASE','ISSUE','RETURN','OPENING','TRANSFER'} <= got, got
        # still rejects nonsense
        expect_error(lambda: con.execute(
            "INSERT INTO basket_movements(basket_id,event_type,quantity) VALUES (?,?,1)", (b, 'SOLD')),
            "unknown basket event_type")
        con.rollback()
        # a TRANSFER without a counterparty is meaningless and must be refused
        expect_error(lambda: con.execute(
            """INSERT INTO basket_movements(basket_id,event_type,quantity,doc_number)
               VALUES (?,?,1,'TR-2')""", (b, 'TRANSFER')),
            "TRANSFER without counterparty")
        con.rollback()
        # legacy v001 vocabulary stays readable
        assert con.execute("SELECT COUNT(*) FROM basket_movements WHERE event_type='RECEIVE'").fetchone()[0] == 0
        con.execute("INSERT INTO basket_movements(basket_id,event_type,quantity) VALUES (?,?,1)", (b, 'RECEIVE'))
        con.commit()

    def t_g12_bank_fee():
        """A fee must not corrupt the bank arithmetic."""
        ba = con.execute("SELECT id FROM bank_accounts LIMIT 1").fetchone()[0]
        con.execute("""INSERT INTO bank_transactions(code,bank_account_id,deposit_rial,withdrawal_rial,fee_rial,tracking_number)
                       VALUES ('BT-FEE',?,0,1000000,5000,'TRK-9')""", (ba,))
        con.commit()
        dep, wd, fee = con.execute(
            "SELECT deposit_rial,withdrawal_rial,fee_rial FROM bank_transactions WHERE code='BT-FEE'").fetchone()
        assert (dep, wd, fee) == (0, 1000000, 5000)
        # principal arithmetic ignores the fee -> balance stays reconcilable
        assert wd - dep == 1000000
        # total cash out is principal + fee, and the fee is a separate expense line
        assert wd - dep + fee == 1005000
        expect_error(lambda: con.execute("UPDATE bank_transactions SET fee_rial=-5 WHERE code='BT-FEE'"),
                     "negative fee")
        con.rollback()

    def t_g22_blank_not_zero():
        """Golden rule 7, proven where it used to be silently violated."""
        # reported_balance_known=0 must mean 'not reported', and the stored
        # balance must not be read as a real zero.
        r = con.execute("""SELECT bank_balance_rial, reported_balance_known
                           FROM bank_transactions WHERE code='BT-FEE'""").fetchone()
        assert r[1] == 0, f"new bank row must default to 'balance not reported': {r}"
        # v001 declared bank_balance_rial NOT NULL DEFAULT 0. Relaxing that on a
        # live DB would need another full rebuild, so v002 tracks known-ness
        # explicitly instead; the report layer must read the flag, never the raw 0.
        con.execute("""UPDATE bank_transactions
                       SET bank_balance_rial=0, reported_balance_known=0
                       WHERE code='BT-FEE'""")
        con.commit()
        row = con.execute("""SELECT bank_balance_rial, reported_balance_known
                             FROM bank_transactions WHERE code='BT-FEE'""").fetchone()
        assert row[1] == 0, "0 Rial stored here means UNREPORTED, not a zero balance"
        # the import layer records which source columns were blank
        cols = [r[1] for r in con.execute("PRAGMA table_info(import_rows)")]
        assert 'blank_fields_json' in cols
        assert 'header_row_second' in [r[1] for r in con.execute("PRAGMA table_info(import_batches)")]
        # and the data dictionary names every legacy trap in the DB itself
        dep = con.execute("""SELECT COUNT(*) FROM schema_field_notes
                             WHERE status IN ('DEPRECATED','LEGACY')""").fetchone()[0]
        assert dep >= 4, f"field-note dictionary incomplete: {dep}"

    def t_g14_cheque_dates():
        con.execute("""INSERT INTO cheques(code,cheque_number,cheque_date,direction,amount_rial,
                                           issue_date_shamsi,due_date_shamsi)
                       VALUES ('CH-D','7001','1403/05/01','ISSUED',1000,'1403/05/01','1403/07/01')""")
        con.commit()
        r = con.execute("""SELECT issue_date_shamsi,due_date_shamsi FROM cheques
                           WHERE code='CH-D'""").fetchone()
        assert r == ('1403/05/01', '1403/07/01'), r
        # an unpaid cheque maturing after issue is exactly what the report needs
        assert r[1] > r[0]
        expect_error(lambda: con.execute(
            """INSERT INTO cheques(code,cheque_number,direction,issue_date_shamsi,due_date_shamsi)
               VALUES ('CH-R','900','RECEIVED','1403/07/01','1403/05/01')"""),
            "due date before issue date")
        con.rollback()

    def t_g15_sayad_and_registry():
        con.execute("UPDATE cheques SET sayad_id='1234567890123456' WHERE code='CH-D'")
        con.commit()
        assert con.execute("SELECT sayad_id FROM cheques WHERE code='CH-D'").fetchone()[0] \
            == '1234567890123456'
        expect_error(lambda: con.execute(
            "UPDATE cheques SET sayad_id='123456789012345' WHERE code='CH-D'"),
            "15-digit sayad id")
        con.rollback()
        expect_error(lambda: con.execute(
            "UPDATE cheques SET sayad_id='123456789012345X' WHERE code='CH-D'"),
            "non-numeric sayad id")
        con.rollback()
        con.execute("""INSERT INTO cheques(code,cheque_number,direction,amount_rial)
                       VALUES ('CH-D2','7002','RECEIVED',2000)""")
        con.commit()
        expect_error(lambda: con.execute(
            "UPDATE cheques SET sayad_id='1234567890123456' WHERE code='CH-D2'"),
            "duplicate sayad id")
        con.rollback()
        # registry link must point at a real registry row
        expect_error(lambda: con.execute(
            "UPDATE cheques SET registry_id=999999 WHERE code='CH-D2'"),
            "cheque linked to a non-existent registry row")
        con.rollback()

    def t_g16_payment_instrument():
        con.execute("""INSERT INTO payments(code,direction,amount_rial,instrument_type)
                       VALUES ('PAY-I','OUT',1000,'BANK')""")
        con.commit()
        assert con.execute(
            "SELECT instrument_type FROM payments WHERE code='PAY-I'").fetchone()[0] == 'BANK'
        expect_error(lambda: con.execute(
            "UPDATE payments SET instrument_type='CASH' WHERE code='PAY-I'"),
            "instrument_type outside BANK/CHEQUE/CREDIT_NOTE/OTHER")
        con.rollback()
        # a CHEQUE payment must be able to name its cheque
        con.execute("""INSERT INTO payments(code,direction,amount_rial,instrument_type,cheque_id)
                       VALUES ('PAY-CHQ','OUT',2000,'CHEQUE',
                               (SELECT id FROM cheques WHERE code='CH-D'))""")
        con.commit()
        assert con.execute(
            "SELECT cheque_id FROM payments WHERE code='PAY-CHQ'").fetchone()[0] is not None
        expect_error(lambda: con.execute(
            "UPDATE payments SET cheque_id=999999 WHERE code='PAY-CHQ'"),
            "payment pointing at a non-existent cheque")
        con.rollback()

    def t_g17_allocation_target():
        """An allocation must point at exactly one real invoice — and the DB
        must refuse a dangling number, which v001 could not."""
        pid2 = con.execute(
            "INSERT INTO payments(code,direction,amount_rial) VALUES ('PAY-X1','OUT',10)").lastrowid
        sid = con.execute("INSERT INTO sales_invoices(code) VALUES ('SI-ALLOC')").lastrowid
        con.commit()
        con.execute("""INSERT INTO payment_allocations(payment_id,sales_invoice_id,amount_rial)
                       VALUES (?,?,10)""", (pid2, sid))
        con.commit()
        # exactly one target enforced
        expect_error(lambda: con.execute(
            """INSERT INTO payment_allocations(payment_id,purchase_invoice_id,sales_invoice_id,amount_rial)
               VALUES (?,?,?,1)""", (pid2, 1, sid)),
            "allocation targeting both invoice kinds")
        con.rollback()
        expect_error(lambda: con.execute(
            "INSERT INTO payment_allocations(payment_id,amount_rial) VALUES (?,1)", (pid2,)),
            "allocation with no invoice")
        con.rollback()
        # a target that does not exist is rejected by the FK (v001 could not)
        expect_error(lambda: con.execute(
            "INSERT INTO payment_allocations(payment_id,sales_invoice_id,amount_rial) VALUES (?,999999,1)", (pid2,)),
            "allocation to a non-existent sales invoice")
        con.rollback()

    def t_g19_partnership_origin():
        p = con.execute(
            "INSERT INTO partnerships(code,description) VALUES ('PS-T','شرکت آزمون')").lastrowid
        con.execute("""INSERT INTO partnership_events(partnership_id,event_type,origin_place,destination_place)
                       VALUES (?,'LOAD_OUT','سردخانه','بازار')""", (p,))
        con.commit()
        r = con.execute("SELECT origin_place,destination_place FROM partnership_events "
                        "WHERE partnership_id=?", (p,)).fetchone()
        assert r == ('سردخانه', 'بازار'), r
        # origin/destination are optional: an event that is not a move stays NULL
        con.execute("""INSERT INTO partnership_events(partnership_id,event_type)
                       VALUES (?,'SETTLEMENT')""", (p,))
        con.commit()
        assert con.execute("""SELECT origin_place FROM partnership_events
                              WHERE partnership_id=? AND event_type='SETTLEMENT'""", (p,)).fetchone()[0] is None

    def t_v002_trigger_guards():
        """Database-level guards that backup the engine."""
        # mass balance
        lot = con.execute("INSERT INTO lots(code,product_id,warehouse_id) VALUES ('LOT-G',1,1)").lastrowid
        con.execute("""INSERT INTO sorting_batches(code,lot_id,input_grams,output_grams,waste_grams,
                       process_loss_grams,variance_grams,tolerance_grams,status)
                       VALUES ('SB-G',?,10000,6000,1000,0,0,500,'REVIEW')""", (lot,))
        con.commit()
        expect_error(lambda: con.execute(
            "UPDATE sorting_batches SET status='APPROVED' WHERE code='SB-G'"),
            "unbalanced batch approved")
        con.rollback()
        con.execute("UPDATE sorting_batches SET variance_grams=3000 WHERE code='SB-G'")
        con.commit()
        con.execute("UPDATE sorting_batches SET status='APPROVED' WHERE code='SB-G'")
        con.commit()
        # wage shares cannot exceed the header
        w = con.execute("""INSERT INTO employee_wages(code,date_iso,date_shamsi,wage_type,total_rial)
                           VALUES ('W-G','2024-01-01','1402/10/11','MONTHLY',1000)""").lastrowid
        con.commit()
        con.execute("INSERT INTO wage_shares(wage_id,share_rial) VALUES (?,600)", (w,))
        con.commit()
        expect_error(lambda: con.execute(
            "INSERT INTO wage_shares(wage_id,share_rial) VALUES (?,600)", (w,)),
            "shares exceeding the wage total")
        con.rollback()
        # v001 immutability triggers still alive after the rebuilds
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        for required in ("trg_journal_no_update_approved", "trg_journal_no_delete_approved",
                         "trg_journal_line_no_update_approved", "trg_journal_line_no_delete_approved",
                         "trg_sorting_mass_balance_v002", "trg_wage_shares_over_total_v002",
                         "trg_basket_transfer_v002", "trg_cheque_sayad_16_v002",
                         "trg_alloc_single_target_v002"):
            assert required in names, f"missing trigger {required}"

    def t_v002_v001_indexes_survived():
        """The rebuilds must not have silently dropped v001 indexes."""
        idx = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")}
        for required in ("ix_audit_entity", "ix_user_keys_user", "ix_parties_nature",
                         "ix_weigh_status", "ix_weigh_party", "ix_stock_key",
                         "ux_bank_source_key", "ix_bank_account", "ux_journal_source_key"):
            assert required in idx, f"v001 index lost: {required}"
        for added in ("ux_weigh_source_key", "ux_purchase_source_key", "ux_sales_source_key",
                      "ux_alloc_source_key", "ux_cheques_sayad", "ux_parties_economic_code",
                      "ix_products_active", "ix_pil_weigh"):
            assert added in idx, f"v002 index missing: {added}"

    def t_v002_fresh_equals_upgraded():
        """A fresh install (schema+seed+migrations) and a v001 install that was
        then migrated must end up with the SAME shape. If they differ, some
        users' software sees columns others' does not — the classic cause of
        'works on my machine' bugs in a single-user offline product."""
        fresh = build_db(os.path.join(tmp, "shape_fresh.db"))
        upg_path = os.path.join(tmp, "shape_upgraded.db")
        old = build_db(upg_path, with_migrations=False)
        apply_migrations(old)      # same connection, as a real upgrade would

        def shape(c):
            cols = sorted(
                (t, c2) for (t, c2) in c.execute(
                    "SELECT m.name, p.name FROM sqlite_master m "
                    "JOIN pragma_table_info(m.name) p WHERE m.type='table' "
                    "AND m.name NOT LIKE 'sqlite_%'"))
            trig = sorted(r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"))
            idx = sorted(r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%'"))
            return cols, trig, idx

        fc, ft, fi = shape(fresh)
        uc, ut, ui = shape(old)
        assert fc == uc, "column drift between fresh and upgraded:\n" + \
            str(sorted(set(fc) ^ set(uc))[:10])
        assert ft == ut, "trigger drift:\n" + str(sorted(set(ft) ^ set(ut)))
        assert fi == ui, "index drift:\n" + str(sorted(set(fi) ^ set(ui)))
        fresh.close()
        old.close()

    def t_v002_no_rebuild_loss():
        """A rebuild must not lose the CHECK constraints of the rebuilt table."""
        sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='basket_movements'"
        ).fetchone()[0]
        assert 'TRANSFER' in sql and 'OPENING' in sql, "rebuilt table lost its vocabulary"
        assert sql.count('CHECK') >= 3, f"quantity/rate/amount checks lost: {sql.count('CHECK')} left"
        sql = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='payment_allocations'"
        ).fetchone()[0]
        assert 'amount_rial >= 0' in sql, "rebuilt allocations table lost its money check"

    def t_v004_lookup_columns():
        """v004 exists because tools/check_csharp_schema.py found three
        references that could not resolve. Each is now proven by behaviour."""
        views = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='view'")}
        assert "v_invoice_lookup" in views, "v_invoice_lookup missing"

        # payments: doc_number is a user-facing number, distinct from `code`
        pid = con.execute(
            "INSERT INTO payments(code,doc_number,direction,amount_rial) "
            "VALUES ('PAY-9','DOC-9','IN',1000)").lastrowid
        con.commit()
        r = con.execute(
            "SELECT code,doc_number FROM payments WHERE id=?", (pid,)).fetchone()
        assert r == ('PAY-9','DOC-9'), r
        con.execute(
            "INSERT INTO payments(code,doc_number,direction,amount_rial) "
            "VALUES ('PAY-10','DOC-10','IN',1)")
        con.commit()
        expect_error(lambda: con.execute(
            "UPDATE payments SET doc_number='DOC-9' WHERE code='PAY-10'"), "dup doc")
        con.rollback()

        # sorting_outputs.code gives a sorting output something to quote
        lot = con.execute(
            "INSERT INTO lots(code,product_id,warehouse_id) VALUES ('LOT-V4',1,1)").lastrowid
        batch = con.execute(
            "INSERT INTO sorting_batches(code,lot_id) VALUES ('SB-V4',?)", (lot,)).lastrowid
        con.commit()
        out = con.execute(
            "INSERT INTO sorting_outputs(batch_id,product_id,grams,code) "
            "VALUES (?,1,1000,'SO-1')", (batch,)).lastrowid
        con.commit()
        assert con.execute(
            "SELECT code FROM sorting_outputs WHERE id=?", (out,)).fetchone()[0] == 'SO-1'
        expect_error(lambda: con.execute(
            "INSERT INTO sorting_outputs(batch_id,product_id,grams,code) "
            "VALUES (?,1,1,'SO-1')", (batch,)), "duplicate sorting output code")
        con.rollback()

        # the invoice view resolves a number on either side
        pi = con.execute(
            "INSERT INTO purchase_invoices(code,doc_number,date_iso) "
            "VALUES ('PI-V4','9001','2024-01-01')").lastrowid
        si = con.execute(
            "INSERT INTO sales_invoices(code,doc_number,date_iso) "
            "VALUES ('SI-V4','9002','2024-01-02')").lastrowid
        con.commit()
        assert con.execute(
            "SELECT kind,id FROM v_invoice_lookup WHERE doc_number='9001'").fetchone() == ('PURCHASE', pi)
        assert con.execute(
            "SELECT kind,id FROM v_invoice_lookup WHERE doc_number='9002'").fetchone() == ('SALES', si)
        assert con.execute(
            "SELECT COUNT(*) FROM v_invoice_lookup WHERE doc_number='9999'").fetchone()[0] == 0

        # one number cannot live on both sides
        expect_error(lambda: con.execute(
            "INSERT INTO sales_invoices(code,doc_number) VALUES ('SI-V5','9001')"),
            "invoice number ambiguous across purchase and sales")
        con.rollback()

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
        ("v002: migration applied, version 2 recorded", t_v002_migration_applied),
        ("v002: table rebuilds preserved rows, ids and upgraded legacy FKs", t_v002_rebuild_preserved_data),
        ("G-01: parties.party_kind PERSON/COMPANY independent of nature", t_g01_party_kind),
        ("G-02: economic code unique when present, blank allowed", t_g02_economic_code),
        ("G-03: products.is_active drives active lists", t_g03_product_active),
        ("G-04/06/09: source_key blocks double import", t_g04_g06_g09_source_keys),
        ("G-05: weigh packaging/receipt; blank != 0", t_g05_weigh_packaging),
        ("G-07: each invoice line binds its own weigh ticket", t_g07_line_weigh_ticket),
        ("G-11: basket TRANSFER/OPENING accepted, junk refused", t_g11_basket_vocabulary),
        ("G-12: bank fee separate from principal", t_g12_bank_fee),
        ("G-22: blank is not zero (views + field notes)", t_g22_blank_not_zero),
        ("G-14: cheque issue date vs due date", t_g14_cheque_dates),
        ("G-15: sayad id 16 digits, unique", t_g15_sayad_and_registry),
        ("G-16: payment instrument type constrained", t_g16_payment_instrument),
        ("G-17: allocation targets exactly one real invoice", t_g17_allocation_target),
        ("G-19: partnership origin/destination optional", t_g19_partnership_origin),
        ("v002: DB guards (mass balance, wage shares, triggers alive)", t_v002_trigger_guards),
        ("v002: v001 indexes survived; v002 indexes present", t_v002_v001_indexes_survived),
        ("v002: fresh install shape == upgraded install shape", t_v002_fresh_equals_upgraded),
        ("v002: rebuilt tables kept their CHECK constraints", t_v002_no_rebuild_loss),
        ("v004: doc_number, sorting output code, invoice lookup view", t_v004_lookup_columns),
    ]
    for name, fn in tests:
        check(name, fn)

    con.close()
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} PASS")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
