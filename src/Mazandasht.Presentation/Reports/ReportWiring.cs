using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Mazandasht.Persistence;

namespace Mazandasht.Presentation.Reports
{
    /// <summary>
    /// The ONE place where the reports screen meets the report engine.
    ///
    /// ReportsViewModel takes delegates and knows nothing about SQLite; this
    /// class supplies them. Keeping the wiring in one file means "which report
    /// reads which table" can be read without opening a view model, and the
    /// view model stays testable with fakes.
    /// </summary>
    public static class ReportWiring
    {
        /// <summary>
        /// Build a view model backed by the real database.
        ///
        /// A missing database is NOT an exception here: the screen opens and
        /// says so. Throwing would mean the owner clicks Reports and gets a
        /// crash dialog, which tells them nothing about what to do.
        /// </summary>
        public static ReportsViewModel Create(string databasePath)
        {
            return new ReportsViewModel(
                () => ListReports(databasePath),
                id => Build(databasePath, id),
                () => databasePath,
                id => ExportCsv(databasePath, id),
                code => SetPartyCode(code));
        }

        private static List<ReportChoice> ListReports(string databasePath)
        {
            var choices = new List<ReportChoice>();
            bool dbPresent = !string.IsNullOrEmpty(databasePath)
                             && File.Exists(databasePath);

            var catalogue = new[]
            {
                Tuple.Create("cheques_issues", "چک‌های صادره",
                    "ثبت صدور هر چک با تاریخ، مبلغ، ذی‌نفع و وضعیت خودکار."),
                Tuple.Create("cheques_month", "گردش چک در بازه",
                    "همه چک‌های یک بازه زمانی با جمع کل، پاس‌شده و پاس‌نشده."),
                Tuple.Create("cheques_unpaid", "چک‌های پاس‌نشده",
                    "فقط چک‌های پاس‌نشده، به ترتیب تاریخ، با نزدیک‌ترین سررسید."),
                Tuple.Create("baskets_report", "مانده حساب فروشنده سبد",
                    "خرید سبد، پرداخت‌ها و مانده هر فروشنده. کد فروشنده را وارد کنید."),
                Tuple.Create("accounting_trial", "تراز آزمایشی",
                    "جمع بدهکار و بستانکار هر حساب، با کنترل توازن."),
                Tuple.Create("accounting_balance", "ترازنامه",
                    "دارایی، بدهی و حقوق صاحبان در سه بخش، با کنترل ترازنامه."),
                Tuple.Create("financial_report", "گزارش مالی",
                    "این گزارش ساختار ندارد.")
            };

            foreach (var item in catalogue)
            {
                var choice = new ReportChoice
                {
                    Id = item.Item1,
                    Title = item.Item2,
                    Description = item.Item3,
                    IsAvailable = true
                };

                if (item.Item1 == "financial_report")
                {
                    // The owner's own file says the layout is awaiting their
                    // definition. The card says so instead of opening an empty
                    // table that reads as "no data this period".
                    choice.IsAvailable = false;
                    choice.UnavailableReason =
                        "ساختار این گزارش هنوز تعریف نشده است. در فایل "
                        + "Financial.xlsx شیت Report نوشته شده: «ساختار و "
                        + "ستون‌ها در انتظار تعریف کارفرما هستند». پس از "
                        + "تعریف، این گزارش ساخته می‌شود.";
                }
                else if (!dbPresent)
                {
                    choice.IsAvailable = false;
                    choice.UnavailableReason =
                        "پایگاه داده پیدا نشد. ابتدا نصب اولیه را اجرا کنید.";
                }

                choices.Add(choice);
            }
            return choices;
        }

        private static ReportView Build(string databasePath, string reportId)
        {
            if (string.IsNullOrEmpty(databasePath) || !File.Exists(databasePath))
                throw new InvalidOperationException(
                    "پایگاه داده پیدا نشد: " + (databasePath ?? "(مسیر خالی)"));

            using (var store = new SqliteReportStore(databasePath))
            {
                ReportResult result;
                switch (reportId)
                {
                    case "cheques_issues":
                        result = store.ChequesIssues();
                        break;
                    case "cheques_month":
                        result = store.ChequesMonth("", "");
                        break;
                    case "cheques_unpaid":
                        result = store.ChequesUnpaid("", "");
                        break;
                    case "baskets_report":
                        // The party code arrives through the view model; an
                        // empty code is a real answer ("no seller"), not an
                        // error, so it is passed through rather than guessed.
                        result = store.BasketsReport(_lastPartyCode ?? "");
                        break;
                    case "accounting_trial":
                        result = store.AccountingTrial();
                        break;
                    case "accounting_balance":
                        result = store.AccountingBalance();
                        break;
                    case "financial_report":
                        throw new ReportUnavailableException(
                            "ساختار این گزارش هنوز تعریف نشده است.");
                    default:
                        throw new ArgumentException("گزارش ناشناخته: " + reportId,
                                                    "reportId");
                }

                return new ReportView
                {
                    Id = result.Id,
                    Title = result.Title,
                    Columns = result.Columns,
                    Rows = result.Rows,
                    TotalsLine = result.TotalsLine,
                    WarningText = result.WarningText
                };
            }
        }

        /// <summary>
        /// The party code for the baskets report.
        ///
        /// A static field is a compromise, and it is deliberate: threading a
        /// parameter through the delegate signature would change all six
        /// reports' call shape for the one report that needs it. The window is
        /// single-instance, so there is exactly one value in play. If a second
        /// parameterised report appears, this becomes a dictionary keyed by
        /// report id rather than a second static.
        /// </summary>
        private static string _lastPartyCode = "";

        public static void SetPartyCode(string code)
        {
            _lastPartyCode = code ?? "";
        }

        private static string ExportCsv(string databasePath, string reportId)
        {
            ReportView view = Build(databasePath, reportId);
            string folder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                "Mazandasht", "Reports");
            Directory.CreateDirectory(folder);
            string path = Path.Combine(folder,
                reportId + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".csv");

            // UTF-8 WITH BOM. Excel on Windows reads a BOM-less UTF-8 CSV as the
            // local ANSI codepage and turns every Persian column into mojibake.
            // The owner opens these in Excel; the BOM is the difference between
            // a usable file and garbage.
            using (var writer = new StreamWriter(path, false, new UTF8Encoding(true)))
            {
                writer.WriteLine(Join(view.Columns));
                foreach (string[] row in view.Rows)
                    writer.WriteLine(Join(row));
                if (!string.IsNullOrEmpty(view.TotalsLine))
                    writer.WriteLine();
                if (!string.IsNullOrEmpty(view.TotalsLine))
                    writer.WriteLine(view.TotalsLine);
            }
            return path;
        }

        private static string Join(string[] cells)
        {
            var sb = new StringBuilder();
            for (int i = 0; i < cells.Length; i++)
            {
                if (i > 0) sb.Append(',');
                string cell = cells[i] ?? "";
                // Quote anything that would break the column count or read as
                // a formula. A leading = or + in a CSV cell executes in Excel.
                bool needsQuotes = cell.IndexOf(',') >= 0
                                   || cell.IndexOf('"') >= 0
                                   || cell.IndexOf('\n') >= 0
                                   || cell.StartsWith("=")
                                   || cell.StartsWith("+")
                                   || cell.StartsWith("-");
                if (needsQuotes)
                    sb.Append('"').Append(cell.Replace("\"", "\"\"")).Append('"');
                else
                    sb.Append(cell);
            }
            return sb.ToString();
        }
    }
}
