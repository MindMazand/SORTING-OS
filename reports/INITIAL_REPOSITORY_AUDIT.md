# ممیزی اولیه مخزن SORTING OS — Prompt 00

- زمان ممیزی: 2026-11-17 (UTC)
- URL مخزن تأییدشده: `https://github.com/MindMazand/SORTING-OS`
- branch فعال: `arena/2e885c97-sorting-os` (از `main` @ `62ad94739a2dafbf2419271d6dc28e6d38261ded`)
- commit SHA: `62ad94739a2dafbf2419271d6dc28e6d38261ded` ("Add files via upload", 2026-10-20)
- وضعیت worktree: تمیز (بدون تغییرات)
- عامل/ابزار: Arena.ai Agent Mode
- سیستم عامل و نسخه Python: Linux sandbox, Python 3.11.2, SQLite 3.40.1
- .NET / Mono / MSBuild: **موجود نیست** (ساخت WPF/.NET فقط روی Windows ممکن است)

## Project State Map

| مؤلفه | وضعیت/شاهد |
|---|---|
| IDENTITY | SORTING OS / مازندشت — ERP دسکتاپ آفلاین سورتینگ محصولات کشاورزی |
| TYPE | Offline Windows desktop operational + finance |
| STAGE | اسناد پایه موجود؛ **هیچ کد اجرایی در مخزن نیست** |
| CLIENT OBJECTIVE | جایگزینی سیستم Excel فعلی (INFO/Baskol/Transactions/Sales/Purchases/Expenses/Employees/Baskets/Cheques/Accounting + فایل شراکت) با نرم‌افزار یکپارچه |
| SOURCE STATUS | فقط ۱۵ فایل مستنداتی؛ بدون `desktop/`، بدون `docs/`، بدون `contracts/`، بدون `prompts/` مجزا، بدون تست، بدون CI |
| GEOMETRY STATUS | N/A — نرم‌افزار است |
| DESIGN STATUS | سند جدید مازندشت (v1.0) هویت بصری را تعریف می‌کند: سبز تیره `#075E1E`، RTL، Glassmorphism کنترل‌شده |
| VISUAL STATUS | هیچ UIای وجود ندارد |
| DECISION STATUS | سند جدید مالک (WPF/.NET 4.8/Win8.1) جایگزین سند قدیمی (Python/Tkinter/Win7) شد — ثبت در `docs/decision-log.md` |
| DELIVERY STATUS | فاز پایه‌سازی (اسکیما + هسته دامنه) در همین نوبت آغاز شد |

## سورس و گیت

- branchها/PRهای مشاهده‌شده: `main` و `arena/2e885c97-sorting-os`؛ هیچ PRای باز نیست.
- فایل‌های فعال: `PROJECT_SPEC.md` (v1.1 قدیمی)، `MASTER_PROMPT_FOR_AGENT_FA.md`، `ALL_PROMPTS_00_TO_35_FULL_FA.md` (۲۴۵۵ خط، متن یکپارچه ۳۶ پرامپت)، `PROMPT_INDEX_00_TO_35_FA.md`، `START_HERE_FA.md`، `HANDOFF_STATUS_FA.md`، `CONTRIBUTING.md`، `LICENSE-DECISION.md`، `reports/` (قالب‌ها)، `repository-patch/` (قالب‌ها).
- فایل‌های آرشیوی/ناموجود: ادعای `HANDOFF_STATUS_FA.md` درباره MVP دسکتاپ Python/Tkinter در `desktop/` و ۱۷ تست موفق **در این مخزن مصداق ندارد** — هیچ کد و تستی وجود ندارد. این همان حالت «مخزن خالی جدید» در `START_HERE_FA.md` است.
- تغییرات ناشناخته کاربر که حفظ شده‌اند: هیچ‌کدام (worktree تمیز).
- اقدامات انجام‌نشده و علت: استخراج منطق Excelها (فصل ۴–۶ سند جدید) به دلیل نبود فایل‌های `Mazandasht_[System.zip]` در مخزن و Google Drive (جست‌وجو شد: فقط پوشه `Google AI Studio` موجود است). ساخت WPF به دلیل نبود .NET در sandbox.

## تعارض‌های شناسایی‌شده (مصوبه مالک)

| # | موضوع | سند قدیمی (PROJECT_SPEC v1.1) | سند جدید مازندشت v1.0 (حاکم) |
|---|---|---|---|
| 1 | فناوری | Python/Tkinter | **WPF + C# + .NET Framework 4.8 + SQLite x64** |
| 2 | سیستم‌عامل هدف | Windows 7 SP1 x64 | **Windows 8.1 x64 به بالا** |
| 3 | مدل کاربری | چندکاربره ضمنی | **Single + تأیید مدیر (Manager Approval)** |
| 4 | موجودی | — | **Simple + Detailed** از یک Stock Ledger |
| 5 | نمایشگر دوم | — | پنجره مستقل در همان Process |
| 6 | دکمه + | — | منوی عملیات سریع از Registry |

## ماتریس وضعیت قابلیت

| حوزه | مسیر کد | وضعیت | فرمان/شاهد | گپ/ریسک |
|---|---|---|---|---|
| ریال/تومان integer rial | `src/Mazandasht.Domain/Money.cs` | IMPLEMENTED (NOT RUN) | بازبینی کد | ساخت روی Windows لازم است |
| وزن گرم صحیح + گردکردن | `src/Mazandasht.Domain/Weight.cs` | IMPLEMENTED (NOT RUN) | بازبینی کد | ساخت روی Windows لازم است |
| دفترکل دوبل | `database/schema/schema_v001.sql` + `LedgerRules.cs` | IMPLEMENTED + DB TESTED | `tools/verify_database.py` | posting خودکار اسناد عملیاتی در فاز بعد |
| تراز آزمایشی | ویو `v_journal_balance` | IMPLEMENTED + DB TESTED | `tools/verify_database.py` | گزارش WPF در فاز UI |
| اسکیمای دیتابیس (۵۲ موجودیت فصل ۱۸) | `database/schema/schema_v001.sql` | IMPLEMENTED + TESTED | `tools/verify_database.py` | — |
| داده پایه (کدها، P01/P02، بانک‌ها) | `database/seed/seed_v001.sql` | IMPLEMENTED + TESTED | `tools/verify_database.py` | مقادیر P01/P02 نیازمند تأیید عملیاتی |
| صافی/تسویه | `SettlementCalculator.cs` | IMPLEMENTED (NOT RUN) | بازبینی کد | مبنای صافی (DEC-003/004) باز است |
| بانک/چک | اسکیما + `BankTransactions` | PARTIAL | `tools/verify_database.py` | مغایرت‌گیری و تطبیق در فاز بعد |
| تقویم شمسی | ستون‌های `date_shamsi` | PARTIAL | — | کتابخانه شمسی در فاز UI |
| backup/restore | `BackupService.cs` + `backup_jobs` | IMPLEMENTED (NOT RUN) | SHA-256 در تست DB | تست restore روی Windows |
| Windows 8.1 x64 | — | NOT VERIFIED | — | نیازمند محیط هدف واقعی |
| فایل‌های Excel مرجع | — | BLOCKED | جست‌وجوی Drive: یافت نشد | مالک باید `Mazandasht_[System.zip]` را ارائه کند |

## فرمان‌ها و شواهد واقعی

| فرمان | کد خروج | نتیجه | Log/path |
|---|---|---|---|
| `git log/status` + فهرست فایل‌ها | 0 | فقط اسناد؛ بدون کد | همین گزارش |
| `python3 tools/verify_database.py` | 0 | ۲۲/۲۲ PASS (اسکیما، سید، قیود، تراز، موجودی، reset، SHA-256) | خروجی کنسول + `reports/BASELINE.md` |
| ساخت WPF/.NET | — | NOT RUN (ابزار .NET در sandbox نیست) | — |

## تصمیم‌های باز و ریسک‌های مسدودکننده

- **BLOCKED-01:** فایل‌های Excel مرجع (`Mazandasht_[System.zip]` + فایل شراکت با سعید بابایی) در دسترس نیستند؛ استخراج فرمول‌ها و تطبیق کامل فصل ۴–۶ ممکن نیست تا مالک فایل‌ها را بدهد.
- **DEC-001..012** (سند قدیمی) همچنان بازند؛ مهم‌ترین‌ها: مدل فعالیت (کارمزدی/خریدوفروش/ترکیبی)، مبنای صافی، روش ارزش‌گذاری موجودی، تقویم عملیاتی.
- **RISK-01:** Windows 8.1 پشتیبانی امنیتی عمومی ندارد (باید در مستندات استقرار ذکر شود — فصل ۳ سند جدید).
- **RISK-02:** ساخت و تست WPF فقط روی Windows 8.1+ با Visual Studio ممکن است؛ ادعای سازگاری بدون آزمون هدف ممنوع است.

## پیشنهاد مرحله بعد

فاز پایه‌سازی همین نوبت انجام شد: اسکیمای نسخه‌دار SQLite با تمام موجودیت‌های فصل ۱۸، داده پایه، هسته دامنه C# (پول/وزن/گردکردن/تراز/مغایرت سورتینگ/تسویه/کدینگ/امنیت)، اسکلت WPF و تست‌های DB اجراشده. مرحله بعد: اتصال posting خودکار اسناد عملیاتی به دفترکل + تکمیل UI ماژول‌ها، پس از ارائه فایل‌های Excel توسط مالک.
