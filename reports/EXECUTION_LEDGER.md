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

## NEW-07 — The last two writers had never been executed, and both were broken

`t_detect_all_eleven` proved that all 11 templates are *recognised* from their
headers. It never imported them. Two writers had therefore never run once:

### SETTLEMENTS could not import at all

It resolved the invoice number through `invoices:doc_number`. There is no
`invoices` table, so the lookup raised `no such table: invoices` on the first
row. It also read `rr.ids["__invoice_kind"]` to decide whether the allocation
belongs to a purchase or a sales invoice — and **nothing ever set that key**, so
the read was decorative.

Fixed with an explicit virtual-lookup table. The settlement line now attaches to
the correct side, and a test imports one allocation against a purchase invoice
and one against a sales invoice, then asserts that each row's NULL side is
really NULL.

### PARTNERSHIP imported every event with no partner

The contract mapped the partner to `partner_party_id`. The column is `party_id`.
`_select_columns` dropped the unknown key **silently**, so:

    import_batches.status = IMPORTED
    partnership_events.party_id = NULL
    no warning anywhere

This is the worst shape a bug can take in an accounting system: nothing fails,
the numbers are simply wrong. `_select_columns` now raises.

### And 23 more contract fields pointed at the wrong table or a made-up name

Invoice *line* fields (`rate_rial_per_kg`, `grams`, `discount_rial`, ...) were
mapped onto the invoice *header*. Sorting fields used names that never existed
(`input_lot_id` vs `lot_id`, `output_grams` vs `grams`). `input_warehouse_id` has
no column anywhere, by design: the lot already carries its warehouse.

Header vs line was implicit knowledge in one person's head. It is now
`FIELD_TARGETS` in `tools/check_contract_schema.py`, which fails on a wrong
column, on two fields writing the same column, and on a field that belongs to
neither group. Proven by planting a typo and watching it fail.

### A bug in the test harness itself

When a test died mid-transaction it left the transaction open and every later
test failed with "cannot start a transaction within a transaction". One real
failure buried six innocent ones. `check()` now rolls back on failure.

### Numbers

    test_import.py        36 -> 39 tests, 39/39 PASS
    verify_all.py         6 gates, exit 0
    contract->schema      124 columns, 11 templates, PASS

### NEW-07b — the 11 templates had never been run as a chain

Each template had its own test. Nothing ran them in the owner's real order on
one database, so nothing proved the *links* between them. `tools/test_chain.py`
now does: parties -> products -> weighing -> purchase -> sales -> sorting ->
baskets -> bank -> cheques -> settlements -> partnership, in order, on a fresh
database, asserting the net weight, the single stock movement, the invoice's
link to its weigh ticket, the settlement landing on the correct side, and the
partnership keeping both its partner and its product. It ends with
`foreign_key_check` empty and `integrity_check = ok`.

Writing it found two more things:

  * **The purchase invoice could not find its weigh ticket.** `WeighCode`
    resolved against `weigh_tickets.code`, which is the engine's internal
    `WT0001`. The owner types their own document number on the weigh sheet and
    quotes that same number on the invoice. Changed to `doc_number`.
  * **The lot code is generated (`LOT001`) and the owner never sees it**, yet
    the sales and sorting sheets must quote it. That is a real product gap, not
    a test artefact; it is recorded in the decision log rather than papered over.

### NEW-08 — the invisible lot code, and the C# settlement bug it exposed

`v005_lot_lookup.sql` closes DEC-NEW-033. The weighing import generates `LOT001`
and shows it to nobody, while sales and sorting must quote it. The owner would
have hit this on their first real sales file. A lot is now also findable by the
**weigh ticket number**, which is printed on the paper in their hand.

`test_chain.py` deliberately quotes the ticket number now, not the lot code, so
the path that is tested is the path the owner has.

Auditing the C# port against the same findings produced one more real defect:

    var isPurchase = _store.Lookup("v_invoice_lookup:kind", invoice) != null
                     && _store.LookupKind(invoice) == "PURCHASE";

`v_invoice_lookup:kind` is not an allowed lookup spec, so that call **threw**;
and `Lookup` returns an id, so it could never have been non-null for the string
"PURCHASE". The consequence, had it run: every settlement silently recorded as a
sales allocation. The C# store also lacked the `invoices:doc_number` virtual
lookup entirely, so the settlements template could not import in C# either.

Both fixed. The lesson repeats: **the Python reference had every one of these
bugs too**, and each was found by making a test execute the path rather than
assert that the path exists.

### NEW-09 — writer parity: same tables, same columns

Contract parity compared field definitions. It did not compare what the writers
actually insert, which is the thing that produces wrong rows. All 18 target
tables now compare column-for-column in both languages. Proven by deleting one
column from the C# writer and watching the check fail.

### NEW-10 — the .NET build was attempted, and honestly failed

Seven routes were tried to get a C# compiler into this sandbox. One worked
partially: the .NET Core 2.0 **runtime** downloaded and ran (`dotnet --info`
answered). No compiler was obtainable — the SDK tarball from npm is missing
`libunwind`, libunwind's own CMake in that tag supports Visual Studio only, and
Debian's repositories are network-blocked.

More importantly, a compiler would not have settled it: the target is WPF on
.NET Framework 4.8 / Windows 8.1, which cannot be built or run on Linux at all.

Full account, including the one route that worked, in
`reports/CSHARP_BUILD_ATTEMPT_FA.md`. Status is unchanged: **IMPLEMENTED /
NOT RUN**, and the three parity guards are what keep that gap from widening.

Also fixed this pass: a missing optional dependency (`tree_sitter`) used to turn
the whole gate red with a message that said nothing about the repository. It is
a NOTE with the install command now, and the PASS line states plainly that
syntax was not checked.

### NEW-11 — scale and rollback precision

The owner's real `01_Parties` template, filled with 2,000 rows and imported:
**6,449 rows/second**, zero errors. Rollback then deleted exactly those 2,000
rows and nothing else — the seed rows were compared code-by-code before and
after and were untouched. `foreign_key_check` empty afterwards.

That last property is the one worth testing. A rollback that "works" by
deleting too much is worse than one that fails loudly, and a row count alone
cannot tell the difference. The test compares the full set of party codes
before and after, not just the totals.

## NEW-12 — نوزده KPI داشبورد، اثبات‌شده روی اسکیمای واقعی

`agents/A_dashboard_queries.py` نوشته و اجرا شد. ۵/۵:
- خالی: همه صفر (بدون None، بدون استثنا)
- تفکیک: ۱٬۰۰۰٬۰۰۰ تأییدشده + ۴۰۰٬۰۰۰ بررسی‌نشده = ۱٬۴۰۰٬۰۰۰
- ابطال‌شده در هیچ سبدی شمرده نمی‌شود
- خارج از بازه حذف می‌شود (۳۰ روز پیش با `days=1` صفر، با `days=60` ۷۰۰٬۰۰۰)
- هر ۱۹ کوئری معتبر

در همین اجرا یک شاخص بیستم (`bank_balance`) پیدا و حذف شد: مشخصات فصل ۱۱
دقیقاً نوزده می‌خواهد و اضافه‌کردن عدد بیستم به لیستی که UI با موقعیت
رندر می‌شود، یعنی عدد درست زیر برچسب غلط.

## NEW-13 — SQL فایل C# همان اعداد پایتون را می‌دهد

`tools/test_dashboard_cs_sql.py`: SQL را با پیمایش پرانتز متوازن از
`SqliteDashboardStore.cs` بیرون می‌کشد، با `Make("<key>", ..., var)` به کلید
وصل می‌کند، روی دیتابیس واقعی اجرا می‌کند، و سطر به سطر با مرجع مقایسه
می‌کند. نتیجه: **۱۹ KPI، همه یکسان**.

جهش‌آزمایی: `VOIDED` به سبد بررسی‌نشده اضافه شد → `sales` از ۱٬۴۰۰٬۰۰۰ به
۲٬۳۹۹٬۰۰۰ رفت و دروازه قرمز شد. بازگردانده شد → سبز.

## NEW-14 — بازرس XAML، بدون کامپایلر

`tools/check_xaml.py --strict`: ۵ فایل، ۶۷ توکن، ۰ خطا. پنج باگ واقعی پیدا
کرد (فهرست در `DASHBOARD_ROUND_FA.md`). هر قاعده با تزریق خطای عمدی آزموده
شد: منبع ناموجود، رویداد بی‌متد، رنگ خام، TargetType ناسازگار.

## NEW-15 — دروازه‌ها از ۹ به ۱۳ رسید

`python3 tools/verify_all.py` → exit 0. چهار دروازه تازه: KPI پایتون، parity
SQL، اعداد SQL استخراج‌شده از C#، بازرس XAML.

## NEW-16 — سانحه بازنشانی ساندباکس، بار دوم

ساندباکس وسط کار بازنشانی شد: HEAD به `62ad947` بازگشت و **همه ویرایش‌های
فایل‌های tracked پاک شدند**؛ فقط فایل‌های نو (untracked) جان سالم بردند.

بازیابی: `git fetch` + `git reset --hard FETCH_HEAD` شاخه را برگرداند، ولی
ویرایش‌های این دور را برنگرداند. فایل‌های نو (Theme.v2، SqliteDashboardStore،
agents/، tools/ سه‌گانه) سالم بودند؛ هفت فایل tracked از محتوای موجود بازنویسی
شدند. پس از بازیابی، `verify_all.py` دوباره ۱۳/۱۳ سبز شد.

درس عملی: در این محیط، کار روی فایل tracked تا لحظه commit شکننده است. باید
زودتر و بیشتر commit شود.
