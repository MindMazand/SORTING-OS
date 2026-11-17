-- ============================================================================
-- MAZANDASHT — Schema v005  (005_lot_lookup.sql)
--
-- DEC-NEW-033. The weighing template creates a lot whose code the engine
-- generates (LOT001). The sales and sorting templates must quote that code, but
-- NOTHING ever shows it to the owner: it is not on the printed weigh ticket, not
-- in the weighing sheet they typed, and not in any report yet. So in practice
-- the owner cannot fill those two columns at all, and would discover it while
-- trying to import their real files.
--
-- Decision: allow the lot to be identified by the WEIGH TICKET NUMBER as well
-- as by the lot code. The ticket number IS printed on the paper the owner
-- already has, and quoting it is what a person would naturally do.
--
-- A view rather than a second lookup column, for the same reason as
-- v_invoice_lookup: one lookup target means the resolution rule exists in one
-- place and two code paths cannot drift apart.
--
-- Execution contract: same as 002/003/004.
-- ============================================================================

CREATE VIEW IF NOT EXISTS v_lot_lookup AS
SELECT l.id AS id, l.code AS ref, 'LOT' AS kind
FROM lots l
WHERE COALESCE(l.code, '') <> ''
UNION ALL
SELECT l.id AS id, w.doc_number AS ref, 'WEIGH_TICKET' AS kind
FROM lots l
JOIN weigh_tickets w ON w.id = l.weigh_ticket_id
WHERE COALESCE(w.doc_number, '') <> '';

-- ---------------------------------------------------------------------------
-- Register.
-- ---------------------------------------------------------------------------
DELETE FROM schema_migrations WHERE version = 5;
INSERT INTO schema_migrations (version, name)
VALUES (5, 'v005 lot lookup (lot code or weigh ticket number)');

INSERT OR REPLACE INTO schema_field_notes (table_name, column_name, status, note) VALUES
 ('lots','code','ACTIVE',
  'شناسه lot که موتور تولید می‌کند (LOT001). مالک آن را روی کاغذ نمی‌بیند، پس فروش و سورتینگ می‌توانند با شماره باسکول هم آن را پیدا کنند (v_lot_lookup).');
