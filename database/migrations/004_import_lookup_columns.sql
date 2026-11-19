-- ============================================================================
-- MAZANDASHT — Schema v004  (004_import_lookup_columns.sql)
--
-- Found by tools/check_csharp_schema.py, which reads the C# writer and checks
-- every table/column it touches against a database built from the real
-- migrations. Three references could not resolve:
--
--   1. payments had no doc_number. The 10_Settlements template identifies a
--      payment by "شماره سند پرداخت", and `code` (PAY001) is the INTERNAL
--      stable id, not the document number a user reads off a receipt.
--      Collapsing the two would make the number unsearchable by the owner.
--
--   2. sorting_outputs had no code at all. The 05_Sales_Invoices template can
--      sell straight from a sorting output ("کد خروجی سورت"), and there was
--      nothing to quote.
--
--   3. "invoices:doc_number" is a VIRTUAL lookup: the owner enters one invoice
--      number and the system must find it in purchase_invoices OR
--      sales_invoices. Expressed as a view so the lookup engine has one target
--      and cannot silently search only one side.
--
-- Execution contract: same as 002/003.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. payments.doc_number
-- ---------------------------------------------------------------------------
ALTER TABLE payments ADD COLUMN doc_number TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_doc_number
    ON payments(doc_number) WHERE doc_number IS NOT NULL AND doc_number <> '';

-- ---------------------------------------------------------------------------
-- 2. sorting_outputs.code
-- ---------------------------------------------------------------------------
ALTER TABLE sorting_outputs ADD COLUMN code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_sorting_output_code
    ON sorting_outputs(code) WHERE code IS NOT NULL AND code <> '';

-- ---------------------------------------------------------------------------
-- 3. One place to resolve an invoice number, whichever side it lives on.
--    A view (not a table) because two documents must never be able to
--    disagree about which invoice a number belongs to.
-- ---------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_invoice_lookup AS
SELECT 'PURCHASE' AS kind, id, doc_number, code, date_shamsi, party_id
FROM purchase_invoices
WHERE COALESCE(doc_number,'') <> ''
UNION ALL
SELECT 'SALES' AS kind, id, doc_number, code, date_shamsi, party_id
FROM sales_invoices
WHERE COALESCE(doc_number,'') <> '';

-- A document number must not exist on BOTH sides: the settlement template has
-- only one column for it, so an ambiguous number could be attached to the
-- wrong invoice. Enforced at write time by triggers, since SQLite cannot put
-- a UNIQUE across two tables.
CREATE TRIGGER IF NOT EXISTS trg_invoice_number_unique_purchase
BEFORE INSERT ON purchase_invoices
WHEN COALESCE(NEW.doc_number,'') <> ''
 AND EXISTS (SELECT 1 FROM sales_invoices WHERE doc_number = NEW.doc_number)
BEGIN
    SELECT RAISE(ABORT, 'شماره فاکتور در فاکتورهای فروش هم وجود دارد؛ شماره سند باید یکتا باشد');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoice_number_unique_sales
BEFORE INSERT ON sales_invoices
WHEN COALESCE(NEW.doc_number,'') <> ''
 AND EXISTS (SELECT 1 FROM purchase_invoices WHERE doc_number = NEW.doc_number)
BEGIN
    SELECT RAISE(ABORT, 'شماره فاکتور در فاکتورهای خرید هم وجود دارد؛ شماره سند باید یکتا باشد');
END;

-- ---------------------------------------------------------------------------
-- Register.
-- ---------------------------------------------------------------------------
DELETE FROM schema_migrations WHERE version = 4;
INSERT INTO schema_migrations (version, name)
VALUES (4, 'v004 import lookup columns (payments.doc_number, sorting_outputs.code, invoice view)');

INSERT OR REPLACE INTO schema_field_notes (table_name, column_name, status, note) VALUES
 ('payments','doc_number','ACTIVE',
  'شماره سند پرداخت که کاربر می‌خواند؛ `code` شناسه داخلی پایدار است و این دو یکی نیستند.'),
 ('payments','code','ACTIVE','شناسه داخلی (PAY001)؛ هرگز با شماره سند اشتباه نشود.'),
 ('sorting_outputs','code','ACTIVE','شناسه خروجی سورت برای ارجاع در فاکتور فروش.');
