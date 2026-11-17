# فرهنگ داده — مازندشت (تولیدشده خودکار)

> این فایل **دستی نوشته نشده** است. با `python3 tools/gen_data_dictionary.py`
> از اسکیمای واقعی تولید می‌شود؛ اگر با کد اختلاف داشت، کد درست است و این فایل
> باید دوباره تولید شود. مبنای فصل ۱۸ سند اصلی (Data Dictionary).

- نسخه اسکیما: **v4**
- تعداد جدول: **62** · ویو: **5** · تریگر: **17** · ایندکس: **25**

## قواعد ثابت (روی همه جدول‌ها)

| قاعده | معنا |
|---|---|
| پول | همیشه `INTEGER` ریال. هیچ `REAL` برای پول. تومان فقط برای نمایش (`/10`). |
| وزن | همیشه `INTEGER` گرم. حداکثر ۳ رقم اعشار کیلوگرم در ورودی. |
| خالی ≠ صفر | مقدار ثبت‌نشده با پرچم `*_known` یا `NULL` بیان می‌شود، نه `0`. |
| شماره نمایشی ≠ شناسه | `code` پایدار و تغییرناپذیر است؛ `doc_number` قابل‌ویرایش. |
| سند تأییدشده | با تریگر قابل UPDATE/DELETE نیست؛ اصلاح فقط با سند معکوس. |
| موجودی و مانده | هرگز ستون ذخیره‌شده نیست؛ از لجر مشتق می‌شود. |

## ویوهای مشتق‌شده

- `v_account_balance`
- `v_invoice_lookup`
- `v_journal_balance`
- `v_stock_balance`
- `v_weigh_ticket_import`

## تریگرهای محافظ

- `trg_alloc_single_target_v002`
- `trg_bank_direction_insert_v003`
- `trg_bank_direction_update_v003`
- `trg_basket_transfer_party_v002`
- `trg_basket_transfer_v002`
- `trg_cheque_due_after_issue_upd_v002`
- `trg_cheque_due_after_issue_v002`
- `trg_cheque_sayad_16_upd_v002`
- `trg_cheque_sayad_16_v002`
- `trg_invoice_number_unique_purchase`
- `trg_invoice_number_unique_sales`
- `trg_journal_line_no_delete_approved`
- `trg_journal_line_no_update_approved`
- `trg_journal_no_delete_approved`
- `trg_journal_no_update_approved`
- `trg_sorting_mass_balance_v002`
- `trg_wage_shares_over_total_v002`

## جدول‌ها

### `account_groups`  — 10 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `accounts`  — 11 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `account_type` | TEXT | الزامی |  |  |
| `group_id` | INTEGER | اختیاری |  |  |
| `is_active` | INTEGER | الزامی | `1` |  |

کلیدهای خارجی: `group_id` → `account_groups.id`

### `audit_events`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `user_id` | INTEGER | اختیاری |  |  |
| `action` | TEXT | الزامی |  |  |
| `entity_type` | TEXT | الزامی |  |  |
| `entity_id` | INTEGER | اختیاری |  |  |
| `details` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `user_id` → `users.id`

### `backup_jobs`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `backup_type` | TEXT | الزامی |  |  |
| `file_path` | TEXT | الزامی | `''` |  |
| `sha256` | TEXT | الزامی | `''` |  |
| `schema_version` | INTEGER | الزامی | `0` |  |
| `integrity_result` | TEXT | الزامی | `''` |  |
| `manifest_json` | TEXT | الزامی | `''` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

### `bank_accounts`  — 2 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `bank_id` | INTEGER | اختیاری |  |  |
| `display_name` | TEXT | الزامی |  |  |
| `account_number` | TEXT | الزامی | `''` |  |
| `sheba` | TEXT | الزامی | `''` |  |
| `opening_balance_rial` | INTEGER | الزامی | `0` |  |
| `is_active` | INTEGER | الزامی | `1` |  |
| `description` | TEXT | الزامی | `''` |  |
| `official_name` | TEXT | اختیاری |  |  |
| `branch_name` | TEXT | اختیاری |  |  |
| `branch_code` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `bank_id` → `banks.id`

### `bank_transactions`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `bank_account_id` | INTEGER | الزامی |  |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `txn_type_id` | INTEGER | اختیاری |  |  |
| `main_group_id` | INTEGER | اختیاری |  |  |
| `sub_group_id` | INTEGER | اختیاری |  |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `time` | TEXT | الزامی | `''` |  |
| `deposit_rial` | INTEGER | الزامی | `0` |  |
| `withdrawal_rial` | INTEGER | الزامی | `0` |  |
| `bank_balance_rial` | INTEGER | الزامی | `0` |  |
| `system_balance_rial` | INTEGER | الزامی | `0` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `void_reason` | TEXT | الزامی | `''` |  |
| `cheque_number` | TEXT | الزامی | `''` |  |
| `source_key` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `fee_rial` | INTEGER | الزامی | `0` | **ACTIVE** — Separate from deposit/withdrawal; posts to bank expense. |
| `tracking_number` | TEXT | اختیاری |  |  |
| `reported_balance_known` | INTEGER | الزامی | `0` | **ACTIVE** — 0 = the statement did not report a balance. Never render as "balance was 0". |
| `direction` | TEXT | اختیاری |  | **ACTIVE** — IN/OUT kept in sync with deposit/withdrawal by trigger; never re-derived in reports. |

کلیدهای خارجی: `approved_by` → `users.id` · `created_by` → `users.id` · `sub_group_id` → `sub_groups.id` · `main_group_id` → `main_groups.id` · `txn_type_id` → `txn_types.id` · `party_id` → `parties.id` · `bank_account_id` → `bank_accounts.id`

### `banks`  — 2 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `basket_movements`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `basket_id` | INTEGER | الزامی |  |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `event_type` | TEXT | الزامی |  | **ACTIVE** — PURCHASE/ISSUE/RETURN/TRANSFER/OPENING; RECEIVE is a legacy alias. |
| `quantity` | INTEGER | الزامی | `0` |  |
| `rate_rial` | INTEGER | الزامی | `0` |  |
| `amount_rial` | INTEGER | الزامی | `0` |  |
| `balance_rial` | INTEGER | الزامی | `0` |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `doc_number` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |
| `counterparty_party_id` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `source_key` | TEXT | اختیاری |  |  |
| `from_warehouse_id` | INTEGER | اختیاری |  |  |
| `to_warehouse_id` | INTEGER | اختیاری |  |  |

کلیدهای خارجی: `to_warehouse_id` → `warehouses.id` · `from_warehouse_id` → `warehouses.id` · `counterparty_party_id` → `parties.id` · `party_id` → `parties.id` · `basket_id` → `baskets.id`

### `baskets`  — 1 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `capacity_grams` | INTEGER | الزامی | `0` |  |
| `description` | TEXT | الزامی | `''` |  |
| `auto_label` | INTEGER | الزامی | `0` |  |

### `cheque_events`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `cheque_id` | INTEGER | الزامی |  |  |
| `event_type` | TEXT | الزامی |  |  |
| `event_date` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `cheque_id` → `cheques.id`

### `cheques`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `cheque_number` | TEXT | الزامی |  |  |
| `bank_account_id` | INTEGER | اختیاری |  |  |
| `cheque_date` | TEXT | الزامی | `''` |  |
| `amount_rial` | INTEGER | الزامی | `0` |  |
| `beneficiary_party_id` | INTEGER | اختیاری |  |  |
| `direction` | TEXT | الزامی |  |  |
| `status` | TEXT | الزامی | `'OPEN'` |  |
| `paid_date` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `issue_date_shamsi` | TEXT | اختیاری |  | **ACTIVE** — Issue date; distinct from due_date_shamsi (G-14). |
| `due_date_shamsi` | TEXT | اختیاری |  | **ACTIVE** — Maturity date used by unpaid-cheque reports. |
| `sayad_id` | TEXT | اختیاری |  |  |
| `registry_id` | INTEGER | اختیاری |  |  |
| `source_key` | TEXT | اختیاری |  |  |
| `doc_number` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `registry_id` → `cheques_registry.id` · `beneficiary_party_id` → `parties.id` · `bank_account_id` → `bank_accounts.id`

### `cheques_registry`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `cheque_number` | TEXT | الزامی |  |  |
| `bank_id` | INTEGER | اختیاری |  |  |
| `branch` | TEXT | الزامی | `''` |  |
| `booklet_number` | TEXT | الزامی | `''` |  |
| `series` | TEXT | الزامی | `''` |  |
| `serial` | TEXT | الزامی | `''` |  |
| `sayad_id` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `bank_id` → `banks.id`

### `company_settings`  — 13 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `key` | TEXT | PK |  |  |
| `value` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `employee_wages`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `wage_type` | TEXT | الزامی | `''` |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `total_rial` | INTEGER | الزامی | `0` |  |
| `shares_total_rial` | INTEGER | الزامی | `0` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `party_id` → `parties.id`

### `export_jobs`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `export_type` | TEXT | الزامی | `''` |  |
| `format` | TEXT | الزامی | `''` |  |
| `file_name` | TEXT | الزامی | `''` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `created_by` → `users.id`

### `fiscal_periods`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `title` | TEXT | الزامی |  |  |
| `start_date` | TEXT | الزامی |  |  |
| `end_date` | TEXT | الزامی |  |  |
| `is_closed` | INTEGER | الزامی | `0` |  |

### `grades`  — 4 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `product_id` | INTEGER | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `product_id` → `products.id`

### `import_batches`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `file_name` | TEXT | الزامی | `''` |  |
| `file_type` | TEXT | الزامی | `''` |  |
| `detected_type` | TEXT | الزامی | `''` |  |
| `header_row` | INTEGER | الزامی | `1` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `total_rows` | INTEGER | الزامی | `0` |  |
| `valid_rows` | INTEGER | الزامی | `0` |  |
| `duplicate_rows` | INTEGER | الزامی | `0` |  |
| `invalid_rows` | INTEGER | الزامی | `0` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `header_row_second` | INTEGER | اختیاری |  | **ACTIVE** — Persian header row of the two-header template layout. |
| `profile_code` | TEXT | اختیاری |  |  |
| `file_sha256` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `approved_by` → `users.id` · `created_by` → `users.id`

### `import_profiles`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `target_type` | TEXT | الزامی | `''` |  |
| `mapping_json` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

### `import_rows`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `batch_id` | INTEGER | الزامی |  |  |
| `row_number` | INTEGER | الزامی | `0` |  |
| `raw_json` | TEXT | الزامی | `''` |  |
| `mapped_json` | TEXT | الزامی | `''` |  |
| `status` | TEXT | الزامی | `'PENDING'` |  |
| `error_message` | TEXT | الزامی | `''` |  |
| `blank_fields_json` | TEXT | اختیاری |  | **ACTIVE** — Names of source columns that were blank — preserves "blank != zero". |
| `source_row_number` | INTEGER | اختیاری |  |  |

کلیدهای خارجی: `batch_id` → `import_batches.id`

### `journal_entries`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `doc_number` | TEXT | الزامی | `''` |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `void_reason` | TEXT | الزامی | `''` |  |
| `source_type` | TEXT | الزامی | `''` |  |
| `source_id` | INTEGER | اختیاری |  |  |
| `source_key` | TEXT | الزامی | `''` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `approved_by` → `users.id` · `created_by` → `users.id`

### `journal_lines`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `journal_id` | INTEGER | الزامی |  |  |
| `account_id` | INTEGER | الزامی |  |  |
| `debit_rial` | INTEGER | الزامی | `0` |  |
| `credit_rial` | INTEGER | الزامی | `0` |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `account_id` → `accounts.id` · `journal_id` → `journal_entries.id`

### `lots`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `weigh_ticket_id` | INTEGER | اختیاری |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `grade_id` | INTEGER | اختیاری |  |  |
| `packaging_id` | INTEGER | اختیاری |  |  |
| `warehouse_id` | INTEGER | اختیاری |  |  |
| `quantity_grams` | INTEGER | الزامی | `0` |  |
| `status` | TEXT | الزامی | `'OPEN'` |  |

کلیدهای خارجی: `warehouse_id` → `warehouses.id` · `packaging_id` → `packaging_types.id` · `grade_id` → `grades.id` · `product_id` → `products.id` · `weigh_ticket_id` → `weigh_tickets.id`

### `main_groups`  — 3 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `operation_types`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `operations`  — 7 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `direction` | TEXT | الزامی |  |  |
| `main_group_id` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `main_group_id` → `main_groups.id`

### `packaging_types`  — 4 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `parameters`  — 2 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `value_text` | TEXT | الزامی | `''` |  |
| `value_number` | REAL | اختیاری |  |  |
| `unit` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |
| `is_confirmed` | INTEGER | الزامی | `0` |  |

### `parties`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `display_name` | TEXT | الزامی |  |  |
| `nature` | TEXT | الزامی |  | **LEGACY** — Account-class code C/SL/S/E/X/F/L/CAP used to build system codes. |
| `national_code` | TEXT | الزامی | `''` |  |
| `phone` | TEXT | الزامی | `''` |  |
| `mobile` | TEXT | الزامی | `''` |  |
| `address` | TEXT | الزامی | `''` |  |
| `accounting_group_id` | INTEGER | اختیاری |  |  |
| `audit_group_id` | INTEGER | اختیاری |  |  |
| `is_active` | INTEGER | الزامی | `1` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `updated_at` | TEXT | الزامی | `datetime('now')` |  |
| `party_kind` | TEXT | اختیاری |  | **ACTIVE** — PERSON/COMPANY from the 01_Parties template; independent of `nature`. |
| `party_kind_confirmed` | INTEGER | الزامی | `0` | **ACTIVE** — 0 = backfilled by migration_002, owner has not confirmed. |
| `economic_code` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `audit_group_id` → `account_groups.id` · `accounting_group_id` → `account_groups.id`

### `partnership_events`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `partnership_id` | INTEGER | الزامی |  |  |
| `event_type` | TEXT | الزامی |  |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `load_type` | TEXT | الزامی | `''` |  |
| `basket_type` | TEXT | الزامی | `''` |  |
| `basket_count` | INTEGER | الزامی | `0` |  |
| `returned_basket_count` | INTEGER | الزامی | `0` |  |
| `weigh_grams` | INTEGER | الزامی | `0` | **LEGACY** — Pre-template column kept for old rows; do not write new values. |
| `net_grams` | INTEGER | الزامی | `0` |  |
| `rounding_mode` | TEXT | الزامی | `''` |  |
| `manual_loss_grams` | INTEGER | الزامی | `0` |  |
| `extra_waste_grams` | INTEGER | الزامی | `0` |  |
| `purchase_code` | TEXT | الزامی | `''` |  |
| `receipt_number` | TEXT | الزامی | `''` |  |
| `partner_share_grams` | INTEGER | الزامی | `0` |  |
| `our_share_grams` | INTEGER | الزامی | `0` |  |
| `loss_percent` | REAL | اختیاری |  |  |
| `basket_total_grams` | INTEGER | الزامی | `0` |  |
| `after_tare_grams` | INTEGER | الزامی | `0` |  |
| `loss_grams` | INTEGER | الزامی | `0` |  |
| `net_before_rounding_grams` | INTEGER | الزامی | `0` |  |
| `suggested_purchase_code` | TEXT | الزامی | `''` |  |
| `stock_effect` | TEXT | الزامی | `''` |  |
| `basket_custody_effect` | TEXT | الزامی | `''` |  |
| `warning` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `origin_place` | TEXT | اختیاری |  |  |
| `destination_place` | TEXT | اختیاری |  |  |
| `source_key` | TEXT | اختیاری |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `warehouse_id` | INTEGER | اختیاری |  |  |
| `basket_id` | INTEGER | اختیاری |  |  |
| `gross_grams` | INTEGER | اختیاری |  | **ACTIVE** — Template name; the legacy weigh_grams column is superseded. |
| `consumed_baskets` | INTEGER | اختیاری |  |  |
| `custody_returned_baskets` | INTEGER | اختیاری |  |  |
| `partner_share_percent` | REAL | اختیاری |  |  |
| `rounding_unit_grams` | INTEGER | اختیاری |  |  |
| `purchase_aggregation_id` | INTEGER | اختیاری |  |  |
| `description` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `purchase_aggregation_id` → `purchase_aggregations.id` · `basket_id` → `baskets.id` · `warehouse_id` → `warehouses.id` · `product_id` → `products.id` · `party_id` → `parties.id` · `partnership_id` → `partnerships.id`

### `partnerships`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `partner_party_id` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `partner_party_id` → `parties.id`

### `party_roles`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `party_id` | INTEGER | PK |  |  |
| `role` | TEXT | PK |  |  |

کلیدهای خارجی: `party_id` → `parties.id`

### `payment_allocations`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `payment_id` | INTEGER | الزامی |  |  |
| `invoice_id` | INTEGER | اختیاری |  | **LEGACY** — Superseded by purchase_invoice_id / sales_invoice_id (G-17). |
| `invoice_kind` | TEXT | اختیاری |  | **LEGACY** — Superseded by the typed invoice columns (G-17). |
| `purchase_invoice_id` | INTEGER | اختیاری |  |  |
| `sales_invoice_id` | INTEGER | اختیاری |  |  |
| `amount_rial` | INTEGER | الزامی | `0` |  |
| `source_key` | TEXT | اختیاری |  |  |
| `instrument_type` | TEXT | اختیاری |  |  |
| `description` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `sales_invoice_id` → `sales_invoices.id` · `purchase_invoice_id` → `purchase_invoices.id` · `payment_id` → `payments.id`

### `payments`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  | **ACTIVE** — شناسه داخلی (PAY001)؛ هرگز با شماره سند اشتباه نشود. |
| `party_id` | INTEGER | اختیاری |  |  |
| `bank_account_id` | INTEGER | اختیاری |  |  |
| `txn_type_id` | INTEGER | اختیاری |  |  |
| `direction` | TEXT | الزامی |  |  |
| `amount_rial` | INTEGER | الزامی | `0` |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `void_reason` | TEXT | الزامی | `''` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `instrument_type` | TEXT | اختیاری |  |  |
| `cheque_id` | INTEGER | اختیاری |  |  |
| `doc_number` | TEXT | اختیاری |  | **ACTIVE** — شماره سند پرداخت که کاربر می‌خواند؛ `code` شناسه داخلی پایدار است و این دو یکی نیستند. |

کلیدهای خارجی: `cheque_id` → `cheques.id` · `approved_by` → `users.id` · `created_by` → `users.id` · `txn_type_id` → `txn_types.id` · `bank_account_id` → `bank_accounts.id` · `party_id` → `parties.id`

### `permissions`  — 23 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |

### `product_groups`  — 1 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `parent_id` | INTEGER | اختیاری |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `parent_id` → `product_groups.id`

### `products`  — 4 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `group_id` | INTEGER | اختیاری |  |  |
| `name` | TEXT | الزامی |  |  |
| `category` | TEXT | الزامی | `''` |  |
| `unit_id` | INTEGER | اختیاری |  |  |
| `is_buy` | INTEGER | الزامی | `0` |  |
| `is_sell` | INTEGER | الزامی | `0` |  |
| `description` | TEXT | الزامی | `''` |  |
| `variety_name` | TEXT | اختیاری |  |  |
| `is_active` | INTEGER | الزامی | `1` |  |

کلیدهای خارجی: `unit_id` → `units.id` · `group_id` → `product_groups.id`

### `purchase_aggregations`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `load_type` | TEXT | الزامی | `''` |  |
| `row_count` | INTEGER | الزامی | `0` |  |
| `weigh_total_grams` | INTEGER | الزامی | `0` |  |
| `net_total_grams` | INTEGER | الزامی | `0` |  |
| `basket_count` | INTEGER | الزامی | `0` |  |
| `buy_rate_rial` | INTEGER | الزامی | `0` |  |
| `base_amount_rial` | INTEGER | الزامی | `0` |  |
| `agreed_discount_rial` | INTEGER | الزامی | `0` |  |
| `final_agreed_rial` | INTEGER | الزامی | `0` |  |
| `paid_rial` | INTEGER | الزامی | `0` |  |
| `payment_difference_rial` | INTEGER | الزامی | `0` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `party_id` → `parties.id`

### `purchase_invoice_lines`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `invoice_id` | INTEGER | الزامی |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `grams` | INTEGER | الزامی | `0` |  |
| `rate_rial_per_kg` | INTEGER | الزامی | `0` |  |
| `gross_rial` | INTEGER | الزامی | `0` |  |
| `discount_rial` | INTEGER | الزامی | `0` |  |
| `freight_rial` | INTEGER | الزامی | `0` |  |
| `commission_rial` | INTEGER | الزامی | `0` |  |
| `adjustments_rial` | INTEGER | الزامی | `0` |  |
| `net_rial` | INTEGER | الزامی | `0` |  |
| `weigh_ticket_id` | INTEGER | اختیاری |  |  |

کلیدهای خارجی: `weigh_ticket_id` → `weigh_tickets.id` · `product_id` → `products.id` · `invoice_id` → `purchase_invoices.id`

### `purchase_invoices`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `doc_number` | TEXT | الزامی | `''` |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `weigh_ticket_id` | INTEGER | اختیاری |  |  |
| `lot_id` | INTEGER | اختیاری |  |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `void_reason` | TEXT | الزامی | `''` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `source_key` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `approved_by` → `users.id` · `created_by` → `users.id` · `lot_id` → `lots.id` · `weigh_ticket_id` → `weigh_tickets.id` · `party_id` → `parties.id`

### `role_permissions`  — 52 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `role_id` | INTEGER | PK |  |  |
| `permission_id` | INTEGER | PK |  |  |

کلیدهای خارجی: `permission_id` → `permissions.id` · `role_id` → `roles.id`

### `roles`  — 3 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `sales_invoice_lines`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `invoice_id` | INTEGER | الزامی |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `grade_id` | INTEGER | اختیاری |  |  |
| `packaging_id` | INTEGER | اختیاری |  |  |
| `grams` | INTEGER | الزامی | `0` |  |
| `rate_rial_per_kg` | INTEGER | الزامی | `0` |  |
| `gross_rial` | INTEGER | الزامی | `0` |  |
| `discount_rial` | INTEGER | الزامی | `0` |  |
| `freight_rial` | INTEGER | الزامی | `0` |  |
| `commission_rial` | INTEGER | الزامی | `0` |  |
| `other_costs_rial` | INTEGER | الزامی | `0` |  |
| `net_rial` | INTEGER | الزامی | `0` |  |
| `sorting_output_id` | INTEGER | اختیاری |  |  |

کلیدهای خارجی: `sorting_output_id` → `sorting_outputs.id` · `packaging_id` → `packaging_types.id` · `grade_id` → `grades.id` · `product_id` → `products.id` · `invoice_id` → `sales_invoices.id`

### `sales_invoices`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `doc_number` | TEXT | الزامی | `''` |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `lot_id` | INTEGER | اختیاری |  |  |
| `sorting_batch_id` | INTEGER | اختیاری |  |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `void_reason` | TEXT | الزامی | `''` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `source_key` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `approved_by` → `users.id` · `created_by` → `users.id` · `sorting_batch_id` → `sorting_batches.id` · `lot_id` → `lots.id` · `party_id` → `parties.id`

### `schema_field_notes`  — 24 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `table_name` | TEXT | الزامی |  |  |
| `column_name` | TEXT | الزامی |  |  |
| `status` | TEXT | الزامی | `'ACTIVE'` |  |
| `note` | TEXT | الزامی | `''` |  |

### `schema_migrations`  — 4 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `version` | INTEGER | PK |  |  |
| `name` | TEXT | الزامی |  |  |
| `applied_at` | TEXT | الزامی | `datetime('now')` |  |
| `checksum` | TEXT | الزامی | `''` |  |

### `sequences`  — 10 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `name` | TEXT | PK |  |  |
| `prefix` | TEXT | الزامی | `''` |  |
| `next_number` | INTEGER | الزامی | `1` |  |

### `sorting_batches`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `lot_id` | INTEGER | اختیاری |  |  |
| `input_grams` | INTEGER | الزامی | `0` |  |
| `output_grams` | INTEGER | الزامی | `0` |  |
| `waste_grams` | INTEGER | الزامی | `0` |  |
| `process_loss_grams` | INTEGER | الزامی | `0` |  |
| `variance_grams` | INTEGER | الزامی | `0` | **DERIVED** — Must equal input - (output + waste + process_loss); approved only inside tolerance. |
| `tolerance_grams` | INTEGER | الزامی | `0` |  |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `source_key` | TEXT | اختیاری |  |  |
| `date_shamsi` | TEXT | اختیاری |  |  |
| `description` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `approved_by` → `users.id` · `created_by` → `users.id` · `lot_id` → `lots.id`

### `sorting_inputs`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `batch_id` | INTEGER | الزامی |  |  |
| `lot_id` | INTEGER | اختیاری |  |  |
| `grams` | INTEGER | الزامی | `0` |  |

کلیدهای خارجی: `lot_id` → `lots.id` · `batch_id` → `sorting_batches.id`

### `sorting_outputs`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `batch_id` | INTEGER | الزامی |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `grade_id` | INTEGER | اختیاری |  |  |
| `packaging_id` | INTEGER | اختیاری |  |  |
| `warehouse_id` | INTEGER | اختیاری |  |  |
| `grams` | INTEGER | الزامی | `0` |  |
| `package_count` | INTEGER | الزامی | `0` |  |
| `code` | TEXT | اختیاری |  | **ACTIVE** — شناسه خروجی سورت برای ارجاع در فاکتور فروش. |

کلیدهای خارجی: `warehouse_id` → `warehouses.id` · `packaging_id` → `packaging_types.id` · `grade_id` → `grades.id` · `product_id` → `products.id` · `batch_id` → `sorting_batches.id`

### `staff`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `party_id` | INTEGER | الزامی |  |  |
| `work_group_id` | INTEGER | اختیاری |  |  |
| `position` | TEXT | الزامی | `''` |  |
| `card_number` | TEXT | الزامی | `''` |  |
| `sheba` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `work_group_id` → `work_groups.id` · `party_id` → `parties.id`

### `stock_movements`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `lot_id` | INTEGER | اختیاری |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `grade_id` | INTEGER | اختیاری |  |  |
| `packaging_id` | INTEGER | اختیاری |  |  |
| `warehouse_id` | INTEGER | اختیاری |  |  |
| `movement_type` | TEXT | الزامی |  |  |
| `quantity_grams` | INTEGER | الزامی |  |  |
| `quantity_count` | INTEGER | الزامی | `0` |  |
| `ref_type` | TEXT | الزامی | `''` |  |
| `ref_id` | INTEGER | اختیاری |  |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |

کلیدهای خارجی: `warehouse_id` → `warehouses.id` · `packaging_id` → `packaging_types.id` · `grade_id` → `grades.id` · `product_id` → `products.id` · `lot_id` → `lots.id`

### `sub_groups`  — 5 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `main_group_id` | INTEGER | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `main_group_id` → `main_groups.id`

### `txn_types`  — 6 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `effect_on_balance` | TEXT | الزامی | `''` |  |
| `color_hex` | TEXT | الزامی | `''` |  |
| `description` | TEXT | الزامی | `''` |  |

### `units`  — 7 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

### `user_keys`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `user_id` | INTEGER | الزامی |  |  |
| `key_hash` | TEXT | الزامی |  |  |
| `key_prefix` | TEXT | الزامی | `''` |  |
| `is_revoked` | INTEGER | الزامی | `0` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `revoked_at` | TEXT | اختیاری |  |  |
| `expires_at` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `user_id` → `users.id`

### `users`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `username` | TEXT | الزامی |  |  |
| `display_name` | TEXT | الزامی |  |  |
| `role_id` | INTEGER | الزامی |  |  |
| `password_hash` | TEXT | الزامی |  |  |
| `password_salt` | TEXT | الزامی |  |  |
| `is_active` | INTEGER | الزامی | `1` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `last_login_at` | TEXT | اختیاری |  |  |

کلیدهای خارجی: `role_id` → `roles.id`

### `wage_shares`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `wage_id` | INTEGER | الزامی |  |  |
| `member_party_id` | INTEGER | اختیاری |  |  |
| `share_rial` | INTEGER | الزامی | `0` |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `member_party_id` → `parties.id` · `wage_id` → `employee_wages.id`

### `warehouses`  — 1 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `name` | TEXT | الزامی |  |  |
| `location` | TEXT | الزامی | `''` |  |
| `keeper_party_id` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `keeper_party_id` → `parties.id`

### `waste_records`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `batch_id` | INTEGER | اختیاری |  |  |
| `grams` | INTEGER | الزامی | `0` |  |
| `reason` | TEXT | الزامی | `''` |  |

کلیدهای خارجی: `batch_id` → `sorting_batches.id`

### `weigh_tickets`  — 0 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `doc_number` | TEXT | الزامی | `''` |  |
| `date_iso` | TEXT | الزامی | `''` |  |
| `date_shamsi` | TEXT | الزامی | `''` |  |
| `time` | TEXT | الزامی | `''` |  |
| `operation_id` | INTEGER | اختیاری |  |  |
| `direction` | TEXT | الزامی |  |  |
| `party_id` | INTEGER | اختیاری |  |  |
| `sub_group_id` | INTEGER | اختیاری |  |  |
| `product_id` | INTEGER | اختیاری |  |  |
| `gross_kg_raw` | TEXT | الزامی | `''` | **ACTIVE** — Raw scale reading kept verbatim for traceability (ch.8). |
| `gross_grams` | INTEGER | الزامی | `0` |  |
| `tare_grams` | INTEGER | الزامی | `0` |  |
| `loss_grams` | INTEGER | الزامی | `0` |  |
| `net_grams` | INTEGER | الزامی | `0` |  |
| `basket_count` | INTEGER | الزامی | `0` |  |
| `basket_id` | INTEGER | اختیاری |  |  |
| `amount_rial` | INTEGER | الزامی | `0` | **DEPRECATED** — Money never enters via the weighbridge (DEC-NEW-007). Reports must not read this column; use the journal. |
| `status` | TEXT | الزامی | `'DRAFT'` |  |
| `void_reason` | TEXT | الزامی | `''` |  |
| `param_snapshot` | TEXT | الزامی | `''` |  |
| `created_by` | INTEGER | اختیاری |  |  |
| `approved_by` | INTEGER | اختیاری |  |  |
| `description` | TEXT | الزامی | `''` |  |
| `created_at` | TEXT | الزامی | `datetime('now')` |  |
| `source_key` | TEXT | اختیاری |  |  |
| `packaging_id` | INTEGER | اختیاری |  |  |
| `package_count` | INTEGER | الزامی | `0` | **OPTIONAL** — 0 means "not recorded"; use has_packages in v_weigh_ticket_import. |
| `receipt_number` | TEXT | اختیاری |  | **OPTIONAL** — Blank means "no receipt issued", not receipt 0. |
| `warehouse_id` | INTEGER | اختیاری |  | **ACTIVE** — Which warehouse received the goods. Absent before v003 — the weighing could not say where it went. |

کلیدهای خارجی: `warehouse_id` → `warehouses.id` · `packaging_id` → `packaging_types.id` · `approved_by` → `users.id` · `created_by` → `users.id` · `basket_id` → `baskets.id` · `product_id` → `products.id` · `sub_group_id` → `sub_groups.id` · `party_id` → `parties.id` · `operation_id` → `operations.id`

### `work_groups`  — 1 ردیف در دیتابیس تازه

| ستون | نوع | الزام | پیش‌فرض | یادداشت |
|---|---|---|---|---|
| `id` | INTEGER | PK |  |  |
| `code` | TEXT | الزامی |  |  |
| `title` | TEXT | الزامی |  |  |
| `description` | TEXT | الزامی | `''` |  |

## ایندکس‌ها

- `ix_audit_entity`
- `ix_bank_account`
- `ix_parties_nature`
- `ix_pil_weigh`
- `ix_products_active`
- `ix_sil_sortout`
- `ix_stock_key`
- `ix_user_keys_user`
- `ix_weigh_party`
- `ix_weigh_status`
- `ix_weigh_warehouse`
- `ux_alloc_source_key`
- `ux_bank_source_key`
- `ux_basket_source_key`
- `ux_cheques_sayad`
- `ux_cheques_source_key`
- `ux_journal_source_key`
- `ux_parties_economic_code`
- `ux_partnership_source_key`
- `ux_payments_doc_number`
- `ux_purchase_source_key`
- `ux_sales_source_key`
- `ux_sorting_output_code`
- `ux_sorting_source_key`
- `ux_weigh_source_key`
