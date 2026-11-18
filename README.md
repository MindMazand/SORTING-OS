# مازندشت — SORTING OS

**Repository description (GitHub):** Offline-first Windows desktop ERP for fruit-sorting operations, including intake, weighing, sorting, inventory, sales, settlements, bank/check workflows, and Persian financial reporting with Rial/Toman support.

مازندشت نرم‌افزار دسکتاپ مدیریت بازرگانی، حسابداری، سورتینگ و انبار محصولات کشاورزی است؛ جایگزین عملیاتی سیستم Excel فعلی. کاملاً آفلاین، فارسی و راست‌چین، با دیتابیس محلی SQLite.

## فناوری (سند مرجع v1.0)

- **WPF + C# + .NET Framework 4.8 + SQLite x64** روی **Windows 8.1 x64 به بالا**
- مدل کاربری: Single + تأیید مدیر (Manager Approval)
- پول داخلی: ریال صحیح؛ تومان صرفاً واحد نمایش (Toman = Rial / 10)
- وزن پایه: گرم صحیح؛ حداکثر ۳ رقم اعشار کیلوگرم در قالب‌های فعلی
- موجودی: Simple + Detailed از یک Stock Movement Ledger
- سند مرجع حاکم: `docs/MAZANDASHT_SPEC_FA.md` (در موارد تعارض بر `PROJECT_SPEC.md` مقدم است — DEC-NEW-001)

## وضعیت فعلی (2026-11-17)

| بخش | وضعیت | شاهد |
|---|---|---|
| اسکیمای دیتابیس (تمام موجودیت‌های فصل ۱۸) | ✅ IMPLEMENTED + TESTED | `database/schema/schema_v001.sql` + `database/migrations/002`…`005` + `tools/verify_database.py` → **40/40 PASS** (اسکیمای v5) |
| داده پایه (کدها، P01/P02، بانک‌ها، نقش‌ها) | IMPLEMENTED + TESTED | `database/seed/seed_v001.sql` |
| هسته دامنه C# (پول/وزن/تراز/تسویه/کدینگ/امنیت) | IMPLEMENTED (NOT RUN) | `src/Mazandasht.Domain` — ساخت روی Windows لازم است |
| پوسته WPF (داشبورد، دکمه +، نمایشگر دوم) | IMPLEMENTED (NOT RUN) | `src/Mazandasht.Presentation` |
| تست‌های C# (xUnit) | NOT RUN | `src/Mazandasht.Tests` — اجرا روی Windows |
| فایل‌های Excel مرجع | ✅ رفع شد (BLOCKED-01) | ۱۵ فایل سیستم + **۱۱ قالب واقعی** در `tests/fixtures/owner_templates/` دانلود شد و به‌عنوان مرجع تست استفاده می‌شود. **داده واقعی وجود ندارد** — `reports/OWNER_DATA_AUDIT_FA.md` |
| `schema_v002` + `v003` vs قالب‌های مالک | ✅ ساخته و تست شد | هر ۲۲ شکاف بسته شد (۲ بازسازی جدول + ۲۰ ستون + ۹ تریگر). `docs/decision-log.md` DEC-NEW-010..014 · `reports/STAGE_SCHEMA_V002_FA.md` |
| موتور واردسازی Excel (۷ مرحله) | ✅ IMPLEMENTED + TESTED | `tools/xlsx_io.py`, `import_contract.py`, `import_parser.py`, `import_engine.py` → `tools/test_import.py` **39/39 PASS** · `reports/STAGE_IMPORT_ENGINE_FA.md` |
| پورت C# موتور واردسازی | 🟡 IMPLEMENTED / NOT RUN | ۸ فایل در `src/Mazandasht.Application/Import/` + `SqliteImportStore.cs` + `SqliteImportBatchStore.cs`. نحو، تطبیق قرارداد (۱۲۹ ستون)، و ستون‌های اسکیما (۱۸۷) PASS — اما **کامپایل/اجرا نشده** · `reports/STAGE_CSHARP_PORT_FA.md` |
| پیش‌نیاز اختیاری | `python3 -m pip install --break-system-packages -r tools/requirements.txt` — بدون آن، بررسی صحت نحوی C# رد می‌شود ولی بقیه دروازه‌ها کار می‌کنند |
| بررسی‌های بدون .NET | ✅ ۲۲ دروازه | `python3 tools/verify_all.py` → اسکیما ۴۰/۴۰ · واردسازی ۳۹/۳۹ · تطبیق قرارداد · ستون↔اسکیما+طرح برگشت · نگاشت قرارداد↔اسکیما · ارجاع پروژه‌ها · زنجیره ۱۱ قالب · قالب‌های واقعی مالک · بردارهای طلایی · **۱۹ KPI داشبورد** · **parity SQL پایتون↔C#** · **اعداد SQL استخراج‌شده از C#** · **بازرس XAML** · **دامنه تأیید برگشت** · **جریان مرکز واردسازی** · **ردپای حسابرسی** · **کوئری‌های صفحه ابزارها** · **مهاجرت ۰۰۶ ستون پولی** · **شش گزارش مالی** · **SQL گزارش‌ها در C#** · **ناوبری بی‌اثر** · **هم‌ترازی گزارش‌ها** |
| فرهنگ داده (فصل ۱۸) | ✅ تولیدشده | `docs/DATA_DICTIONARY_FA.md` — با `tools/gen_data_dictionary.py` از اسکیمای واقعی ساخته می‌شود، دستی نیست |
| تأیید مالک برای `party_kind` | ⏳ منتظر مالک | ردیف‌های موجود با `party_kind_confirmed=0` علامت خورده‌اند؛ مالک باید مرور کند (DEC-NEW-011) |
| گزارش‌های مالی (BLOCKED-02) | 🟡 ۶ از ۷ + رابط | **شش گزارش ساختار کامل داشتند** و ساخته شدند (پایتون ۱۳/۱۳، C# ۸/۸، هم‌ترازی ۷/۷) و به رابط وصل شدند: `ReportsWindow`. فقط `Financial.xlsx → Report` واقعاً خالی است. `reports/REPORTS_UI_ROUND_FA.md` |

**وضعیت فعلی و کارهای بعدی: `reports/HANDOFF_NEXT_FA.md`**

جزئیات: `reports/INITIAL_REPOSITORY_AUDIT.md`، `reports/BASELINE.md` و `docs/WORKBOOK_SPEC_FA.md` (مشخصات قالب‌های کاری).

## ساخت روی Windows

> **صادقانه:** C# در محیط توسعهٔ خودکار این مخزن **کامپایل نشده**. هفت مسیر برای
> آوردن کامپایلر امتحان شد و هیچ‌کدام نشد؛ و مهم‌تر اینکه هدف WPF روی .NET
> Framework 4.8 است که روی لینوکس اصلاً build نمی‌شود. فقط یک مسیر نیمه‌کاره
> جواب داد: **.NET Core 2.0 runtime** دانلود و اجرا شد (بدون کامپایلر).
> گزارش کامل: `reports/CSHARP_BUILD_ATTEMPT_FA.md`. اعداد سبز زیر همه از
> پیاده‌سازی **پایتون** روی فایل‌های **واقعی** مالک می‌آیند.


1. Visual Studio 2019+ با .NET Framework 4.8 SDK و WPF را نصب کنید.
2. `src/Mazandasht.sln` را باز و Build کنید (x64).
3. تست‌ها: `dotnet test src/Mazandasht.Tests` (یا Test Explorer).
4. دیتابیس اولیه از `database/schema/schema_v001.sql` + `database/seed/seed_v001.sql` ساخته می‌شود (MigrationRunner).

## راستی‌آزمایی دیتابیس (بدون .NET)

```bash
python3 tools/verify_database.py   # 18 invariant tests on real SQLite
```

## قوانین مالی غیرقابل‌مذاکره

- مبالغ فقط به‌صورت ریال صحیح ذخیره می‌شوند؛ هرگز float برای پول استفاده نشود.
- تبدیل تومان به ریال دقیقاً با ضریب ۱۰؛ تغییر واحد نمایش نباید مقدار ذخیره‌شده را تغییر دهد.
- سند مالی قطعی باید متوازن باشد (بدهکار = بستانکار)؛ اصلاح فقط با برگشت/اصلاحیه، نه حذف یا ویرایش بی‌ردپا.
- موجودی و مانده‌ها از دفترهای گردش مشتق می‌شوند؛ ویرایش مستقیم مانده ممنوع.
- گزارش‌ها فقط از داده واقعی دفترکل ساخته می‌شوند؛ داده نمونه در محیط عملیاتی ممنوع.
- دیتابیس زنده هرگز در پوشه Google Drive Sync قرار نمی‌گیرد؛ فقط Backup می‌تواند آنجا باشد.

## نقشه مخزن

- `src/` — سورس C# لایه‌بندی‌شده (Domain / Application / Persistence / Infrastructure / Presentation / Tests)
- `database/` — اسکیما و سید نسخه‌دار SQLite
- `docs/` — سند مرجع مازندشت، دفتر تصمیمات، مشخصات قدیمی
- `tools/` — ابزار راستی‌آزمایی دیتابیس
- `reports/` — گزارش ممیزی، خط مبنا و دفتر اجرا
- `ALL_PROMPTS_00_TO_35_FULL_FA.md` — متن یکپارچه پرامپت‌های قدیمی (برای تاریخچه؛ فناوری آن Python/Tkinter بود و با DEC-NEW-001 جایگزین شد)

## هشدار استقرار

Windows 8.1 دیگر پشتیبانی امنیتی عمومی ندارد؛ این محدودیت باید در مستندات استقرار ذکر شود (فصل ۳ سند مرجع). ادعای سازگاری فقط پس از آزمون روی Windows 8.1 Update x64 واقعی پذیرفته است.
