# Execution Ledger — SORTING OS / مازندشت

| Prompt | Date | Branch | Before SHA | After SHA | Status | Files changed | Tests executed/result | Migration/data effect | Open decision | Reviewer |
|---|---|---|---|---|---|---|---|---|---|---|
| 00 (audit) | 2026-11-17 | arena/2e885c97-sorting-os | 62ad947 | — | PASS | reports/INITIAL_REPOSITORY_AUDIT.md | git/file inventory (read-only) | none | BLOCKED-01 (Excel files missing) | — |
| NEW-01 (foundation) | 2026-11-17 | arena/2e885c97-sorting-os | 62ad947 | (this commit) | PARTIAL | docs/MAZANDASHT_SPEC_FA.md, docs/decision-log.md, database/schema/schema_v001.sql, database/seed/seed_v001.sql, tools/verify_database.py, src/** (40 files), reports/BASELINE.md | tools/verify_database.py: 18/18 PASS; C# build/test: NOT RUN (no .NET in sandbox) | schema v001 + seed v001 created and verified | DEC-NEW-004 (P01/P02 confirmation), DEC-001..012 | — |
| NEW-03 (schema v002) | 2026-11-17 | arena/2e885c97-sorting-os | c6c9f12 | (this commit) | PASS (data layer) / C# NOT RUN | database/migrations/002_v002_workbook_alignment.sql, src/Mazandasht.Persistence/{MigrationRunner,DatabaseBootstrapper,Repositories}.cs, src/Mazandasht.Domain/{Entities,CodeGenerator}.cs, tools/{verify_database,gen_data_dictionary}.py, docs/{DATA_DICTIONARY_FA,decision-log}.md | `tools/verify_database.py`: **38/38 PASS** (18 v001 + 20 v002). C# build/test: **NOT RUN** (no .NET in sandbox) | migration v001→v002 applied; 2 tables rebuilt, 20 columns, 9 triggers, 2 views, field-note dictionary | DEC-NEW-010..014; owner to confirm `party_kind` backfill + P01/P02 | — |
| NEW-02 (reference extraction) | 2026-11-17 | arena/2e885c97-sorting-os | 407352d | (this commit) | PASS | docs/WORKBOOK_SPEC_FA.md, docs/decision-log.md (DEC-NEW-005..009), reports/EXECUTION_LEDGER.md | استخراج متن ۱۵ فایل سیستم + ۱۱ قالب واردسازی از Google Drive؛ مقایسه ۲۲ فیلد با schema_v001 | بدون تغییر دیتابیس (schema_v001 دست‌نخورده) | DEC-NEW-004 (تأیید عددی P01/P02), DEC-001..012 | — |

Status values: `PASS`, `PARTIAL`, `BLOCKED`, `FAIL`, `NOT RUN`, `NOT VERIFIED`. Never mark `PASS` without evidence path.

## NEW-03 — Defects found while building v002 (evidence trail)

Every item below was found by `tools/verify_database.py` or by an explicit probe, **after** it looked finished. Recording them because the pattern matters: a passing trigger is not a working constraint.

| # | Defect | How it surfaced | Fix |
|---|---|---|---|
| 1 | Migration backfill set **both** `invoice_id` and the typed FK → violated the exactly-one CHECK | test `v002: table rebuilds preserved rows…` failed | rewrite legacy row to the typed column and clear the legacy pair; unresolvable rows kept as-is |
| 2 | Cheque guards only fired on INSERT — an UPDATE could store a 15-digit sayad id / inverted due date | test `G-15` failed | added `trg_cheque_sayad_16_upd_v002`, `trg_cheque_due_after_issue_upd_v002` |
| 3 | First draft of the G-11 fix added a trigger but left the v001 **CHECK** in place, so `TRANSFER`/`OPENING` were still rejected | probe printed `CHECK constraint failed` | full table rebuild of `basket_movements` |
| 4 | `MigrationRunner` issued `PRAGMA foreign_keys=OFF` **inside** the transaction (silently ignored) and would have rebuilt tables with FKs on | code review + SQLite semantics | pragma before the transaction, then verified by reading it back |
| 5 | `LoadFromFolder` split on `_` and **silently skipped** `migration_002.sql` → migration never runs | filename check | canonical `NNN_*.sql`; anything else logged as SKIP; duplicate versions throw |
| 6 | No code path ever called the migration runner | grep for `LoadFromFolder` returned only its definition | added `DatabaseBootstrapper.EnsureCreated()` |
| 7 | Checksums were never computed, so drift on a released migration was invisible | code review | SHA-256 recorded + `DetectDrift()` fails the boot |
| 8 | My own test asserted `is_active=7` fails but used a fixture row that did not exist, and another assumed seed cheques | 5 tests failed with `NoneType` | tests now create their own fixtures |

Deliberate limitation carried forward (DEC-NEW-012): v001 columns declared `NOT NULL DEFAULT 0` were **not** relaxed to NULL. Blank-vs-zero is surfaced through `*_known` flags and `schema_field_notes`; a true NULL on those columns needs a `003` rebuild.
