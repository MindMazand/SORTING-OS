-- ============================================================================
-- MAZANDASHT — Schema v006  (006_amount_nullable.sql)
--
-- DEC-NEW-053. The owner's first rule is «خالی ≠ صفر» — blank is not zero.
-- That rule was enforced in the IMPORT ENGINE only. The SCHEMA did the
-- opposite, in fourteen places:
--
--     amount_rial INTEGER NOT NULL DEFAULT 0
--
-- An insert that does not know the amount does not fail — it stores 0. From
-- then on the database cannot distinguish "amount not recorded" from "this
-- transaction is worth zero rials", and every report inherits the confusion.
-- A trial balance of zeros is balanced; a balance sheet of zeros balances.
-- The wrong number is invisible, which is the whole problem.
--
-- HOW IT SURFACED
--
-- tools/test_reports.py tried to construct the "blank is unknown" case and
-- could not: the insert meant to leave an amount empty died with
--     NOT NULL constraint failed: cheques.amount_rial
-- and the variant that succeeded stored 0. The rule was tested at the door
-- and violated in the warehouse.
--
-- WHAT CHANGES
--
-- For every money column (any column whose name contains `_rial`):
--   * drop NOT NULL          -> the unknown becomes representable
--   * drop DEFAULT 0         -> a default is the mechanism that turns
--                               "unknown" into "zero" without anyone deciding
--   * widen the typeof CHECK -> NULL is allowed
--
-- Nothing else changes: same columns, same order, same types, same foreign
-- keys, same non-money defaults. A present amount is still INTEGER, so the
-- "no silent rounding" rule is untouched.
--
-- The tables are REBUILT (create / copy / drop / rename) because SQLite cannot
-- ALTER COLUMN.
--
-- THE DDL IS GENERATED FROM THE LIVE SCHEMA, NOT TYPED BY HAND.
-- A hand-written first attempt guessed the shape of bank_transactions and
-- supplied 26 values to an 11-column table; the migration died on
--     table bank_transactions_new has 11 columns but 26 values were supplied
-- The column count per table is asserted by tools/test_migration_006.py.
--
-- A TRAP IN THIS FILE'S OWN GENERATION: sqlite_master stores the DDL of any
-- table that was itself rebuilt by an earlier migration with the name QUOTED
-- ("basket_movements"), while untouched tables come back unquoted. A string
-- replace on `CREATE TABLE basket_movements` therefore silently misses the
-- quoted one, the table is created under its real name next to the old one,
-- and the migration dies on `table "basket_movements" already exists`. Match
-- on the name, quoted or not; and assert the __new suffix landed.
--
-- ORDERING IS NOT OPTIONAL. SQLite refuses DROP TABLE while any view OR any
-- trigger still references that table — including a trigger sitting on a
-- DIFFERENT table (trg_invoice_number_unique_sales lives on sales_invoices and
-- reads purchase_invoices). So every view and every trigger is dropped first
-- and recreated verbatim at the end. Two failures led here:
--     error in view v_lot_lookup: no such table: main.lots
--     error in trigger trg_invoice_number_unique_sales: no such table:
--         main.purchase_invoices
--
-- NO BEGIN/COMMIT IN THIS FILE. The runner wraps each migration in one
-- transaction and disables foreign keys before it. A file that opens its own
-- transaction fails with "cannot start a transaction within a transaction" —
-- the same trap that bit the audit logger this round.
-- ============================================================================

-- ---- 1. drop every view and trigger ----
-- (every one is recreated verbatim at the end)

DROP VIEW IF EXISTS v_account_balance;
DROP VIEW IF EXISTS v_invoice_lookup;
DROP VIEW IF EXISTS v_journal_balance;
DROP VIEW IF EXISTS v_lot_lookup;
DROP VIEW IF EXISTS v_stock_balance;
DROP VIEW IF EXISTS v_weigh_ticket_import;
DROP TRIGGER IF EXISTS trg_alloc_single_target_v002;
DROP TRIGGER IF EXISTS trg_bank_direction_insert_v003;
DROP TRIGGER IF EXISTS trg_bank_direction_update_v003;
DROP TRIGGER IF EXISTS trg_basket_transfer_party_v002;
DROP TRIGGER IF EXISTS trg_basket_transfer_v002;
DROP TRIGGER IF EXISTS trg_cheque_due_after_issue_upd_v002;
DROP TRIGGER IF EXISTS trg_cheque_due_after_issue_v002;
DROP TRIGGER IF EXISTS trg_cheque_sayad_16_upd_v002;
DROP TRIGGER IF EXISTS trg_cheque_sayad_16_v002;
DROP TRIGGER IF EXISTS trg_invoice_number_unique_purchase;
DROP TRIGGER IF EXISTS trg_invoice_number_unique_sales;
DROP TRIGGER IF EXISTS trg_journal_line_no_delete_approved;
DROP TRIGGER IF EXISTS trg_journal_line_no_update_approved;
DROP TRIGGER IF EXISTS trg_journal_no_delete_approved;
DROP TRIGGER IF EXISTS trg_journal_no_update_approved;
DROP TRIGGER IF EXISTS trg_sorting_mass_balance_v002;
DROP TRIGGER IF EXISTS trg_wage_shares_over_total_v002;

-- ---- 2. rebuild each table; money columns become nullable ----
-- lots: 9 columns
CREATE TABLE lots__new (                        -- محموله / Lot
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    weigh_ticket_id INTEGER REFERENCES weigh_tickets(id),
    product_id     INTEGER REFERENCES products(id),
    grade_id       INTEGER REFERENCES grades(id),
    packaging_id   INTEGER REFERENCES packaging_types(id),
    warehouse_id   INTEGER REFERENCES warehouses(id),
    quantity_grams INTEGER NOT NULL DEFAULT 0 CHECK (typeof(quantity_grams)='integer'),
    status         TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED'))
);
INSERT INTO lots__new (id, code, weigh_ticket_id, product_id, grade_id, packaging_id, warehouse_id, quantity_grams, status) SELECT id, code, weigh_ticket_id, product_id, grade_id, packaging_id, warehouse_id, quantity_grams, status FROM lots;
DROP TABLE lots;
ALTER TABLE lots__new RENAME TO lots;

-- purchase_invoices: 15 columns
CREATE TABLE purchase_invoices__new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    doc_number     TEXT NOT NULL DEFAULT '',
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    party_id       INTEGER REFERENCES parties(id),
    weigh_ticket_id INTEGER REFERENCES weigh_tickets(id),
    lot_id         INTEGER REFERENCES lots(id),
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason    TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id),
    approved_by    INTEGER REFERENCES users(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
, source_key TEXT);
INSERT INTO purchase_invoices__new (id, code, doc_number, date_iso, date_shamsi, party_id, weigh_ticket_id, lot_id, status, void_reason, created_by, approved_by, description, created_at, source_key) SELECT id, code, doc_number, date_iso, date_shamsi, party_id, weigh_ticket_id, lot_id, status, void_reason, created_by, approved_by, description, created_at, source_key FROM purchase_invoices;
DROP TABLE purchase_invoices;
ALTER TABLE purchase_invoices__new RENAME TO purchase_invoices;

-- sales_invoices: 15 columns
CREATE TABLE sales_invoices__new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    doc_number     TEXT NOT NULL DEFAULT '',
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    party_id       INTEGER REFERENCES parties(id),
    lot_id         INTEGER REFERENCES lots(id),
    sorting_batch_id INTEGER REFERENCES sorting_batches(id),
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason    TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id),
    approved_by    INTEGER REFERENCES users(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
, source_key TEXT);
INSERT INTO sales_invoices__new (id, code, doc_number, date_iso, date_shamsi, party_id, lot_id, sorting_batch_id, status, void_reason, created_by, approved_by, description, created_at, source_key) SELECT id, code, doc_number, date_iso, date_shamsi, party_id, lot_id, sorting_batch_id, status, void_reason, created_by, approved_by, description, created_at, source_key FROM sales_invoices;
DROP TABLE sales_invoices;
ALTER TABLE sales_invoices__new RENAME TO sales_invoices;

-- purchase_invoice_lines: 12 columns
CREATE TABLE purchase_invoice_lines__new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id),
    grams          INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer'),
    rate_rial_per_kg INTEGER DEFAULT NULL CHECK (rate_rial_per_kg IS NULL OR typeof(rate_rial_per_kg)='integer'),
    gross_rial     INTEGER DEFAULT NULL CHECK (gross_rial IS NULL OR typeof(gross_rial)='integer'),
    discount_rial  INTEGER DEFAULT NULL CHECK (discount_rial IS NULL OR typeof(discount_rial)='integer'),
    freight_rial   INTEGER DEFAULT NULL CHECK (freight_rial IS NULL OR typeof(freight_rial)='integer'),
    commission_rial INTEGER DEFAULT NULL CHECK (commission_rial IS NULL OR typeof(commission_rial)='integer'),
    adjustments_rial INTEGER DEFAULT NULL CHECK (adjustments_rial IS NULL OR typeof(adjustments_rial)='integer'),
    net_rial       INTEGER DEFAULT NULL CHECK (net_rial IS NULL OR typeof(net_rial)='integer')
, weigh_ticket_id INTEGER REFERENCES weigh_tickets(id));
INSERT INTO purchase_invoice_lines__new (id, invoice_id, product_id, grams, rate_rial_per_kg, gross_rial, discount_rial, freight_rial, commission_rial, adjustments_rial, net_rial, weigh_ticket_id) SELECT id, invoice_id, product_id, grams, rate_rial_per_kg, gross_rial, discount_rial, freight_rial, commission_rial, adjustments_rial, net_rial, weigh_ticket_id FROM purchase_invoice_lines;
DROP TABLE purchase_invoice_lines;
ALTER TABLE purchase_invoice_lines__new RENAME TO purchase_invoice_lines;

-- sales_invoice_lines: 14 columns
CREATE TABLE sales_invoice_lines__new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id),
    grade_id       INTEGER REFERENCES grades(id),
    packaging_id   INTEGER REFERENCES packaging_types(id),
    grams          INTEGER NOT NULL DEFAULT 0 CHECK (typeof(grams)='integer'),
    rate_rial_per_kg INTEGER DEFAULT NULL CHECK (rate_rial_per_kg IS NULL OR typeof(rate_rial_per_kg)='integer'),
    gross_rial     INTEGER DEFAULT NULL CHECK (gross_rial IS NULL OR typeof(gross_rial)='integer'),
    discount_rial  INTEGER DEFAULT NULL CHECK (discount_rial IS NULL OR typeof(discount_rial)='integer'),
    freight_rial   INTEGER DEFAULT NULL CHECK (freight_rial IS NULL OR typeof(freight_rial)='integer'),
    commission_rial INTEGER DEFAULT NULL CHECK (commission_rial IS NULL OR typeof(commission_rial)='integer'),
    other_costs_rial INTEGER DEFAULT NULL CHECK (other_costs_rial IS NULL OR typeof(other_costs_rial)='integer'),
    net_rial       INTEGER DEFAULT NULL CHECK (net_rial IS NULL OR typeof(net_rial)='integer')
, sorting_output_id INTEGER REFERENCES sorting_outputs(id));
INSERT INTO sales_invoice_lines__new (id, invoice_id, product_id, grade_id, packaging_id, grams, rate_rial_per_kg, gross_rial, discount_rial, freight_rial, commission_rial, other_costs_rial, net_rial, sorting_output_id) SELECT id, invoice_id, product_id, grade_id, packaging_id, grams, rate_rial_per_kg, gross_rial, discount_rial, freight_rial, commission_rial, other_costs_rial, net_rial, sorting_output_id FROM sales_invoice_lines;
DROP TABLE sales_invoice_lines;
ALTER TABLE sales_invoice_lines__new RENAME TO sales_invoice_lines;

-- payments: 18 columns
CREATE TABLE payments__new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT NOT NULL UNIQUE,
    party_id       INTEGER REFERENCES parties(id),
    bank_account_id INTEGER REFERENCES bank_accounts(id),
    txn_type_id    INTEGER REFERENCES txn_types(id),
    direction      TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
    amount_rial    INTEGER DEFAULT NULL CHECK (amount_rial IS NULL OR typeof(amount_rial)='integer'),
    date_iso      TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason    TEXT NOT NULL DEFAULT '',
    created_by     INTEGER REFERENCES users(id),
    approved_by    INTEGER REFERENCES users(id),
    description    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
, instrument_type TEXT
    CHECK (instrument_type IS NULL OR instrument_type IN ('BANK','CHEQUE','CREDIT_NOTE','OTHER')), cheque_id INTEGER REFERENCES cheques(id), doc_number TEXT);
INSERT INTO payments__new (id, code, party_id, bank_account_id, txn_type_id, direction, amount_rial, date_iso, date_shamsi, status, void_reason, created_by, approved_by, description, created_at, instrument_type, cheque_id, doc_number) SELECT id, code, party_id, bank_account_id, txn_type_id, direction, amount_rial, date_iso, date_shamsi, status, void_reason, created_by, approved_by, description, created_at, instrument_type, cheque_id, doc_number FROM payments;
DROP TABLE payments;
ALTER TABLE payments__new RENAME TO payments;

-- cheques: 18 columns
CREATE TABLE cheques__new (                     -- Cheques.xlsx; ISSUED and RECEIVED are independent flows
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL UNIQUE,
    cheque_number      TEXT NOT NULL,
    bank_account_id    INTEGER REFERENCES bank_accounts(id),
    cheque_date        TEXT NOT NULL DEFAULT '',
    amount_rial        INTEGER DEFAULT NULL CHECK (amount_rial IS NULL OR typeof(amount_rial)='integer'),
    beneficiary_party_id INTEGER REFERENCES parties(id),
    direction          TEXT NOT NULL CHECK (direction IN ('ISSUED','RECEIVED')),
    status             TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','PAID','COLLECTED','RETURNED','VOIDED')),
    paid_date          TEXT NOT NULL DEFAULT '',
    description        TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
, issue_date_shamsi TEXT, due_date_shamsi TEXT, sayad_id TEXT, registry_id INTEGER REFERENCES cheques_registry(id), source_key TEXT, doc_number TEXT);
INSERT INTO cheques__new (id, code, cheque_number, bank_account_id, cheque_date, amount_rial, beneficiary_party_id, direction, status, paid_date, description, created_at, issue_date_shamsi, due_date_shamsi, sayad_id, registry_id, source_key, doc_number) SELECT id, code, cheque_number, bank_account_id, cheque_date, amount_rial, beneficiary_party_id, direction, status, paid_date, description, created_at, issue_date_shamsi, due_date_shamsi, sayad_id, registry_id, source_key, doc_number FROM cheques;
DROP TABLE cheques;
ALTER TABLE cheques__new RENAME TO cheques;

-- bank_transactions: 26 columns
CREATE TABLE bank_transactions__new (           -- Transactions.xlsx Entry (single engine)
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    code               TEXT NOT NULL UNIQUE,
    bank_account_id    INTEGER NOT NULL REFERENCES bank_accounts(id),
    party_id           INTEGER REFERENCES parties(id),
    txn_type_id        INTEGER REFERENCES txn_types(id),
    main_group_id      INTEGER REFERENCES main_groups(id),
    sub_group_id       INTEGER REFERENCES sub_groups(id),
    date_iso          TEXT NOT NULL DEFAULT '',
    date_shamsi        TEXT NOT NULL DEFAULT '',
    time               TEXT NOT NULL DEFAULT '',
    deposit_rial       INTEGER DEFAULT NULL CHECK (deposit_rial IS NULL OR typeof(deposit_rial)='integer'),
    withdrawal_rial    INTEGER DEFAULT NULL CHECK (withdrawal_rial IS NULL OR typeof(withdrawal_rial)='integer'),
    bank_balance_rial  INTEGER DEFAULT NULL CHECK (bank_balance_rial IS NULL OR typeof(bank_balance_rial)='integer'),
    system_balance_rial INTEGER DEFAULT NULL CHECK (system_balance_rial IS NULL OR typeof(system_balance_rial)='integer'),
    status             TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW','APPROVED','VOIDED')),
    void_reason        TEXT NOT NULL DEFAULT '',
    cheque_number      TEXT NOT NULL DEFAULT '',
    source_key         TEXT NOT NULL DEFAULT '',   -- idempotency key (duplicate control)
    description        TEXT NOT NULL DEFAULT '',
    created_by         INTEGER REFERENCES users(id),
    approved_by        INTEGER REFERENCES users(id),
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
, fee_rial INTEGER DEFAULT NULL
    CHECK (fee_rial IS NULL OR (typeof(fee_rial)='integer' AND fee_rial >= 0)), tracking_number TEXT, reported_balance_known INTEGER NOT NULL DEFAULT 0
    CHECK (reported_balance_known IN (0,1)), direction TEXT
    CHECK (direction IS NULL OR direction IN ('IN','OUT')));
INSERT INTO bank_transactions__new (id, code, bank_account_id, party_id, txn_type_id, main_group_id, sub_group_id, date_iso, date_shamsi, time, deposit_rial, withdrawal_rial, bank_balance_rial, system_balance_rial, status, void_reason, cheque_number, source_key, description, created_by, approved_by, created_at, fee_rial, tracking_number, reported_balance_known, direction) SELECT id, code, bank_account_id, party_id, txn_type_id, main_group_id, sub_group_id, date_iso, date_shamsi, time, deposit_rial, withdrawal_rial, bank_balance_rial, system_balance_rial, status, void_reason, cheque_number, source_key, description, created_by, approved_by, created_at, fee_rial, tracking_number, reported_balance_known, direction FROM bank_transactions;
DROP TABLE bank_transactions;
ALTER TABLE bank_transactions__new RENAME TO bank_transactions;

-- basket_movements: 17 columns
CREATE TABLE basket_movements__new (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    basket_id      INTEGER NOT NULL REFERENCES baskets(id),
    party_id       INTEGER REFERENCES parties(id),
    event_type     TEXT NOT NULL CHECK (event_type IN
                       ('PURCHASE','ISSUE','RETURN','TRANSFER','OPENING','RECEIVE')),
    quantity       INTEGER NOT NULL DEFAULT 0,
    rate_rial      INTEGER DEFAULT NULL CHECK (rate_rial IS NULL OR typeof(rate_rial)='integer'),
    amount_rial    INTEGER DEFAULT NULL CHECK (amount_rial IS NULL OR typeof(amount_rial)='integer'),
    balance_rial   INTEGER DEFAULT NULL CHECK (balance_rial IS NULL OR typeof(balance_rial)='integer'),
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    doc_number     TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    -- G-19 pattern reused: a TRANSFER has a counterparty location.
    counterparty_party_id INTEGER REFERENCES parties(id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
, source_key TEXT, from_warehouse_id INTEGER REFERENCES warehouses(id), to_warehouse_id INTEGER REFERENCES warehouses(id));
INSERT INTO basket_movements__new (id, basket_id, party_id, event_type, quantity, rate_rial, amount_rial, balance_rial, date_iso, date_shamsi, doc_number, description, counterparty_party_id, created_at, source_key, from_warehouse_id, to_warehouse_id) SELECT id, basket_id, party_id, event_type, quantity, rate_rial, amount_rial, balance_rial, date_iso, date_shamsi, doc_number, description, counterparty_party_id, created_at, source_key, from_warehouse_id, to_warehouse_id FROM basket_movements;
DROP TABLE basket_movements;
ALTER TABLE basket_movements__new RENAME TO basket_movements;

-- journal_lines: 6 columns
CREATE TABLE journal_lines__new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    journal_id  INTEGER NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    debit_rial  INTEGER DEFAULT NULL CHECK (debit_rial IS NULL OR (typeof(debit_rial)='integer' AND debit_rial >= 0)),
    credit_rial INTEGER DEFAULT NULL CHECK (credit_rial IS NULL OR (typeof(credit_rial)='integer' AND credit_rial >= 0)),
    description TEXT NOT NULL DEFAULT '',
    CHECK (debit_rial = 0 OR credit_rial = 0)   -- a line is debit XOR credit
);
INSERT INTO journal_lines__new (id, journal_id, account_id, debit_rial, credit_rial, description) SELECT id, journal_id, account_id, debit_rial, credit_rial, description FROM journal_lines;
DROP TABLE journal_lines;
ALTER TABLE journal_lines__new RENAME TO journal_lines;

-- ---- 3. indexes ON THE REBUILT TABLES, plus every trigger ----
-- Only indexes on tables dropped above are listed: DROP TABLE removed
-- them. An index on an untouched table still exists, and recreating
-- it fails with `index ix_audit_entity already exists`.
CREATE INDEX ix_bank_account ON bank_transactions(bank_account_id, date_iso);
CREATE INDEX ix_pil_weigh ON purchase_invoice_lines(weigh_ticket_id);
CREATE INDEX ix_sil_sortout ON sales_invoice_lines(sorting_output_id);
CREATE UNIQUE INDEX ux_bank_source_key ON bank_transactions(source_key) WHERE source_key <> '';
CREATE UNIQUE INDEX ux_basket_source_key
    ON basket_movements(source_key) WHERE source_key IS NOT NULL AND source_key <> '';
CREATE UNIQUE INDEX ux_cheques_sayad ON cheques(sayad_id)
    WHERE sayad_id IS NOT NULL AND sayad_id <> '';
CREATE UNIQUE INDEX ux_cheques_source_key
    ON cheques(source_key) WHERE source_key IS NOT NULL AND source_key <> '';
CREATE UNIQUE INDEX ux_payments_doc_number
    ON payments(doc_number) WHERE doc_number IS NOT NULL AND doc_number <> '';
CREATE UNIQUE INDEX ux_purchase_source_key ON purchase_invoices(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';
CREATE UNIQUE INDEX ux_sales_source_key ON sales_invoices(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';
CREATE TRIGGER trg_alloc_single_target_v002
BEFORE INSERT ON payment_allocations
WHEN (NEW.purchase_invoice_id IS NOT NULL) + (NEW.sales_invoice_id IS NOT NULL)
   + (CASE WHEN NEW.invoice_id IS NOT NULL THEN 1 ELSE 0 END) <> 1
BEGIN
    SELECT RAISE(ABORT,
        'an allocation must reference exactly one invoice (purchase XOR sales XOR legacy)');
END;
CREATE TRIGGER trg_bank_direction_insert_v003
BEFORE INSERT ON bank_transactions
WHEN NEW.direction IS NOT NULL
 AND ((NEW.direction = 'IN'  AND NEW.withdrawal_rial > 0)
   OR (NEW.direction = 'OUT' AND NEW.deposit_rial > 0))
BEGIN
    SELECT RAISE(ABORT, 'bank direction contradicts the deposit/withdrawal amounts');
END;
CREATE TRIGGER trg_bank_direction_update_v003
BEFORE UPDATE OF direction, deposit_rial, withdrawal_rial ON bank_transactions
WHEN NEW.direction IS NOT NULL
 AND ((NEW.direction = 'IN'  AND NEW.withdrawal_rial > 0)
   OR (NEW.direction = 'OUT' AND NEW.deposit_rial > 0))
BEGIN
    SELECT RAISE(ABORT, 'bank direction contradicts the deposit/withdrawal amounts');
END;
CREATE TRIGGER trg_basket_transfer_party_v002
BEFORE INSERT ON basket_movements
WHEN NEW.event_type = 'TRANSFER' AND NEW.counterparty_party_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'basket TRANSFER requires a counterparty party');
END;
CREATE TRIGGER trg_basket_transfer_v002
BEFORE INSERT ON basket_movements
WHEN NEW.event_type = 'TRANSFER' AND (NEW.doc_number IS NULL OR NEW.doc_number = '')
BEGIN
    SELECT RAISE(ABORT, 'basket TRANSFER requires a document number');
END;
CREATE TRIGGER trg_cheque_due_after_issue_upd_v002
BEFORE UPDATE OF issue_date_shamsi, due_date_shamsi ON cheques
WHEN COALESCE(NEW.issue_date_shamsi,'') <> '' AND COALESCE(NEW.due_date_shamsi,'') <> ''
 AND NEW.due_date_shamsi < NEW.issue_date_shamsi
BEGIN
    SELECT RAISE(ABORT, 'cheque due date cannot be earlier than its issue date');
END;
CREATE TRIGGER trg_cheque_due_after_issue_v002
BEFORE INSERT ON cheques
WHEN COALESCE(NEW.issue_date_shamsi,'') <> '' AND COALESCE(NEW.due_date_shamsi,'') <> ''
 AND NEW.due_date_shamsi < NEW.issue_date_shamsi
BEGIN
    SELECT RAISE(ABORT, 'cheque due date cannot be earlier than its issue date');
END;
CREATE TRIGGER trg_cheque_sayad_16_upd_v002
BEFORE UPDATE OF sayad_id ON cheques
WHEN COALESCE(NEW.sayad_id,'') <> ''
 AND (length(NEW.sayad_id) <> 16 OR NEW.sayad_id GLOB '*[^0-9]*')
BEGIN
    SELECT RAISE(ABORT, 'sayad_id must be exactly 16 digits');
END;
CREATE TRIGGER trg_cheque_sayad_16_v002
BEFORE INSERT ON cheques
WHEN COALESCE(NEW.sayad_id,'') <> ''
 AND (length(NEW.sayad_id) <> 16 OR NEW.sayad_id GLOB '*[^0-9]*')
BEGIN
    SELECT RAISE(ABORT, 'sayad_id must be exactly 16 digits');
END;
CREATE TRIGGER trg_invoice_number_unique_purchase
BEFORE INSERT ON purchase_invoices
WHEN COALESCE(NEW.doc_number,'') <> ''
 AND EXISTS (SELECT 1 FROM sales_invoices WHERE doc_number = NEW.doc_number)
BEGIN
    SELECT RAISE(ABORT, 'شماره فاکتور در فاکتورهای فروش هم وجود دارد؛ شماره سند باید یکتا باشد');
END;
CREATE TRIGGER trg_invoice_number_unique_sales
BEFORE INSERT ON sales_invoices
WHEN COALESCE(NEW.doc_number,'') <> ''
 AND EXISTS (SELECT 1 FROM purchase_invoices WHERE doc_number = NEW.doc_number)
BEGIN
    SELECT RAISE(ABORT, 'شماره فاکتور در فاکتورهای خرید هم وجود دارد؛ شماره سند باید یکتا باشد');
END;
CREATE TRIGGER trg_journal_line_no_delete_approved
BEFORE DELETE ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = OLD.journal_id) = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Lines of an approved journal entry cannot be deleted.');
END;
CREATE TRIGGER trg_journal_line_no_update_approved
BEFORE UPDATE ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = OLD.journal_id) = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Lines of an approved journal entry are immutable.');
END;
CREATE TRIGGER trg_journal_no_delete_approved
BEFORE DELETE ON journal_entries
WHEN OLD.status = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Approved journal entries cannot be deleted; use a reversal entry.');
END;
CREATE TRIGGER trg_journal_no_update_approved
BEFORE UPDATE ON journal_entries
WHEN OLD.status = 'APPROVED'
BEGIN
    SELECT RAISE(ABORT, 'Approved journal entries are immutable; use a reversal entry.');
END;
CREATE TRIGGER trg_sorting_mass_balance_v002
BEFORE UPDATE OF status ON sorting_batches
WHEN NEW.status = 'APPROVED'
 AND ABS(NEW.input_grams - (NEW.output_grams + NEW.waste_grams
                            + NEW.process_loss_grams + NEW.variance_grams))
     > NEW.tolerance_grams
BEGIN
    SELECT RAISE(ABORT, 'mass balance violated: Input must equal Outputs + Waste + Loss + Variance within tolerance');
END;
CREATE TRIGGER trg_wage_shares_over_total_v002
BEFORE INSERT ON wage_shares
WHEN (SELECT COALESCE(SUM(share_rial),0) FROM wage_shares WHERE wage_id = NEW.wage_id)
     + NEW.share_rial
   > (SELECT total_rial FROM employee_wages WHERE id = NEW.wage_id)
BEGIN
    SELECT RAISE(ABORT, 'sum of wage shares cannot exceed the wage total');
END;

-- ---- 4. views back, unchanged ----
CREATE VIEW v_account_balance AS
SELECT a.id AS account_id, a.code, a.title, a.account_type,
       COALESCE(SUM(jl.debit_rial),0)  AS total_debit,
       COALESCE(SUM(jl.credit_rial),0) AS total_credit,
       COALESCE(SUM(jl.debit_rial),0) - COALESCE(SUM(jl.credit_rial),0) AS balance_rial
FROM accounts a
LEFT JOIN journal_lines jl ON jl.account_id = a.id
LEFT JOIN journal_entries je ON je.id = jl.journal_id AND je.status = 'APPROVED'
GROUP BY a.id;
CREATE VIEW v_invoice_lookup AS
SELECT 'PURCHASE' AS kind, id, doc_number, code, date_shamsi, party_id
FROM purchase_invoices
WHERE COALESCE(doc_number,'') <> ''
UNION ALL
SELECT 'SALES' AS kind, id, doc_number, code, date_shamsi, party_id
FROM sales_invoices
WHERE COALESCE(doc_number,'') <> '';
CREATE VIEW v_journal_balance AS
SELECT je.id AS journal_id, je.code, je.status,
       COALESCE(SUM(jl.debit_rial),0)  AS total_debit,
       COALESCE(SUM(jl.credit_rial),0) AS total_credit,
       COALESCE(SUM(jl.debit_rial),0) - COALESCE(SUM(jl.credit_rial),0) AS difference
FROM journal_entries je
LEFT JOIN journal_lines jl ON jl.journal_id = je.id
GROUP BY je.id;
CREATE VIEW v_lot_lookup AS
SELECT l.id AS id, l.code AS ref, 'LOT' AS kind
FROM lots l
WHERE COALESCE(l.code, '') <> ''
UNION ALL
SELECT l.id AS id, w.doc_number AS ref, 'WEIGH_TICKET' AS kind
FROM lots l
JOIN weigh_tickets w ON w.id = l.weigh_ticket_id
WHERE COALESCE(w.doc_number, '') <> '';
CREATE VIEW v_stock_balance AS
SELECT product_id, grade_id, packaging_id, warehouse_id, lot_id,
       SUM(CASE WHEN movement_type='IN' THEN quantity_grams
                WHEN movement_type='OUT' THEN -quantity_grams
                ELSE quantity_grams END) AS balance_grams,
       SUM(CASE WHEN movement_type='IN' THEN quantity_count
                WHEN movement_type='OUT' THEN -quantity_count
                ELSE quantity_count END) AS balance_count
FROM stock_movements
GROUP BY product_id, grade_id, packaging_id, warehouse_id, lot_id;
CREATE VIEW v_weigh_ticket_import AS
SELECT w.id, w.code, w.source_key, w.date_shamsi, w.time,
       w.direction, w.operation_id, w.party_id, w.product_id,
       w.packaging_id, w.package_count, w.receipt_number,
       w.basket_count, w.basket_id,
       w.gross_grams, w.tare_grams, w.loss_grams, w.net_grams,
       w.status,
       CASE WHEN COALESCE(w.receipt_number,'') = '' THEN 0 ELSE 1 END AS has_receipt_number,
       CASE WHEN w.package_count = 0 THEN 0 ELSE 1 END                AS has_packages
FROM weigh_tickets w;

-- ---- 5. register ---- 
DELETE FROM schema_migrations WHERE version = 6;
INSERT INTO schema_migrations (version, name)
VALUES (6, 'v006 nullable money columns (blank is not zero)');

INSERT OR REPLACE INTO schema_field_notes (table_name, column_name, status, note) VALUES
 ('cheques','amount_rial','ACTIVE',
  'NULL means the amount was not recorded. 0 means zero rials. Since v006 these are different values; do not COALESCE to 0 in a report.'),
 ('payments','amount_rial','ACTIVE',
  'NULL means the amount was not recorded; 0 means zero. Do not COALESCE.'),
 ('basket_movements','amount_rial','ACTIVE',
  'NULL means the amount was not recorded; 0 means zero. Do not COALESCE.'),
 ('journal_lines','debit_rial','ACTIVE',
  'NULL means no debit side stated by the source; 0 means an explicit zero.'),
 ('journal_lines','credit_rial','ACTIVE',
  'NULL means no credit side stated by the source; 0 means an explicit zero.');

-- End of 006. The runner commits and re-enables foreign keys.
