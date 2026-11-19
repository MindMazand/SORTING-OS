-- ============================================================================
-- MAZANDASH — Schema v003  (003_import_contract_columns.sql)
--
-- Closes the columns the import engine proved it needs. Every column here was
-- found by tools/test_import.py failing against a real database — not by
-- reading the contract and guessing. See reports/EXECUTION_LEDGER.md NEW-04.
--
-- Two of these are not cosmetic:
--   * bank_transactions had NO direction column. The template says IN/OUT and
--     the schema only had deposit_rial/withdrawal_rial, so "direction" could
--     not be stored at all and every report would have re-derived it.
--   * weigh_tickets.warehouse_id was missing entirely, so an imported weighing
--     could not record WHICH warehouse received the goods.
--
-- Execution contract: same as 002 — PRAGMA foreign_keys=OFF outside the
-- transaction, one transaction, foreign_key_check before COMMIT. Runs once.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- G-23  bank_transactions.direction
-- kept in sync with deposit/withdrawal by trigger, so the three can never
-- disagree (a mismatch here would silently corrupt every bank report).
-- ---------------------------------------------------------------------------
ALTER TABLE bank_transactions ADD COLUMN direction TEXT
    CHECK (direction IS NULL OR direction IN ('IN','OUT'));
UPDATE bank_transactions
   SET direction = CASE WHEN withdrawal_rial > 0 THEN 'OUT' ELSE 'IN' END
 WHERE direction IS NULL;

CREATE TRIGGER IF NOT EXISTS trg_bank_direction_insert_v003
BEFORE INSERT ON bank_transactions
WHEN NEW.direction IS NOT NULL
 AND ((NEW.direction = 'IN'  AND NEW.withdrawal_rial > 0)
   OR (NEW.direction = 'OUT' AND NEW.deposit_rial > 0))
BEGIN
    SELECT RAISE(ABORT, 'bank direction contradicts the deposit/withdrawal amounts');
END;

CREATE TRIGGER IF NOT EXISTS trg_bank_direction_update_v003
BEFORE UPDATE OF direction, deposit_rial, withdrawal_rial ON bank_transactions
WHEN NEW.direction IS NOT NULL
 AND ((NEW.direction = 'IN'  AND NEW.withdrawal_rial > 0)
   OR (NEW.direction = 'OUT' AND NEW.deposit_rial > 0))
BEGIN
    SELECT RAISE(ABORT, 'bank direction contradicts the deposit/withdrawal amounts');
END;

-- ---------------------------------------------------------------------------
-- G-24  weigh_tickets.warehouse_id (which warehouse received the goods)
-- ---------------------------------------------------------------------------
ALTER TABLE weigh_tickets ADD COLUMN warehouse_id INTEGER REFERENCES warehouses(id);
CREATE INDEX IF NOT EXISTS ix_weigh_warehouse ON weigh_tickets(warehouse_id);

-- ---------------------------------------------------------------------------
-- G-25  sorting_batches: source key + document identity
-- The import template identifies a sorting operation by SortDocCode; without a
-- unique key a re-import would create the batch twice.
-- ---------------------------------------------------------------------------
ALTER TABLE sorting_batches ADD COLUMN source_key TEXT;
ALTER TABLE sorting_batches ADD COLUMN date_shamsi TEXT;
ALTER TABLE sorting_batches ADD COLUMN description TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_sorting_source_key
    ON sorting_batches(source_key) WHERE source_key IS NOT NULL AND source_key <> '';

-- ---------------------------------------------------------------------------
-- G-26  basket_movements: source key + the two warehouse ends
-- The transfer rule already required both ends; there was nowhere to put them.
-- ---------------------------------------------------------------------------
ALTER TABLE basket_movements ADD COLUMN source_key TEXT;
ALTER TABLE basket_movements ADD COLUMN from_warehouse_id INTEGER REFERENCES warehouses(id);
ALTER TABLE basket_movements ADD COLUMN to_warehouse_id INTEGER REFERENCES warehouses(id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_basket_source_key
    ON basket_movements(source_key) WHERE source_key IS NOT NULL AND source_key <> '';

-- ---------------------------------------------------------------------------
-- G-27  cheques: idempotency key + the document number
--
-- The 09_Cheques template has ONE identity column (SourceDocCode) and says it
-- is unique, but a cheque also needs a human-readable document number for the
-- sub-ledger. v002 left `doc_number` out entirely, so the importer had no
-- honest place to put it: writing SourceDocCode into `cheque_number` would
-- overwrite the real cheque number the bank prints on the paper. Both columns
-- exist from v003 on.
-- ---------------------------------------------------------------------------
ALTER TABLE cheques ADD COLUMN source_key TEXT;
ALTER TABLE cheques ADD COLUMN doc_number TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_cheques_source_key
    ON cheques(source_key) WHERE source_key IS NOT NULL AND source_key <> '';

-- ---------------------------------------------------------------------------
-- G-28  payment_allocations.instrument_type + note
-- The 10_Settlements template carries the instrument per allocation row, and
-- an allocation is exactly the place where "how was this paid" belongs.
-- ---------------------------------------------------------------------------
ALTER TABLE payment_allocations ADD COLUMN instrument_type TEXT
    CHECK (instrument_type IS NULL OR instrument_type IN ('BANK','CHEQUE','CREDIT_NOTE','OTHER'));
ALTER TABLE payment_allocations ADD COLUMN description TEXT;

-- ---------------------------------------------------------------------------
-- G-29  partnership_events: idempotency key + the template's own column names
-- v002 had origin_place/destination_place but the rest of the template landed
-- in columns named after the OLD workbook, so imported and hand-entered rows
-- would have disagreed about where a value lives.
-- ---------------------------------------------------------------------------
ALTER TABLE partnership_events ADD COLUMN source_key TEXT;
ALTER TABLE partnership_events ADD COLUMN product_id INTEGER REFERENCES products(id);
ALTER TABLE partnership_events ADD COLUMN warehouse_id INTEGER REFERENCES warehouses(id);
ALTER TABLE partnership_events ADD COLUMN basket_id INTEGER REFERENCES baskets(id);
ALTER TABLE partnership_events ADD COLUMN gross_grams INTEGER;
ALTER TABLE partnership_events ADD COLUMN consumed_baskets INTEGER;
ALTER TABLE partnership_events ADD COLUMN custody_returned_baskets INTEGER;
ALTER TABLE partnership_events ADD COLUMN partner_share_percent REAL;
ALTER TABLE partnership_events ADD COLUMN rounding_unit_grams INTEGER;
ALTER TABLE partnership_events ADD COLUMN purchase_aggregation_id INTEGER REFERENCES purchase_aggregations(id);
ALTER TABLE partnership_events ADD COLUMN description TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_partnership_source_key
    ON partnership_events(source_key) WHERE source_key IS NOT NULL AND source_key <> '';

-- ---------------------------------------------------------------------------
-- G-30  sales_invoice_lines.sorting_output_id
-- The template can sell directly from a sorting output; without the link the
-- report "which output was sold" is unanswerable.
-- ---------------------------------------------------------------------------
ALTER TABLE sales_invoice_lines ADD COLUMN sorting_output_id INTEGER REFERENCES sorting_outputs(id);
CREATE INDEX IF NOT EXISTS ix_sil_sortout ON sales_invoice_lines(sorting_output_id);

-- ---------------------------------------------------------------------------
-- Register the migration.
-- ---------------------------------------------------------------------------
DELETE FROM schema_migrations WHERE version = 3;
INSERT INTO schema_migrations (version, name)
VALUES (3, 'v003 import-contract columns (bank direction, weigh warehouse, source keys)');

-- Field notes: name the places where a value now has a home, so the data
-- dictionary does not silently lose them.
INSERT OR REPLACE INTO schema_field_notes (table_name, column_name, status, note) VALUES
 ('bank_transactions','direction','ACTIVE',
  'IN/OUT kept in sync with deposit/withdrawal by trigger; never re-derived in reports.'),
 ('weigh_tickets','warehouse_id','ACTIVE',
  'Which warehouse received the goods. Absent before v003 — the weighing could not say where it went.'),
 ('sorting_batches','variance_grams','DERIVED',
  'Must equal input - (output + waste + process_loss); approved only inside tolerance.'),
 ('partnership_events','gross_grams','ACTIVE','Template name; the legacy weigh_grams column is superseded.'),
 ('partnership_events','weigh_grams','LEGACY','Pre-template column kept for old rows; do not write new values.');
