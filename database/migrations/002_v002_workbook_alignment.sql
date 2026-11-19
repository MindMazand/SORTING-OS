-- ============================================================================
-- MAZANDASHT — Schema v002  (002_v002_workbook_alignment.sql)
-- Aligns schema_v001 with the owner's 11 import templates + 15 operational
-- workbooks (docs/WORKBOOK_SPEC_FA.md ch.10, DEC-NEW-009).
--
-- ---------------------------------------------------------------------------
-- EXECUTION CONTRACT (must be honoured by the runner — see MigrationRunner):
--   * The runner sets PRAGMA foreign_keys=OFF *before* opening the transaction,
--     runs this whole file inside ONE transaction, then runs
--     PRAGMA foreign_key_check and rolls back on any violation.
--   * Therefore this file must NOT contain BEGIN/COMMIT and must NOT rely on
--     a PRAGMA issued inside the transaction (SQLite silently ignores
--     `PRAGMA foreign_keys` inside a transaction).
--   * Table rebuilds are ordered BEFORE the triggers/indexes that sit on the
--     rebuilt tables, otherwise DROP TABLE silently discards them.
--
-- DESIGN RULES
--   1. Money = INTEGER Rial. Weight = INTEGER grams. No REAL in either.
--   2. "Empty != zero" (template golden rule 7): optional values are NULLable
--      and blank-ness is recorded, never coerced to 0.
--   3. v001 data survives; approved documents stay immutable.
--   4. Runs exactly once. ADD COLUMN is NOT re-runnable, so the guard is the
--      runner's version gate (version > MAX(schema_migrations.version)), not
--      statement-level tolerance. Never edit this file after release: add
--      003_*.sql instead (checksum-drift rule, Spec ch.3).
-- ============================================================================

-- ===========================================================================
-- STEP 1 — TABLE REBUILDS (must come first: DROP TABLE kills its triggers)
--
-- SQLite cannot ALTER a CHECK constraint or relax a NOT NULL. Two v001 tables
-- make the owner's templates literally unimportable, so they are rebuilt
-- with the 12-step procedure, preserving every row and id.
-- ===========================================================================

-- --- 1a. basket_movements ---------------------------------------------------
-- G-11: v001 CHECK was ('RECEIVE','ISSUE','RETURN','PURCHASE').
--       The owner's 07_Basket_Movements template uses
--       PURCHASE / ISSUE / RETURN / TRANSFER / OPENING.
--       'RECEIVE' is retained as a legacy alias so v001 rows stay valid.
CREATE TABLE IF NOT EXISTS basket_movements_v2 (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    basket_id      INTEGER NOT NULL REFERENCES baskets(id),
    party_id       INTEGER REFERENCES parties(id),
    event_type     TEXT NOT NULL CHECK (event_type IN
                       ('PURCHASE','ISSUE','RETURN','TRANSFER','OPENING','RECEIVE')),
    quantity       INTEGER NOT NULL DEFAULT 0,
    rate_rial      INTEGER NOT NULL DEFAULT 0 CHECK (typeof(rate_rial)='integer'),
    amount_rial    INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer'),
    balance_rial   INTEGER NOT NULL DEFAULT 0 CHECK (typeof(balance_rial)='integer'),
    date_iso       TEXT NOT NULL DEFAULT '',
    date_shamsi    TEXT NOT NULL DEFAULT '',
    doc_number     TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    -- G-19 pattern reused: a TRANSFER has a counterparty location.
    counterparty_party_id INTEGER REFERENCES parties(id),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO basket_movements_v2
    (id, basket_id, party_id, event_type, quantity, rate_rial, amount_rial,
     balance_rial, date_iso, date_shamsi, doc_number, description, created_at)
SELECT id, basket_id, party_id, event_type, quantity, rate_rial, amount_rial,
       balance_rial, date_iso, date_shamsi, doc_number, description, created_at
FROM basket_movements
WHERE NOT EXISTS (SELECT 1 FROM basket_movements_v2 v WHERE v.id = basket_movements.id);

DROP TABLE basket_movements;
ALTER TABLE basket_movements_v2 RENAME TO basket_movements;

-- --- 1b. payment_allocations -----------------------------------------------
-- G-17: v001 forced `invoice_id INTEGER NOT NULL` + a polymorphic
--       `invoice_kind`, which cannot be a foreign key. The template's
--       allocation rows carry a source key and reference a real invoice.
--       v002 adds two properly-constrained FKs and relaxes the legacy pair
--       so old rows keep working.
CREATE TABLE IF NOT EXISTS payment_allocations_v2 (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id         INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    -- legacy pair (v001 rows); kept, now nullable
    invoice_id         INTEGER,
    invoice_kind       TEXT CHECK (invoice_kind IS NULL OR invoice_kind IN ('PURCHASE','SALES')),
    -- v002 typed targets
    purchase_invoice_id INTEGER REFERENCES purchase_invoices(id),
    sales_invoice_id    INTEGER REFERENCES sales_invoices(id),
    amount_rial        INTEGER NOT NULL DEFAULT 0 CHECK (typeof(amount_rial)='integer' AND amount_rial >= 0),
    source_key         TEXT,
    CHECK (
        ((purchase_invoice_id IS NOT NULL) + (sales_invoice_id IS NOT NULL)
          + (CASE WHEN invoice_id IS NOT NULL THEN 1 ELSE 0 END)) = 1
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_alloc_source_key_v2 ON payment_allocations_v2(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';

-- UPGRADE, not duplication: a legacy row whose target resolves to a real
-- invoice is rewritten into the typed column and its legacy pair is cleared
-- (otherwise the row would count as TWO targets). A legacy row whose target
-- cannot be resolved keeps its legacy pair untouched and stays visible as
-- LEGACY in schema_field_notes — it is never guessed at or silently deleted.
INSERT INTO payment_allocations_v2
    (id, payment_id, invoice_id, invoice_kind, purchase_invoice_id,
     sales_invoice_id, amount_rial, source_key)
SELECT a.id, a.payment_id,
       CASE WHEN resolved THEN NULL ELSE a.invoice_id END,
       CASE WHEN resolved THEN NULL ELSE a.invoice_kind END,
       CASE WHEN resolved AND a.invoice_kind = 'PURCHASE' THEN a.invoice_id END,
       CASE WHEN resolved AND a.invoice_kind = 'SALES'    THEN a.invoice_id END,
       a.amount_rial, NULL
FROM (
    SELECT a.*,
           ((a.invoice_kind = 'PURCHASE' AND EXISTS (
                 SELECT 1 FROM purchase_invoices p WHERE p.id = a.invoice_id))
         OR (a.invoice_kind = 'SALES' AND EXISTS (
                 SELECT 1 FROM sales_invoices s WHERE s.id = a.invoice_id))) AS resolved
    FROM payment_allocations a
) a
WHERE NOT EXISTS (SELECT 1 FROM payment_allocations_v2 v WHERE v.id = a.id);

DROP TABLE payment_allocations;
ALTER TABLE payment_allocations_v2 RENAME TO payment_allocations;

-- Recreate the source-key index under its canonical name on the final table.
DROP INDEX IF EXISTS ux_alloc_source_key_v2;
CREATE UNIQUE INDEX IF NOT EXISTS ux_alloc_source_key ON payment_allocations(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';

-- A backfilled typed target must never contradict the legacy kind.
CREATE TRIGGER IF NOT EXISTS trg_alloc_single_target_v002
BEFORE INSERT ON payment_allocations
WHEN (NEW.purchase_invoice_id IS NOT NULL) + (NEW.sales_invoice_id IS NOT NULL)
   + (CASE WHEN NEW.invoice_id IS NOT NULL THEN 1 ELSE 0 END) <> 1
BEGIN
    SELECT RAISE(ABORT,
        'an allocation must reference exactly one invoice (purchase XOR sales XOR legacy)');
END;

-- ===========================================================================
-- STEP 2 — ADDITIVE COLUMNS (non-destructive ALTER TABLE ADD COLUMN)
-- ===========================================================================

-- --- G-01  parties.party_kind (PERSON / COMPANY) ---------------------------
-- The 01_Parties template requires PERSON|COMPANY. v001 `nature`
-- (C/SL/S/E/X/F/L/CAP) is an ACCOUNT CLASS, a different axis: a COMPANY can
-- hold class 'S'. Overloading `nature` would corrupt the code system, so the
-- two concepts get two columns.
ALTER TABLE parties ADD COLUMN party_kind TEXT
    CHECK (party_kind IS NULL OR party_kind IN ('PERSON','COMPANY'));
ALTER TABLE parties ADD COLUMN party_kind_confirmed INTEGER NOT NULL DEFAULT 0
    CHECK (party_kind_confirmed IN (0,1));
UPDATE parties SET party_kind = CASE WHEN nature = 'E' THEN 'PERSON' ELSE 'COMPANY' END
 WHERE party_kind IS NULL;   -- backfill only; owner must confirm (flag stays 0)

-- --- G-02  parties.economic_code ------------------------------------------
ALTER TABLE parties ADD COLUMN economic_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_parties_economic_code ON parties(economic_code)
    WHERE economic_code IS NOT NULL AND economic_code <> '';

-- --- G-03  products.variety_name / products.is_active ---------------------
ALTER TABLE products ADD COLUMN variety_name TEXT;
ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
    CHECK (is_active IN (0,1));
CREATE INDEX IF NOT EXISTS ix_products_active ON products(is_active);

-- --- G-04 / G-06 / G-09  idempotency source keys --------------------------
-- A repeated import of the same file must not double-post.
ALTER TABLE weigh_tickets     ADD COLUMN source_key TEXT;
ALTER TABLE purchase_invoices ADD COLUMN source_key TEXT;
ALTER TABLE sales_invoices    ADD COLUMN source_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_weigh_source_key ON weigh_tickets(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_purchase_source_key ON purchase_invoices(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';
CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_source_key ON sales_invoices(source_key)
    WHERE source_key IS NOT NULL AND source_key <> '';

-- --- G-05  weigh_tickets packaging / package count / receipt --------------
ALTER TABLE weigh_tickets ADD COLUMN packaging_id INTEGER REFERENCES packaging_types(id);
ALTER TABLE weigh_tickets ADD COLUMN package_count INTEGER NOT NULL DEFAULT 0
    CHECK (package_count >= 0);
ALTER TABLE weigh_tickets ADD COLUMN receipt_number TEXT;

-- --- G-07  purchase_invoice_lines.weigh_ticket_id -------------------------
-- The template binds the weighbridge document to the LINE: one purchase
-- invoice may aggregate several truckloads.
ALTER TABLE purchase_invoice_lines ADD COLUMN weigh_ticket_id INTEGER REFERENCES weigh_tickets(id);
CREATE INDEX IF NOT EXISTS ix_pil_weigh ON purchase_invoice_lines(weigh_ticket_id);

-- --- G-12  bank_transactions.fee_rial / tracking / reported balance -------
-- The bank fee is NOT part of deposit/withdrawal, so SUM(deposit-withdrawal)
-- stays correct while the fee posts to expense separately.
ALTER TABLE bank_transactions ADD COLUMN fee_rial INTEGER NOT NULL DEFAULT 0
    CHECK (typeof(fee_rial)='integer' AND fee_rial >= 0);
ALTER TABLE bank_transactions ADD COLUMN tracking_number TEXT;
ALTER TABLE bank_transactions ADD COLUMN reported_balance_known INTEGER NOT NULL DEFAULT 0
    CHECK (reported_balance_known IN (0,1));   -- 0 = not reported (NOT "balance was 0")

-- --- G-14  cheques issue date vs due date ---------------------------------
ALTER TABLE cheques ADD COLUMN issue_date_shamsi TEXT;
ALTER TABLE cheques ADD COLUMN due_date_shamsi TEXT;
UPDATE cheques SET issue_date_shamsi = cheque_date WHERE issue_date_shamsi IS NULL;

-- --- G-15  cheques.sayad_id (16-digit national id) + registry link --------
ALTER TABLE cheques ADD COLUMN sayad_id TEXT;
ALTER TABLE cheques ADD COLUMN registry_id INTEGER REFERENCES cheques_registry(id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cheques_sayad ON cheques(sayad_id)
    WHERE sayad_id IS NOT NULL AND sayad_id <> '';

-- --- G-21  bank_accounts official name / branch ---------------------------
ALTER TABLE bank_accounts ADD COLUMN official_name TEXT;
ALTER TABLE bank_accounts ADD COLUMN branch_name TEXT;
ALTER TABLE bank_accounts ADD COLUMN branch_code TEXT;

-- --- G-16  payments instrument type + cheque link -------------------------
ALTER TABLE payments ADD COLUMN instrument_type TEXT
    CHECK (instrument_type IS NULL OR instrument_type IN ('BANK','CHEQUE','CREDIT_NOTE','OTHER'));
ALTER TABLE payments ADD COLUMN cheque_id INTEGER REFERENCES cheques(id);

-- --- G-19  partnership_events origin / destination ------------------------
ALTER TABLE partnership_events ADD COLUMN origin_place TEXT;
ALTER TABLE partnership_events ADD COLUMN destination_place TEXT;

-- --- Import layer: blank-vs-zero and two-header-row support (G-22, G-05) --
ALTER TABLE import_rows ADD COLUMN blank_fields_json TEXT;
ALTER TABLE import_rows ADD COLUMN source_row_number INTEGER;
ALTER TABLE import_batches ADD COLUMN header_row_second INTEGER;   -- Persian header row
ALTER TABLE import_batches ADD COLUMN profile_code TEXT;
ALTER TABLE import_batches ADD COLUMN file_sha256 TEXT;

-- ===========================================================================
-- STEP 3 — TRIGGERS THAT NEED THE REBUILT TABLES
-- ===========================================================================

-- G-11 companion: a TRANSFER must be bound by a document number.
CREATE TRIGGER IF NOT EXISTS trg_basket_transfer_v002
BEFORE INSERT ON basket_movements
WHEN NEW.event_type = 'TRANSFER' AND (NEW.doc_number IS NULL OR NEW.doc_number = '')
BEGIN
    SELECT RAISE(ABORT, 'basket TRANSFER requires a document number');
END;

-- G-11 companion: a TRANSFER must name its counterparty.
CREATE TRIGGER IF NOT EXISTS trg_basket_transfer_party_v002
BEFORE INSERT ON basket_movements
WHEN NEW.event_type = 'TRANSFER' AND NEW.counterparty_party_id IS NULL
BEGIN
    SELECT RAISE(ABORT, 'basket TRANSFER requires a counterparty party');
END;

-- G-14 companion: due date cannot precede issue date.
CREATE TRIGGER IF NOT EXISTS trg_cheque_due_after_issue_v002
BEFORE INSERT ON cheques
WHEN COALESCE(NEW.issue_date_shamsi,'') <> '' AND COALESCE(NEW.due_date_shamsi,'') <> ''
 AND NEW.due_date_shamsi < NEW.issue_date_shamsi
BEGIN
    SELECT RAISE(ABORT, 'cheque due date cannot be earlier than its issue date');
END;

-- G-15 companion: sayad id is exactly 16 digits when present.
CREATE TRIGGER IF NOT EXISTS trg_cheque_sayad_16_v002
BEFORE INSERT ON cheques
WHEN COALESCE(NEW.sayad_id,'') <> ''
 AND (length(NEW.sayad_id) <> 16 OR NEW.sayad_id GLOB '*[^0-9]*')
BEGIN
    SELECT RAISE(ABORT, 'sayad_id must be exactly 16 digits');
END;

-- GUARDS MUST ALSO FIRE ON UPDATE. A validated insert followed by a lax update
-- is not validation: these two triggers exist because the first version of
-- this migration only guarded INSERT and the harness proved it
-- (verify_database.py, G-14/G-15) — a cheque could be edited to a 15-digit
-- sayad id or a due date before its issue date.
CREATE TRIGGER IF NOT EXISTS trg_cheque_sayad_16_upd_v002
BEFORE UPDATE OF sayad_id ON cheques
WHEN COALESCE(NEW.sayad_id,'') <> ''
 AND (length(NEW.sayad_id) <> 16 OR NEW.sayad_id GLOB '*[^0-9]*')
BEGIN
    SELECT RAISE(ABORT, 'sayad_id must be exactly 16 digits');
END;

CREATE TRIGGER IF NOT EXISTS trg_cheque_due_after_issue_upd_v002
BEFORE UPDATE OF issue_date_shamsi, due_date_shamsi ON cheques
WHEN COALESCE(NEW.issue_date_shamsi,'') <> '' AND COALESCE(NEW.due_date_shamsi,'') <> ''
 AND NEW.due_date_shamsi < NEW.issue_date_shamsi
BEGIN
    SELECT RAISE(ABORT, 'cheque due date cannot be earlier than its issue date');
END;

-- Mass balance at the database boundary (defence in depth; the engine in
-- MassBalance.cs computes it first). A batch may only be APPROVED when
-- Input = Outputs + Waste + ProcessLoss + Variance within tolerance.
CREATE TRIGGER IF NOT EXISTS trg_sorting_mass_balance_v002
BEFORE UPDATE OF status ON sorting_batches
WHEN NEW.status = 'APPROVED'
 AND ABS(NEW.input_grams - (NEW.output_grams + NEW.waste_grams
                            + NEW.process_loss_grams + NEW.variance_grams))
     > NEW.tolerance_grams
BEGIN
    SELECT RAISE(ABORT, 'mass balance violated: Input must equal Outputs + Waste + Loss + Variance within tolerance');
END;

-- Wage shares may never exceed the wage header total.
CREATE TRIGGER IF NOT EXISTS trg_wage_shares_over_total_v002
BEFORE INSERT ON wage_shares
WHEN (SELECT COALESCE(SUM(share_rial),0) FROM wage_shares WHERE wage_id = NEW.wage_id)
     + NEW.share_rial
   > (SELECT total_rial FROM employee_wages WHERE id = NEW.wage_id)
BEGIN
    SELECT RAISE(ABORT, 'sum of wage shares cannot exceed the wage total');
END;

-- ===========================================================================
-- STEP 4 — VIEWS
-- ===========================================================================

-- The contract the import layer and the UI read for weighbridge rows: it
-- exposes whether an optional value was recorded instead of pretending a 0.
CREATE VIEW IF NOT EXISTS v_weigh_ticket_import AS
SELECT w.id, w.code, w.source_key, w.date_shamsi, w.time,
       w.direction, w.operation_id, w.party_id, w.product_id,
       w.packaging_id, w.package_count, w.receipt_number,
       w.basket_count, w.basket_id,
       w.gross_grams, w.tare_grams, w.loss_grams, w.net_grams,
       w.status,
       CASE WHEN COALESCE(w.receipt_number,'') = '' THEN 0 ELSE 1 END AS has_receipt_number,
       CASE WHEN w.package_count = 0 THEN 0 ELSE 1 END                AS has_packages
FROM weigh_tickets w;

-- ===========================================================================
-- STEP 5 — DATA DICTIONARY METADATA (feeds the ch.18 data dictionary doc)
--   Records, in the database itself, which columns are optional and which
--   legacy columns are NOT the source of truth. This is how G-22 is made
--   auditable: every place where "0 means unknown" used to hide is named.
-- ===========================================================================
CREATE TABLE IF NOT EXISTS schema_field_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    column_name TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK (status IN ('ACTIVE','OPTIONAL','DEPRECATED','LEGACY','DERIVED')),
    note        TEXT NOT NULL DEFAULT '',
    UNIQUE (table_name, column_name)
);

INSERT OR REPLACE INTO schema_field_notes (table_name, column_name, status, note) VALUES
 ('weigh_tickets','amount_rial','DEPRECATED',
  'Money never enters via the weighbridge (DEC-NEW-007). Reports must not read this column; use the journal.'),
 ('weigh_tickets','gross_kg_raw','ACTIVE','Raw scale reading kept verbatim for traceability (ch.8).'),
 ('weigh_tickets','receipt_number','OPTIONAL','Blank means "no receipt issued", not receipt 0.'),
 ('weigh_tickets','package_count','OPTIONAL','0 means "not recorded"; use has_packages in v_weigh_ticket_import.'),
 ('bank_transactions','reported_balance_known','ACTIVE',
  '0 = the statement did not report a balance. Never render as "balance was 0".'),
 ('bank_transactions','fee_rial','ACTIVE','Separate from deposit/withdrawal; posts to bank expense.'),
 ('parties','party_kind','ACTIVE','PERSON/COMPANY from the 01_Parties template; independent of `nature`.'),
 ('parties','party_kind_confirmed','ACTIVE','0 = backfilled by migration_002, owner has not confirmed.'),
 ('parties','nature','LEGACY','Account-class code C/SL/S/E/X/F/L/CAP used to build system codes.'),
 ('payment_allocations','invoice_id','LEGACY','Superseded by purchase_invoice_id / sales_invoice_id (G-17).'),
 ('payment_allocations','invoice_kind','LEGACY','Superseded by the typed invoice columns (G-17).'),
 ('basket_movements','event_type','ACTIVE','PURCHASE/ISSUE/RETURN/TRANSFER/OPENING; RECEIVE is a legacy alias.'),
 ('cheques','issue_date_shamsi','ACTIVE','Issue date; distinct from due_date_shamsi (G-14).'),
 ('cheques','due_date_shamsi','ACTIVE','Maturity date used by unpaid-cheque reports.'),
 ('import_rows','blank_fields_json','ACTIVE','Names of source columns that were blank — preserves "blank != zero".'),
 ('import_batches','header_row_second','ACTIVE','Persian header row of the two-header template layout.');

-- ===========================================================================
-- STEP 6 — REGISTER THE MIGRATION (runner also records it; idempotent here)
-- ===========================================================================
DELETE FROM schema_migrations WHERE version = 2;
INSERT INTO schema_migrations (version, name)
VALUES (2, 'v002 workbook alignment: rebuilds (G-11, G-17) + 20 columns + 7 triggers + field notes');
