-- ============================================================================
-- MAZANDASHT — Seed v001 (base definitions only; NO operational sample data)
-- These rows survive a database Reset (Spec ch. 15). Operational data
-- (invoices, weigh tickets, journal entries, ...) is never seeded.
-- ============================================================================

-- Roles (Spec ch. 10)
INSERT INTO roles (code, name, description) VALUES
 ('ADMIN',    'مدیر سیستم',   'دسترسی کامل شامل Reset و مدیریت کاربران'),
 ('MANAGER',  'مدیر',         'تأیید اسناد و عملیات حساس'),
 ('OPERATOR', 'اپراتور',      'ثبت عملیات بدون تأیید نهایی');

-- Permissions
INSERT INTO permissions (code, name) VALUES
 ('weigh.create',        'ثبت باسکول'),
 ('weigh.approve',       'تأیید باسکول'),
 ('sorting.create',      'ثبت سورتینگ'),
 ('sorting.approve',     'تأیید سورتینگ'),
 ('purchase.create',     'ثبت خرید'),
 ('purchase.approve',    'تأیید خرید'),
 ('sales.create',        'ثبت فروش'),
 ('sales.approve',       'تأیید فروش'),
 ('payment.create',      'ثبت دریافت/پرداخت'),
 ('payment.approve',     'تأیید دریافت/پرداخت'),
 ('bank.create',         'ثبت تراکنش بانکی'),
 ('bank.approve',        'تأیید تراکنش بانکی'),
 ('cheque.create',       'ثبت چک'),
 ('journal.create',      'ثبت سند حسابداری'),
 ('journal.approve',     'تأیید سند حسابداری'),
 ('party.create',        'ثبت طرف حساب'),
 ('masterdata.edit',     'ویرایش اطلاعات پایه'),
 ('import.create',       'ایجاد Import'),
 ('import.approve',      'تأیید نهایی Import'),
 ('backup.create',       'پشتیبان‌گیری'),
 ('backup.restore',      'بازیابی پشتیبان'),
 ('user.manage',         'مدیریت کاربران و کلیدها'),
 ('db.reset',            'پاکسازی دیتابیس (فقط مدیر)');

-- Role -> permission matrix (Operator cannot approve or reset)
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON 1=1
WHERE r.code = 'ADMIN';

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p
WHERE r.code = 'MANAGER' AND p.code NOT IN ('db.reset','user.manage','backup.restore');

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p
WHERE r.code = 'OPERATOR' AND p.code IN
 ('weigh.create','sorting.create','purchase.create','sales.create',
  'payment.create','bank.create','cheque.create','party.create','import.create');

-- Account groups (INFO.xlsx Groups sheet)
INSERT INTO account_groups (code, name) VALUES
 ('AG-CUSTOMER',  'مشتری'),
 ('AG-VENDOR',    'فروشنده'),
 ('AG-SUPPLIER',  'تأمین‌کننده'),
 ('AG-EMPLOYEE',  'کارمند'),
 ('AG-OTHER',     'سایر حساب'),
 ('AG-FIXED',     'دارایی ثابت'),
 ('AG-LOAN',      'وام و تسهیلات'),
 ('AG-CAPITAL',   'سرمایه و آورده صاحبان'),
 ('AG-ACCOUNTING','گروه حسابداری'),
 ('AG-AUDIT',     'گروه حسابرسی');

-- Main groups (G) — base operational groups
INSERT INTO main_groups (code, title, description) VALUES
 ('G-OPS',    'عملیات',        'گروه‌های اصلی عملیات'),
 ('G-FIN',    'مالی',          'گروه‌های مالی'),
 ('G-LOG',    'لجستیک',        'گروه‌های لجستیک');

INSERT INTO sub_groups (code, main_group_id, title) VALUES
 ('SG-WEIGH',  (SELECT id FROM main_groups WHERE code='G-OPS'), 'باسکول'),
 ('SG-SORT',   (SELECT id FROM main_groups WHERE code='G-OPS'), 'سورتینگ'),
 ('SG-BANK',   (SELECT id FROM main_groups WHERE code='G-FIN'), 'بانک'),
 ('SG-CHEQUE', (SELECT id FROM main_groups WHERE code='G-FIN'), 'چک'),
 ('SG-STOCK',  (SELECT id FROM main_groups WHERE code='G-LOG'), 'انبار');

INSERT INTO work_groups (code, title) VALUES
 ('WG-GENERAL', 'عمومی');

-- Units (Lists sheet: واحد شمارش)
INSERT INTO units (code, title) VALUES
 ('U-GRAM', 'گرم'),
 ('U-KG',   'کیلوگرم'),
 ('U-COUNT','عدد'),
 ('U-BASKET','سبد'),
 ('U-CARTON','کارتن'),
 ('U-BAG',  'کیسه'),
 ('U-CRATE','جعبه');

-- Product tree (Spec ch. 4.3): مرکبات as base catalog (editable, not hardcoded)
INSERT INTO product_groups (code, title) VALUES
 ('PG-CITRUS', 'مرکبات');

INSERT INTO products (code, group_id, name, category, unit_id, is_buy, is_sell) VALUES
 ('PB-ORANGE', (SELECT id FROM product_groups WHERE code='PG-CITRUS'), 'پرتقال',   'مرکبات', (SELECT id FROM units WHERE code='U-KG'), 1, 1),
 ('PB-MANDARIN',(SELECT id FROM product_groups WHERE code='PG-CITRUS'), 'نارنگی',  'مرکبات', (SELECT id FROM units WHERE code='U-KG'), 1, 1),
 ('PB-LEMON',  (SELECT id FROM product_groups WHERE code='PG-CITRUS'), 'لیمو',     'مرکبات', (SELECT id FROM units WHERE code='U-KG'), 1, 1),
 ('PB-GRAPE',  (SELECT id FROM product_groups WHERE code='PG-CITRUS'), 'گریپ‌فروت','مرکبات', (SELECT id FROM units WHERE code='U-KG'), 1, 1);

INSERT INTO grades (code, product_id, title) VALUES
 ('GR-ORANGE-1', (SELECT id FROM products WHERE code='PB-ORANGE'), 'درجه یک'),
 ('GR-ORANGE-2', (SELECT id FROM products WHERE code='PB-ORANGE'), 'درجه دو'),
 ('GR-ORANGE-3', (SELECT id FROM products WHERE code='PB-ORANGE'), 'درجه سه'),
 ('GR-ORANGE-W', (SELECT id FROM products WHERE code='PB-ORANGE'), 'ضایعات');

INSERT INTO packaging_types (code, title) VALUES
 ('PK-BASKET', 'سبد'),
 ('PK-CARTON', 'کارتن'),
 ('PK-BAG',    'کیسه'),
 ('PK-CRATE',  'جعبه');

-- Banks (BANK prefix; example accounts from Spec ch. 4.2)
INSERT INTO banks (code, name) VALUES
 ('BANK-MELLAT', 'ملت'),
 ('BANK-SADERAT','صادرات');

INSERT INTO bank_accounts (code, bank_id, display_name, opening_balance_rial) VALUES
 ('BANK01', (SELECT id FROM banks WHERE code='BANK-MELLAT'),  'ملت ـ جاری شرکت',   0),
 ('BANK02', (SELECT id FROM banks WHERE code='BANK-SADERAT'), 'صادرات ـ جاری شرکت', 0);

-- Transaction types with operational colors (Spec ch. 12)
INSERT INTO txn_types (code, title, effect_on_balance, color_hex) VALUES
 ('T-DEPOSIT',    'واریز',    'افزایش', '#E2F0D9'),
 ('T-WITHDRAW',   'برداشت',   'کاهش',   '#FCE4D6'),
 ('T-FEE',        'کارمزد',   'کاهش',   '#E4DFEC'),
 ('T-TRANSFER',   'انتقال',   'خنثی',   '#E7E6E6'),
 ('T-CHEQUE-PAY', 'پاس چک',   'کاهش',   '#FFF2CC'),
 ('T-CHEQUE-REC', 'وصول چک',  'افزایش', '#DDEBF7');

-- Base operations (OP prefix)
INSERT INTO operations (code, title, direction, main_group_id) VALUES
 ('OP-WEIGH-IN',  'باسکول ورودی',  'IN',  (SELECT id FROM main_groups WHERE code='G-OPS')),
 ('OP-WEIGH-OUT', 'باسکول خروجی',  'OUT', (SELECT id FROM main_groups WHERE code='G-OPS')),
 ('OP-SORTING',   'سورتینگ',       'OUT', (SELECT id FROM main_groups WHERE code='G-OPS')),
 ('OP-PURCHASE',  'خرید',          'IN',  (SELECT id FROM main_groups WHERE code='G-OPS')),
 ('OP-SALES',     'فروش',          'OUT', (SELECT id FROM main_groups WHERE code='G-OPS')),
 ('OP-STOCK-IN',  'ورود به انبار', 'IN',  (SELECT id FROM main_groups WHERE code='G-LOG')),
 ('OP-STOCK-OUT', 'خروج از انبار', 'OUT', (SELECT id FROM main_groups WHERE code='G-LOG'));

-- Baskets (BK prefix)
INSERT INTO baskets (code, name, capacity_grams, auto_label) VALUES
 ('BK01', 'سبد ۵ کیلویی', 5000, 1);

-- Warehouses (W prefix)
INSERT INTO warehouses (code, name, location) VALUES
 ('W01', 'انبار اصلی', '');

-- Parameters (P prefix). P01/P02 exist in the Excel files but MUST be
-- confirmed by the owner before operational activation (Spec ch. 5.1).
INSERT INTO parameters (code, name, value_text, value_number, unit, description, is_confirmed) VALUES
 ('P01', 'وزن تار عمومی سبد', '1.5', 1.5, 'کیلوگرم', 'وزن تار عمومی سبد از Baskol.xlsx؛ نیازمند تأیید مالک پیش از فعال‌سازی', 0),
 ('P02', 'درصد افت', '1', 1.0, 'درصد', 'درصد افت از Baskol.xlsx؛ نیازمند تأیید مالک پیش از فعال‌سازی', 0);

-- Chart of accounts (base set for double-entry posting)
INSERT INTO accounts (code, title, account_type) VALUES
 ('1000', 'صندوق',                 'ASSET'),
 ('1010', 'بانک',                  'ASSET'),
 ('1020', 'چک‌های دریافتی',       'ASSET'),
 ('1100', 'موجودی کالا',           'ASSET'),
 ('1200', 'بدهکاران',              'ASSET'),
 ('2000', 'بستانکاران',            'LIABILITY'),
 ('2100', 'چک‌های پرداختی',       'LIABILITY'),
 ('3000', 'سرمایه',                'EQUITY'),
 ('4000', 'فروش',                  'INCOME'),
 ('5000', 'خرید',                  'EXPENSE'),
 ('5100', 'هزینه‌ها',              'EXPENSE');

-- Company settings (Spec ch. 2, 17): money display, rounding, backup, dashboard
INSERT INTO company_settings (key, value, description) VALUES
 ('money.display_unit',        'RIAL',   'واحد نمایش پول: RIAL یا TOMAN (فقط نمایش؛ ذخیره همیشه ریال)'),
 ('money.rounding_mode',       'NEAREST','گردکردن پول: NONE / NEAREST / UP / DOWN'),
 ('money.rounding_unit_rial',  '1',      'واحد گردکردن پول به ریال'),
 ('weight.rounding_mode',      'NONE',   'گردکردن وزن: NONE / NEAREST / UP / DOWN (مستقل از پول)'),
 ('weight.rounding_unit_grams','1',      'واحد گردکردن وزن به گرم'),
 ('weight.max_kg_decimals',    '3',      'حداکثر رقم اعشار کیلوگرم در قالب‌های فعلی'),
 ('sorting.tolerance_grams',   '0',      'تلورانس مغایرت سورتینگ به گرم (قابل تنظیم)'),
 ('backup.daily_keep',         '7',      'تعداد نسخه روزانه'),
 ('backup.monthly_keep',       '3',      'تعداد نسخه منتخب هر ماه'),
 ('backup.max_total',          '30',     'حداکثر کل نسخه‌ها'),
 ('backup.destination',        '',       'مسیر ذخیره پشتیبان (پوشه محلی/حافظه خارجی/Google Drive Sync)'),
 ('dashboard.kpis',            '[]',     'کارت‌های KPI انتخاب‌شده داشبورد (JSON)'),
 ('dashboard.range_days',      '7',      'بازه پیش‌فرض داشبورد به روز');

-- Document sequences (display numbers independent of internal ids)
INSERT INTO sequences (name, prefix, next_number) VALUES
 ('weigh_ticket', 'WT-', 1),
 ('purchase_invoice','PI-', 1),
 ('sales_invoice',  'SI-', 1),
 ('journal',        'JE-', 1),
 ('payment',        'PAY-', 1),
 ('bank_transaction','BT-', 1),
 ('cheque',         'CHQ-', 1),
 ('sorting_batch',  'SB-', 1),
 ('import_batch',   'IMP-', 1),
 ('backup',         'BKP-', 1);

-- Schema version marker
INSERT INTO schema_migrations (version, name, checksum) VALUES
 (1, 'schema_v001 + seed_v001', 'mazandasht-v001');
