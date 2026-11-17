# Execution Ledger — SORTING OS / مازندشت

| Prompt | Date | Branch | Before SHA | After SHA | Status | Files changed | Tests executed/result | Migration/data effect | Open decision | Reviewer |
|---|---|---|---|---|---|---|---|---|---|---|
| 00 (audit) | 2026-11-17 | arena/2e885c97-sorting-os | 62ad947 | — | PASS | reports/INITIAL_REPOSITORY_AUDIT.md | git/file inventory (read-only) | none | BLOCKED-01 (Excel files missing) | — |
| NEW-01 (foundation) | 2026-11-17 | arena/2e885c97-sorting-os | 62ad947 | (this commit) | PARTIAL | docs/MAZANDASHT_SPEC_FA.md, docs/decision-log.md, database/schema/schema_v001.sql, database/seed/seed_v001.sql, tools/verify_database.py, src/** (40 files), reports/BASELINE.md | tools/verify_database.py: 18/18 PASS; C# build/test: NOT RUN (no .NET in sandbox) | schema v001 + seed v001 created and verified | DEC-NEW-004 (P01/P02 confirmation), DEC-001..012 | — |
| NEW-06 (ImportRunner) | 2026-11-17 | arena/2e885c97-sorting-os | dd6f287 | (this commit) | PARTIAL — C# NOT RUN, guards PASS | src/Mazandasht.Application/Import/ImportRunner.cs, src/Mazandasht.Persistence/SqliteImportBatchStore.cs, tools/{import_engine,test_import,check_csharp_schema}.py | verify_database **39/39** · test_import **36/36** (+2 rollback tests) · contract parity · C#↔schema incl. rollback-plan parity · project refs | no migration; rollback semantics fixed (no schema change) | DEC-NEW-025..027 | — |
| NEW-05 (C# port) | 2026-11-17 | arena/2e885c97-sorting-os | 35c6588 | (this commit) | PARTIAL — C# IMPLEMENTED/NOT RUN, guards PASS | src/Mazandasht.Application/Import/{ImportContract,XlsxReader,Jalali,ImportValidator,ImportEngine,ImportWriter}.cs, src/Mazandasht.Persistence/SqliteImportStore.cs, src/Mazandasht.Tests/{ImportContractTests,ImportGoldenTests}.cs, database/migrations/004_import_lookup_columns.sql, tools/{check_contract_parity,check_csharp_schema,check_project_refs,verify_all}.py, tests/golden/import_vectors.json | verify_database **39/39** · test_import **34/34** · contract parity (129/129 columns) · C#↔schema (187 columns) · project refs · C# build/test **NOT RUN** (no toolchain) | migration v003→v004: payments.doc_number, sorting_outputs.code, v_invoice_lookup + 2 unique triggers | DEC-NEW-019..024 | — |
| NEW-04 (import engine) | 2026-11-17 | arena/2e885c97-sorting-os | 808b391 | (this commit) | PASS (data layer) / C# NOT RUN | tools/{xlsx_io,import_contract,import_parser,import_engine,test_import}.py, database/migrations/003_import_contract_columns.sql, docs/decision-log.md | `tools/test_import.py`: **34/34 PASS** (۷ مرحله، روی فایل‌های xlsx واقعی) · `tools/verify_database.py`: **38/38 PASS** | migration v002→v003: ۲۴ ستون + ۴ کلید idempotency + ۲ تریگر بانکی | DEC-NEW-015..018 | — |
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

## NEW-05 — C# port: what is proven and what is not

**Not proven:** that the C# compiles or runs. No `dotnet`, `mono`, `msbuild` or `csc` exists in
the build sandbox and the Debian mirrors are unreachable, so no compiler can be installed. Every
claim below stops short of that line deliberately.

| Claim | Evidence | Limit |
|---|---|---|
| All 41 C# files are syntactically valid | tree-sitter C# parser, 0 ERROR/missing nodes | syntax only, not semantics |
| The contract matches Python exactly | 129/129 columns, name/fa/kind/required/lookup/choices/order | does not prove C# logic |
| Every column the writer touches exists | 187 column writes + 17 lookup specs + 21 whitelisted tables, checked against a real DB | does not prove runtime types |
| Project reference graph is complete and acyclic | tools/check_project_refs.py | does not prove assembly load |
| Golden vectors are self-consistent | checked against the Python reference and against known real dates | C# consumption of them is UNRUN |

### A golden vector caught a mistake in itself

`net_weight_check` originally recorded `expected_net_grams = 5090295` for
`(5200500 − 40×1500) × 0.99`. The correct value is **5089095**. Had I not
verified the vector against the formula, `ImportGoldenTests` would have been
written to confirm the wrong number — a test that pins a bug is worse than no
test, because it makes the bug permanent.

### Two build-breaking defects found before any build

1. **`payments.doc_number` did not exist.** The settlements template identifies
   a payment by its document number, and `code` (PAY001) is the internal stable
   id. Merging them would have made the number the owner reads off a receipt
   unsearchable.
2. **`Mazandasht.Persistence` did not reference `Mazandasht.Application`**, so
   `SqliteImportStore` could never compile. A unit test cannot catch this; only
   a reference-graph check or a real build can.

Both now have guards that were tested by deliberately breaking them.

## NEW-06 — Rollback was broken, and only a weigh-ticket test could show it

The previous stage claimed rollback worked because a basket-movement batch
rolled back cleanly. Basket movements have **no children**. The real chain is
two levels deep:

    weigh_tickets -> lots -> stock_movements

Three successive fixes were all wrong, and each failure looked different:

| attempt | what happened |
|---|---|
| delete in plan order | deleted `lots` while `stock_movements` still pointed at them -> FK failure |
| reverse plan order | the `stock_movements` step ran first but `collected['lots']` was empty, so it **silently skipped**, then `lots` failed |
| one pass (find + delete together) | identify and delete are different jobs; the parent was deleted before its children were found |

The correct rule, now written in the code and enforced by a test:
**collect forwards, delete by depth, deepest first, root last.**

This is the cheapest possible place to find that bug. On the owner's machine it
would have surfaced as "rollback doesn't work" weeks later, with no obvious
cause, on live data.

### What is still NOT proven

The C# `ImportRunner` and `SqliteImportBatchStore` are **written and unrun**.
Their rollback plan is verified to be identical to the Python plan that is
proven, but the C# execution path has never executed. Status stays
`IMPLEMENTED / NOT RUN`.
