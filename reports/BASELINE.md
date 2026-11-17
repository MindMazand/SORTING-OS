# خط مبنا — مازندشت (Prompt 01)

- تاریخ: 2026-11-17
- branch: `arena/2e885c97-sorting-os`
- مبنا: `62ad94739a2dafbf2419271d6dc28e6d38261ded` (main)
- سند مرجع: `docs/MAZANDASHT_SPEC_FA.md` v1.0 (DEC-NEW-001)

## دستورات اجراشده و نتایج واقعی

| فرمان | نتیجه | توضیح |
|---|---|---|
| `python3 tools/verify_database.py` | **18/18 PASS** (exit 0) | ساخت دیتابیس موقت از `database/schema/schema_v001.sql` + `database/seed/seed_v001.sql` و اجرای ۱۸ تست ناوردایی |
| `dotnet build` / `dotnet test` | **NOT RUN** | ابزار .NET در sandbox نیست؛ ساخت WPF/.NET 4.8 فقط روی Windows 8.1+ با Visual Studio ممکن است |

## تست‌های دیتابیس (همه PASS)

1. وجود تمام موجودیت‌های فصل ۱۸ + ویوهای گزارشی
2. داده پایه: نقش‌ها، مجوزها (اپراتور بدون `db.reset`)، گروه‌ها، واحدها، بانک‌ها، پارامترها، حساب‌ها
3. `PRAGMA foreign_key_check` خالی
4. یکتایی کد طرف حساب (C/SL/S/E/X/F/L/CAP)
5. پول فقط ریال صحیح؛ تومان صرفاً نمایش
6. وزن فقط گرم صحیح؛ Net = Gross − Tare − Loss
7. P01 = ۱٫۵ کیلوگرم و P02 = ۱٪ موجود و `is_confirmed=0`
8. تراز دوبل: سند متوازن diff=0، سند نامتوازن شناسایی می‌شود
9. posting تکراری با `source_key` یکسان رد می‌شود
10. سند تأییدشده با تریگر قابل UPDATE/DELETE نیست
11. موجودی از روی گردش‌ها مشتق می‌شود (ستون مانده وجود ندارد)
12. وضعیت تأیید فقط DRAFT/REVIEW/APPROVED/VOIDED
13. جمع ریزسهم‌های دستمزد = مبلغ کل رویداد
14. موازنه سورتینگ: Input = Outputs + Waste + ProcessLoss + Variance
15. کنترل تکرار تراکنش بانکی با `source_key`
16. سبد مصرف‌شده و سبد برگشتی امانی دو فیلد جدا
17. Reset با جایگزینی دیتابیس: داده عملیاتی صفر، تعاریف پایه کامل
18. Backup: SHA-256، `integrity_check=ok`، نسخه اسکیما

## وضعیت کد C# (IMPLEMENTED — NOT RUN)

- `src/Mazandasht.Domain`: Money (ریال صحیح)، Weight (گرم صحیح)، گردکردن مستقل پول/وزن، ماشین وضعیت تأیید، قواعد تراز دوبل، موازنه سورتینگ، محاسبه تسویه/فاکتور، کدینگ پیشوندی.
- `src/Mazandasht.Application`: سرویس باسکول (Snapshot پارامتر)، سورتینگ، فاکتور، Backup (SHA-256 + Manifest)، Reset (عبارت `RESET MAZANDASHT`)، Registry ایمپورت.
- `src/Mazandasht.Infrastructure`: PBKDF2-HMAC-SHA256 با Salt مستقل، کلید خصوصی ۳۲ بایتی (فقط هش ذخیره می‌شود)، Audit.
- `src/Mazandasht.Persistence`: Migration نسخه‌دار تراکنشی، Repositoryهای طرف حساب/دفترکل/موجودی.
- `src/Mazandasht.Presentation`: پوسته WPF راست‌چین، تم سبز `#075E1E`، رنگ‌های عملیاتی بانکی، داشبورد KPI، دکمه + عملیات سریع، نمایشگر دوم.
- `src/Mazandasht.Tests`: ۷ فایل تست xUnit (اجرا روی Windows).

## موارد باز

- ساخت و تست C# روی Windows 8.1 x64 (NOT RUN).
- فایل‌های Excel مرجع در دسترس نیستند (BLOCKED-01)؛ تطبیق فرمول‌ها پس از ارائه فایل‌ها.
- تأیید مقادیر P01/P02 توسط مالک (DEC-NEW-004).
- تصمیم‌های DEC-001 تا DEC-012 (مدل فعالیت، مبنای صافی، ارزش‌گذاری موجودی و...).
