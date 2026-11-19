# گزارش مرحله — Schema v002 (رفع شکاف قالب‌های مالک)

**تاریخ:** 2026-11-17 · **شاخه:** `arena/2e885c97-sorting-os` · **پایه:** `c6c9f12`

> ⚠️ **این گزارش یک عکس لحظه‌ای تاریخی است.** اعداد و وضعیت داخل آن مربوط به
> همان commit پایه است و امروز جلوتر رفته‌اند. برای وضعیت فعلی:
> `README.md` (جدول بالا) و `python3 tools/verify_all.py`.

---

## ۱. چه ساخته شد

| فایل | نقش |
|---|---|
| `database/migrations/002_v002_workbook_alignment.sql` | مهاجرت v001 → v002: ۲ بازسازی جدول، ۲۰ ستون، ۹ تریگر، ۲ ویو، فرهنگ داده درون‌دیتابیسی |
| `src/Mazandasht.Persistence/MigrationRunner.cs` | بازنویسی کامل: pragma بیرون تراکنش، checksum، تشخیص drift، FK/integrity قبل از COMMIT |
| `src/Mazandasht.Persistence/DatabaseBootstrapper.cs` | **جدید** — تنها مسیر ساخت/ارتقای دیتابیس؛ قبلاً هیچ کدی مهاجرت را صدا نمی‌زد |
| `src/Mazandasht.Persistence/Repositories.cs` | `PartyRepository` با `party_kind`/`economic_code`؛ خالی = NULL نه صفر |
| `src/Mazandasht.Domain/CodeGenerator.cs` | `PartyKind` (PERSON/COMPANY) جدا از `PartyNature` |
| `src/Mazandasht.Domain/Entities.cs` | `Party.PartyKind`, `PartyKindConfirmed`, `EconomicCode` |
| `tools/verify_database.py` | **۳۸ تست** (۱۸ نسخه v001 + ۲۰ نسخه v002) |
| `tools/gen_data_dictionary.py` | **جدید** — تولید `docs/DATA_DICTIONARY_FA.md` از اسکیمای واقعی |
| `docs/DATA_DICTIONARY_FA.md` | ۱۰۰۸ خط، ۶۲ جدول — تولیدشده، دستی نوشته نشده |

## ۲. آنچه تست شد (شاهد واقعی)

```
$ python3 tools/verify_database.py
...
38/38 PASS
```

تست‌های جدید v002، هر کدام **رفتار** را می‌سنجند نه وجود ستون را:

| تست | اثبات |
|---|---|
| `v002: migration applied` | نسخه ۲ ثبت شده |
| `v002: table rebuilds preserved rows, ids and upgraded legacy FKs` | ردیف و id قبل/بعد یکسان؛ FK قدیمی به تایپ‌دار ارتقا یافته |
| `v002: fresh install shape == upgraded install shape` | نصب تازه و ارتقایافته **ستون/تریگر/ایندکس یکسان** دارند |
| `G-01` | `COMPANY` + `SL` هم‌زمان روی یک ردیف؛ `ORGANIZATION` رد می‌شود |
| `G-02` | کد اقتصادی تکراری رد، خالی مجاز |
| `G-04/06/09` | واردسازی دوباره همان فایل = رد (source_key) |
| `G-05` | رسید خالی به‌عنوان `has_receipt_number=0` گزارش می‌شود نه «رسید صفر» |
| `G-07` | یک فاکتور، دو بار کامیون، هر خط تیکت باسکول خودش؛ خط با تیکت ناموجود رد |
| `G-11` | `TRANSFER`/`OPENING` پذیرفته، `SOLD` رد، `TRANSFER` بدون طرف مقابل رد |
| `G-12` | کارمزد جدا از اصل؛ `1000000 − 0 + 5000` |
| `G-14` | سررسید قبل از صدور رد (هم INSERT هم UPDATE) |
| `G-15` | صیاد ۱۵ رقمی/غیرعددی/تکراری رد |
| `G-17` | تخصیص به دو فاکتور یا صفر فاکتور رد؛ FK به فاکتور ناموجود رد |
| `G-19` | مبدأ/مقصد اختیاری و NULL برای رویداد غیرجابه‌جایی |
| `G-22` | پرچم known-ness + فرهنگ داده (۶ ردیف LEGACY/DEPRECATED) |
| `v002: DB guards` | موازنه جرم، سهم دستمزد، و **زنده‌بودن ۴ تریگر تغییرناپذیری ژورنال** |
| `v002: indexes survived` | هر ۹ ایندکس v001 + ۸ ایندکس جدید |
| `v002: rebuilt tables kept their CHECKs` | بازسازی، CHECKهای پول/مقدار را از دست نداده |

## ۳. چه چیزی تست نشد — و چرا

- **C# هرگز build/test نشد.** در این محیط `dotnet`, `mono`, `msbuild`, `csc` وجود ندارند. کد `MigrationRunner`/`DatabaseBootstrapper`/`Repositories` از نظر منطقی با همان الگوریتمی که در پایتون اثبات شد نوشته شده، اما **اجرای واقعی روی Windows 8.1 x64 انجام نشده**. وضعیت: `IMPLEMENTED / NOT RUN`.
- **Import واقعی فایل Excel انجام نشد** — لایه Import فقط اسکیما و ژورنال خالی‌ها را دارد.
- **تصمیم‌های مالک باز است:** backfill `party_kind_confirmed=0` (نیازمند مرور مالک)، و P01/P02.

## ۴. خطاها و نقص‌های پیدا و رفع‌شده

هشت نقص واقعی — فهرست کامل با شاهد در `reports/EXECUTION_LEDGER.md` بخش «NEW-03»:

1. backfill دو مقصد می‌ساخت و CHECK را می‌شکست.
2. محافظ چک فقط روی INSERT بود، UPDATE آزاد.
3. تلاش اول G-11 تریگر اضافه کرد ولی CHECK قدیمی سر جایش بود — `TRANSFER` هنوز رد می‌شد.
4. `PRAGMA foreign_keys=OFF` داخل تراکنش (بی‌اثر).
5. لودر مهاجرت فایل `migration_002.sql` را بی‌صدا رد می‌کرد.
6. هیچ مسیر اجرایی برای مهاجرت وجود نداشت.
7. checksum محاسبه نمی‌شد.
8. پنج فیکسچر تست خودم روی داده‌ای تکیه داشت که وجود نداشت.

## ۵. آنچه مالک باید بداند/انجام دهد

| موضوع | اقدام مالک |
|---|---|
| `party_kind` برای ردیف‌های موجود | فهرست `party_kind_confirmed=0` را مرور و تأیید کند (مهاجرت حدس زده و علامت گذاشته) |
| P01 / P02 | تأیید عددی (DEC-NEW-004) |
| ستون‌های «صفر به‌جای نامعلوم» | تصمیم: آیا `003` با بازسازی برای NULL واقعی لازم است؟ (DEC-NEW-012) |
| بکاپ قبل از مهاجرت | اسکریپت مهاجرت، بکاپ اجباری را صدا **نمی‌زند**؛ نصب‌کننده باید قبل از `EnsureCreated` بکاپ بگیرد |

## ۶. تنظیمات قابل تغییر (بدون کد)

همه در جدول `parameters` / `company_settings`: مسیر DB، حالت گرد کردن پول و وزن، `P01`, `P02`, آستانه اغماض موازنه جرم (`tolerance_grams`)، شماره‌گذاری اسناد (`sequences`)، حساب‌های کنترلی `SYS-*`.
