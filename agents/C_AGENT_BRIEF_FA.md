# ایجنت C — پورت C# لایه دادهٔ داشبورد

**دستور:** همان نوزده کوئری‌ای که ایجنت A در پایتون اثبات کرد، در C# پیاده کن،
روی SQLite، بدون هیچ کتابخانه UI. SQL باید **کاراکتر به کاراکتر** با پایتون
یکی باشد، وگرنه دو عدد مختلف روی دو صفحه می‌بینی.

## تصمیم‌های معماری

1. **اینترفیس جدا از پیاده‌سازی.** `IDashboardStore` تعریف می‌کند،
   `SqliteDashboardStore` اجرا می‌کند. دلیل عملی: در تست ویندوز می‌توان یک
   `FakeDashboardStore` داد و UI را بدون دیتابیس بالا آورد.

2. **همان سه عدد.** `KpiValue` سه فیلد دارد: `Approved`, `Review`, `Value`.
   داشبورد اگر یکی را نشان دهد و دو تا را نه، تصمیم غلط می‌گیرد.

3. **`decimal` نه `double`.** مبلغ ریالی با `double` جمع شود، در ۱۰٬۰۰۰ سند
   چند ریال اختلاف می‌دهد. SQLite عدد را INTEGER می‌دهد؛ تبدیل به `long` و بعد
   `decimal` انجام می‌شود، نه از `double`.

4. **هیچ SQL ای در UI.** اگر ویو مجبور شود کوئری بنویسد، عدد غیرقابل تست
   می‌شود. تنها راه دسترسی، متدهای اینترفیس است.

5. **`LangVersion 7.3`.** پروژه روی .NET Framework 4.8 قفل است و کامپایلر
   پیش‌فرض VS2019 با 7.3 کار می‌کند. یعنی: بدون `switch` expression، بدون
   `record`، بدون `nameof` در attribute، بدون nullable reference types.

## تحویل

- `src/Mazandasht.Application/Dashboard/IDashboardStore.cs`
- `src/Mazandasht.Application/Dashboard/KpiValue.cs`
- `src/Mazandasht.Application/Dashboard/SqliteDashboardStore.cs`
- `src/Mazandasht.Tests/DashboardStoreTests.cs` (برچسب: NOT RUN)

**صادقانه:** این کد کامپایل نشده است. هر ادعایی درباره درستی‌اش تا اجرا روی
ویندوز، ادعا نیست — حدس است. برچسب `NOT RUN` تا آن روز می‌ماند.
