using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace Mazandasht.Application.Import
{
    public sealed class ParseOutcome
    {
        public ImportTemplate Template { get; set; }
        public string SheetName { get; set; } = "";
        public Dictionary<string, int> HeaderMap { get; set; } =
            new Dictionary<string, int>(StringComparer.Ordinal);
        public List<string> UnmatchedHeaders { get; } = new List<string>();
        public List<string> FileErrors { get; } = new List<string>();
        public List<string> Warnings { get; } = new List<string>();
        public List<ParsedRow> Rows { get; } = new List<ParsedRow>();
        public int IgnoredBlankRows { get; set; }

        public bool Ok => FileErrors.Count == 0;
        public IEnumerable<ParsedRow> ValidRows => Rows.Where(r => r.Ok);
        public IEnumerable<ParsedRow> InvalidRows => Rows.Where(r => !r.Ok);
    }

    /// <summary>One reference code resolved to a real database id.</summary>
    public sealed class LookupRequest
    {
        public LookupRequest(string templateCode, int sourceRow, string fieldName,
                             string lookupSpec, string code)
        {
            TemplateCode = templateCode;
            SourceRow = sourceRow;
            FieldName = fieldName;
            LookupSpec = lookupSpec;
            Code = code;
        }

        public string TemplateCode { get; }
        public int SourceRow { get; }
        public string FieldName { get; }
        /// <summary>"table:column", e.g. "parties:code".</summary>
        public string LookupSpec { get; }
        public string Code { get; }
    }

    /// <summary>
    /// Port of tools/import_parser.py + the cross-file rules of
    /// tools/import_engine.py.
    ///
    /// Stages 2-4 live here (detect, map, validate); stage 5 needs a database,
    /// so resolution is expressed as a list of <see cref="LookupRequest"/> that
    /// the persistence layer answers. That keeps this class unit-testable with
    /// no SQLite at all, while still making "an unknown code must not create a
    /// row" impossible to forget: the caller has no way to write a document
    /// without first resolving every request.
    /// </summary>
    public sealed class ImportEngine
    {
        private readonly ImportValidator _validator = new ImportValidator();

        // -- stage 2: detect -------------------------------------------------
        public ParseOutcome Parse(string path, string expectedTemplateCode = null)
        {
            var result = new ParseOutcome();
            XlsxReader reader;
            try
            {
                reader = new XlsxReader(path);
            }
            catch (XlsxException e)
            {
                result.FileErrors.Add(e.Message);
                return result;
            }

            using (reader)
            {
                string notes;
                var sheetName = FindDataSheet(reader, out notes);
                if (notes != null) result.Warnings.Add(notes);
                if (sheetName == null)
                {
                    result.FileErrors.Add("شیت «داده‌ها» پیدا نشد.");
                    return result;
                }
                result.SheetName = sheetName;

                var sheet = reader.GetSheet(sheetName);
                var template = DetectTemplate(sheet);
                if (template == null)
                {
                    result.FileErrors.Add(
                        "نوع فایل شناسایی نشد: کمتر از نیمی از سرستون‌ها با هیچ‌کدام از " +
                        "۱۱ قالب رسمی نمی‌خواند.");
                    return result;
                }
                result.Template = template;

                if (expectedTemplateCode != null &&
                    !string.Equals(expectedTemplateCode, template.Code, StringComparison.Ordinal))
                {
                    result.FileErrors.Add("نوع تشخیص‌داده‌شده (" + template.Code +
                                          ") با نوع انتخاب‌شده (" + expectedTemplateCode + ") نمی‌خواند.");
                    return result;
                }

                // -- stage 3: map --------------------------------------------
                var mapping = MapHeaders(template, sheet, result.UnmatchedHeaders);
                result.HeaderMap = mapping;
                if (result.UnmatchedHeaders.Count > 0)
                    result.Warnings.Add("سرستون‌های ناشناخته نادیده گرفته شد: " +
                                        string.Join("، ", result.UnmatchedHeaders));

                var missing = template.RequiredFields
                    .Where(f => !mapping.ContainsKey(f.NameEn))
                    .Select(f => f.NameFa).ToList();
                if (missing.Count > 0)
                {
                    result.FileErrors.Add("سرستون‌های الزامی گم شده‌اند: " +
                        string.Join("، ", missing) +
                        " — نگاشت ستون‌ها انجام نشد تا داده در جای اشتباه نوشته نشود.");
                    return result;
                }

                CheckMerges(sheet, result);

                // -- stage 4: validate ---------------------------------------
                var rowNumber = LastHeaderRow(template, sheet) + 1;
                var lastRow = Math.Max(sheet.MaxRow, rowNumber);
                while (rowNumber <= lastRow)
                {
                    var allBlank = mapping.Values.All(col => sheet.Cell(rowNumber, col).IsBlank);
                    if (allBlank)
                    {
                        result.IgnoredBlankRows++;
                        rowNumber++;
                        continue;
                    }
                    result.Rows.Add(_validator.Validate(template, sheet, rowNumber, mapping));
                    rowNumber++;
                }
                return result;
            }
        }

        private static string FindDataSheet(XlsxReader reader, out string note)
        {
            note = null;
            foreach (var name in reader.SheetNames)
                if (ImportContract.DataSheetNames.Contains(name.Trim(), StringComparer.Ordinal))
                    return name;

            foreach (var name in reader.SheetNames)
            {
                var sheet = reader.GetSheet(name);
                if (sheet.MaxCol >= 3 && sheet.MaxRow >= 2)
                {
                    note = "شیت استاندارد «داده‌ها» نبود؛ از شیت «" + name + "» استفاده شد.";
                    return name;
                }
            }
            return null;
        }

        private static ImportTemplate DetectTemplate(XlsxSheet sheet)
        {
            var headers = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (var r = 1; r <= 2; r++)
                for (var c = 1; c <= Math.Min(sheet.MaxCol, 60); c++)
                {
                    var text = sheet.Cell(r, c).Text.Trim();
                    if (text.Length > 0) headers.Add(text);
                }

            ImportTemplate best = null;
            double bestScore = 0;
            foreach (var template in ImportContract.All.Values)
            {
                var hits = template.Fields.Count(f =>
                    headers.Contains(f.NameEn) || headers.Contains(f.NameFa));
                var score = (double)hits / Math.Max(1, template.Fields.Count);
                if (score > bestScore)
                {
                    best = template;
                    bestScore = score;
                }
            }
            return bestScore < 0.5 ? null : best;
        }

        /// <summary>
        /// The last row that actually holds field labels.
        ///
        /// Counting header rows by POSITION is wrong in both directions: the
        /// two-row English+Persian layout puts data at row 3, and the owner's
        /// real workbooks (tests/fixtures/owner_templates) have ONE Persian
        /// header row, so their data starts at row 2. Using the constant
        /// DataStartRow silently skipped the owner's first data row on every
        /// real file. Asking the sheet which rows hold labels answers both.
        /// </summary>
        public static int LastHeaderRow(ImportTemplate template, XlsxSheet sheet)
        {
            var labels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var f in template.Fields)
            {
                labels.Add(f.NameEn);
                labels.Add(f.NameFa);
            }
            var last = 0;
            foreach (var rowNo in new[] { template.HeaderRowEn, template.HeaderRowFa })
            {
                if (rowNo > Math.Max(sheet.MaxRow, 1)) continue;
                for (var c = 1; c <= Math.Min(sheet.MaxCol, 200); c++)
                {
                    var text = sheet.Cell(rowNo, c).Text.Trim();
                    if (text.Length > 0 && labels.Contains(text))
                    {
                        if (rowNo > last) last = rowNo;
                        break;
                    }
                }
            }
            return last > 0 ? last : template.HeaderRowEn;
        }

        /// <summary>Match by header NAME, in either language, in either header
        /// row. A position-based mapping would write purchase weights into
        /// discount columns the moment a user reorders anything; requiring the
        /// English row would reject the owner's real files outright.</summary>
        public static Dictionary<string, int> MapHeaders(ImportTemplate template, XlsxSheet sheet,
                                                         List<string> unmatched)
        {
            var mapping = new Dictionary<string, int>(StringComparer.Ordinal);
            var used = new HashSet<int>();

            foreach (var rowNo in new[] { template.HeaderRowEn, template.HeaderRowFa })
            {
                for (var c = 1; c <= Math.Min(sheet.MaxCol, 200); c++)
                {
                    var text = sheet.Cell(rowNo, c).Text.Trim();
                    if (text.Length == 0) continue;
                    // either language in either row: the owner's `داده‌ها` sheet
                    // is Persian-only, while the English labels live in `فرهنگ داده`
                    var field = template.ByEn(text) ?? template.ByFa(text);
                    if (field != null && !mapping.ContainsKey(field.NameEn) && !used.Contains(c))
                    {
                        mapping[field.NameEn] = c;
                        used.Add(c);
                    }
                }
            }

            if (unmatched != null)
            {
                for (var c = 1; c <= Math.Min(sheet.MaxCol, 200); c++)
                {
                    var text = sheet.Cell(1, c).Text.Trim();
                    if (text.Length == 0) text = sheet.Cell(2, c).Text.Trim();
                    if (text.Length > 0 && !used.Contains(c))
                        unmatched.Add(text + " (ستون " + c + ")");
                }
            }
            return mapping;
        }

        private static void CheckMerges(XlsxSheet sheet, ParseOutcome result)
        {
            foreach (var m in sheet.Merges)
            {
                if (m.Item1 <= 2) continue;    // a merged title above the header is fine
                result.Warnings.Add("سلول ادغام‌شده در محدوده داده: ردیف " + m.Item1 +
                                    " تا " + m.Item3 +
                                    " — طبق قاعده قالب مجاز نیست و ممکن است باعث از دست رفتن مقدار شود.");
                break;
            }
        }

        // -- stage 5: what must be resolved ----------------------------------
        /// <summary>
        /// Every code in a valid row that must reach a real id. Returned as
        /// data so the caller cannot skip resolution, and so the rule is
        /// testable without a database.
        /// </summary>
        public static List<LookupRequest> LookupRequests(ImportTemplate template,
                                                         ParsedRow row)
        {
            var requests = new List<LookupRequest>();
            if (!row.Ok) return requests;

            foreach (var field in template.Fields)
            {
                if (field.Lookup == null) continue;
                var code = row.GetString(field.NameEn);
                if (string.IsNullOrEmpty(code)) continue;
                requests.Add(new LookupRequest(template.Code, row.SourceRow,
                                               field.NameEn, field.Lookup, code));
            }
            return requests;
        }

        // -- cross-file rules ------------------------------------------------
        /// <summary>
        /// Business rules that need more than one column. Applied after lookup
        /// resolution because several of them depend on resolved ids.
        /// Returns true when the row may be written.
        /// </summary>
        public static bool CheckRules(ImportTemplate template, ParsedRow row,
                                      out List<string> errors, out List<string> warnings)
        {
            errors = new List<string>();
            warnings = new List<string>();

            if (!row.Ok)
            {
                errors.AddRange(row.Errors.Select(e => e.Message));
                return false;
            }

            switch (template.Code)
            {
                case "WEIGHING_IN":
                {
                    var net = row.GetLong("NetKg");
                    var gross = row.GetLong("ScaleKg");
                    var tare = row.GetLong("TareKg") ?? 0;
                    if (net.HasValue && net.Value < 0)
                        errors.Add("وزن خالص منفی است — ورودی بار نمی‌تواند منفی باشد");
                    if (gross.HasValue && net.HasValue)
                    {
                        var natural = gross.Value - tare;
                        if (Math.Abs(natural - net.Value) > 1000)
                            warnings.Add("وزن خالص فایل (" + Kg(net.Value) +
                                         ") با «ناخالص − تار» (" + Kg(natural) +
                                         ") بیش از ۱ کیلو اختلاف دارد؛ مقدار فایل ثبت می‌شود.");
                    }
                    var direction = row.GetString("Direction");
                    if (direction != null && direction != "IN")
                        errors.Add("در قالب باسکول ورودی، جهت فقط IN مجاز است");
                    break;
                }

                case "SORTING":
                {
                    var input = row.GetLong("InputKg") ?? 0;
                    var output = row.GetLong("OutputKg") ?? 0;
                    var waste = row.GetLong("WasteKg") ?? 0;
                    var loss = row.GetLong("ProcessLossKg") ?? 0;
                    var tolerance = row.GetLong("ToleranceKg");
                    var variance = input - (output + waste + loss);
                    if (!tolerance.HasValue)
                    {
                        warnings.Add("تلورانس ذکر نشده؛ مغایرت با تلورانس پیش‌فرض سیستم سنجیده می‌شود");
                        tolerance = 0;
                    }
                    if (Math.Abs(variance) > Math.Max(tolerance.Value, 0))
                        errors.Add("موازنه جرم برقرار نیست: ورودی " + Kg(input) +
                                   " ≠ خروجی+ضایعات+افت " + Kg(output + waste + loss) +
                                   " (مغایرت " + Kg(variance) + "، تلورانس " + Kg(tolerance.Value) + ")");
                    break;
                }

                case "BASKET_MOVEMENTS":
                {
                    var qty = row.GetLong("Quantity");
                    if (qty.HasValue && qty.Value < 0)
                        errors.Add("تعداد سبد نمی‌تواند منفی باشد");
                    var type = row.GetString("MovementType");
                    if (type == "TRANSFER")
                    {
                        if (string.IsNullOrEmpty(row.GetString("FromWarehouseCode")))
                            errors.Add("انتقال سبد نیازمند انبار مبدأ است");
                        if (string.IsNullOrEmpty(row.GetString("ToWarehouseCode")))
                            errors.Add("انتقال سبد نیازمند انبار مقصد است");
                    }
                    break;
                }

                case "CHEQUES":
                {
                    var sayad = row.GetString("SayadId");
                    if (!string.IsNullOrEmpty(sayad) &&
                        (sayad.Length != 16 || !sayad.All(char.IsDigit)))
                        errors.Add("شناسه صیادی باید دقیقاً ۱۶ رقم باشد");
                    var issue = row.GetString("IssueDateShamsi");
                    var due = row.GetString("DueDateShamsi");
                    if (!string.IsNullOrEmpty(issue) && !string.IsNullOrEmpty(due) &&
                        string.CompareOrdinal(due, issue) < 0)
                        errors.Add("تاریخ سررسید نمی‌تواند قبل از تاریخ صدور باشد");
                    break;
                }

                case "PURCHASE_INVOICES":
                case "SALES_INVOICES":
                {
                    var grams = row.GetLong(template.Code == "PURCHASE_INVOICES"
                        ? "PurchaseKg" : "SaleKg");
                    var rate = row.GetLong("RateRialPerKg");
                    if (grams.HasValue && rate.HasValue && GrossRial(grams.Value, rate.Value) <= 0)
                        errors.Add("مبلغ ناخالص فاکتور صفر یا منفی است");
                    break;
                }

                case "SETTLEMENTS":
                {
                    var amount = row.GetLong("AllocationRial");
                    if (!amount.HasValue || amount.Value <= 0)
                        errors.Add("مبلغ تخصیص باید مثبت باشد");
                    break;
                }
            }

            return errors.Count == 0;
        }

        /// <summary>gross = round-half-up(grams * rate / 1000) in integer Rial.
        /// Integer maths only: floating point money is forbidden by spec.</summary>
        public static long GrossRial(long grams, long rateRialPerKg)
        {
            return (grams * rateRialPerKg + 500) / 1000;
        }

        /// <summary>Purchase net: gross + freight + commission + adjustments - discount.</summary>
        public static long PurchaseNetRial(long gross, long discount, long freight,
                                           long commission, long adjustments)
        {
            return gross + freight + commission + adjustments - discount;
        }

        /// <summary>Sales net: gross - freight - commission - other - discount.</summary>
        public static long SalesNetRial(long gross, long discount, long freight,
                                        long commission, long other)
        {
            return gross - freight - commission - other - discount;
        }

        private static string Kg(long grams)
        {
            return (grams / 1000m).ToString("0.###", CultureInfo.InvariantCulture) + " kg";
        }
    }
}
