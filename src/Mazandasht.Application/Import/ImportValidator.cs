using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace Mazandasht.Application.Import
{
    public sealed class RowIssue
    {
        public string Field { get; set; } = "";
        public string Message { get; set; } = "";
    }

    public sealed class ParsedRow
    {
        public int SourceRow { get; set; }
        public Dictionary<string, object> Values { get; } =
            new Dictionary<string, object>(StringComparer.Ordinal);
        public List<string> Blanks { get; } = new List<string>();
        public List<RowIssue> Errors { get; } = new List<RowIssue>();
        public List<string> Warnings { get; } = new List<string>();
        public List<string> NumericCodes { get; } = new List<string>();

        public bool Ok => Errors.Count == 0;

        public string GetString(string field)
        {
            object v;
            return Values.TryGetValue(field, out v) ? v as string : null;
        }

        /// <summary>Null means ABSENT — never 0. Golden rule 7.</summary>
        public long? GetLong(string field)
        {
            object v;
            if (!Values.TryGetValue(field, out v) || v == null) return null;
            return Convert.ToInt64(v, CultureInfo.InvariantCulture);
        }

        public double? GetDouble(string field)
        {
            object v;
            if (!Values.TryGetValue(field, out v) || v == null) return null;
            return Convert.ToDouble(v, CultureInfo.InvariantCulture);
        }
    }

    /// <summary>
    /// Stage 4 of the import pipeline: turn cells into typed values.
    /// Port of tools/import_parser.py:validate_row/_convert.
    ///
    /// The rules that are not negotiable:
    ///   * blank -> null, never 0
    ///   * kg -> integer grams, and &gt;3 decimals is an ERROR (silent rounding
    ///     destroys traceability the owner explicitly asked for)
    ///   * no formula in a data cell
    ///   * a required cell that is blank fails the ROW, not the file
    /// </summary>
    public sealed class ImportValidator
    {
        public sealed class RowValidationResult
        {
            public ParsedRow Row { get; set; }
            public bool Ok => Row.Ok;
        }

        public ParsedRow Validate(ImportTemplate template, XlsxSheet sheet, int rowNumber,
                                  IReadOnlyDictionary<string, int> mapping)
        {
            var row = new ParsedRow { SourceRow = rowNumber };

            foreach (var field in template.Fields)
            {
                int col;
                XlsxCell cell = mapping.TryGetValue(field.NameEn, out col)
                    ? sheet.Cell(rowNumber, col)
                    : null;

                if (cell == null || cell.IsBlank)
                {
                    row.Blanks.Add(field.NameEn);
                    row.Values[field.NameEn] = null;   // absent, NOT zero
                    if (field.Required)
                        row.Errors.Add(new RowIssue
                        {
                            Field = field.NameEn,
                            Message = "«" + field.NameFa + "» الزامی است و خالی است"
                        });
                    continue;
                }

                if (cell.HasFormula)
                {
                    row.Errors.Add(new RowIssue
                    {
                        Field = field.NameEn,
                        Message = "«" + field.NameFa + "» فرمول دارد؛ در شیت داده فرمول مجاز نیست"
                    });
                    continue;
                }

                if (field.Kind == FieldKind.Code && cell.IsNumericText)
                {
                    row.NumericCodes.Add(field.NameEn);
                    row.Warnings.Add("«" + field.NameFa +
                        "» به‌صورت عدد ذخیره شده؛ صفرهای ابتدایی ممکن است از دست رفته باشد");
                }

                object value;
                string error;
                if (!TryConvert(field, cell, out value, out error))
                {
                    row.Errors.Add(new RowIssue { Field = field.NameEn, Message = error });
                    continue;
                }

                if (field.Kind == FieldKind.Kind && field.Choices != null &&
                    value != null && !field.Choices.Contains((string)value, StringComparer.Ordinal))
                {
                    row.Errors.Add(new RowIssue
                    {
                        Field = field.NameEn,
                        Message = "مقدار «" + value + "» مجاز نیست؛ یکی از " +
                                  string.Join(", ", field.Choices)
                    });
                    continue;
                }

                var text = value as string;
                if (field.Kind == FieldKind.Code && text != null && text.Length > field.MaxLen)
                {
                    row.Errors.Add(new RowIssue
                    {
                        Field = field.NameEn,
                        Message = "طول مقدار بیش از " + field.MaxLen + " است"
                    });
                    continue;
                }

                row.Values[field.NameEn] = value;
            }
            return row;
        }

        public static bool TryConvert(ImportField field, XlsxCell cell, out object value,
                                      out string error)
        {
            value = null;
            error = null;

            switch (field.Kind)
            {
                case FieldKind.Text:
                case FieldKind.Code:
                case FieldKind.Kind:
                    value = cell.Text.Trim();
                    return true;

                case FieldKind.Shamsi:
                {
                    string normalized;
                    if (!Jalali.TryNormalize(cell.Text, out normalized, out error)) return false;
                    value = normalized;
                    return true;
                }

                case FieldKind.Time:
                {
                    string normalized;
                    if (!Jalali.TryNormalizeTime(cell.Text, out normalized))
                    {
                        error = "ساعت باید HH:mm باشد";
                        return false;
                    }
                    value = normalized;
                    return true;
                }

                case FieldKind.Kg:
                    return TryGrams(cell, out value, out error);

                case FieldKind.Gram:
                case FieldKind.Rial:
                    return TryInteger(cell, false, out value, out error);

                case FieldKind.RialSigned:
                    return TryInteger(cell, true, out value, out error);

                case FieldKind.Count:
                    return TryInteger(cell, false, out value, out error);

                case FieldKind.Percent:
                    return TryPercent(cell, out value, out error);

                case FieldKind.Flag01:
                {
                    var raw = cell.Text.Trim();
                    if (raw.Length == 0) return true;            // blank stays absent
                    if (raw == "1") { value = 1L; return true; }
                    if (raw == "0") { value = 0L; return true; }
                    if (string.Equals(raw, "true", StringComparison.OrdinalIgnoreCase))
                    { value = 1L; return true; }
                    if (string.Equals(raw, "false", StringComparison.OrdinalIgnoreCase))
                    { value = 0L; return true; }
                    error = "مقدار باید ۱ یا ۰ باشد";
                    return false;
                }

                default:
                    value = cell.Text.Trim();
                    return true;
            }
        }

        /// <summary>kg text -> integer grams. More than 3 decimals is refused
        /// rather than silently rounded.</summary>
        public static bool TryGrams(XlsxCell cell, out object value, out string error)
        {
            value = null;
            error = null;
            if (cell.IsBlank) return true;

            var raw = cell.IsNumericText && cell.Number.HasValue
                ? XlsxReader.FormatNumber(cell.Number.Value)
                : cell.Text.Trim().Replace("٬", "").Replace(",", "").Replace("٫", ".");

            decimal kg;
            if (!decimal.TryParse(raw, NumberStyles.Number, CultureInfo.InvariantCulture, out kg))
            {
                error = "وزن عددی نیست: «" + cell.Text + "»";
                return false;
            }
            if (kg < 0)
            {
                error = "وزن منفی است";
                return false;
            }

            var dot = raw.IndexOf('.');
            if (dot >= 0 && raw.Length - dot - 1 > 3)
            {
                error = "وزن بیش از ۳ رقم اعشار دارد: " + raw;
                return false;
            }

            var grams = Math.Round(kg * 1000m, MidpointRounding.AwayFromZero);
            value = (long)grams;
            return true;
        }

        public static bool TryInteger(XlsxCell cell, bool signed, out object value, out string error)
        {
            value = null;
            error = null;
            if (cell.IsBlank) return true;

            var raw = cell.IsNumericText && cell.Number.HasValue
                ? XlsxReader.FormatNumber(cell.Number.Value)
                : cell.Text.Trim().Replace("٬", "").Replace(",", "").Replace("−", "-");

            decimal num;
            if (!decimal.TryParse(raw, NumberStyles.Number, CultureInfo.InvariantCulture, out num))
            {
                error = "عدد نیست: «" + cell.Text + "»";
                return false;
            }
            if (!signed && num < 0)
            {
                error = "مقدار منفی مجاز نیست";
                return false;
            }
            if (num != Math.Truncate(num))
            {
                error = "باید عدد صحیح باشد: " + raw;
                return false;
            }
            value = (long)num;
            return true;
        }

        public static bool TryPercent(XlsxCell cell, out object value, out string error)
        {
            value = null;
            error = null;
            if (cell.IsBlank) return true;

            double pct;
            if (!double.TryParse(cell.Text.Trim(), NumberStyles.Float,
                                 CultureInfo.InvariantCulture, out pct))
            {
                error = "درصد عددی نیست: «" + cell.Text + "»";
                return false;
            }
            if (pct < 0 || pct > 100)
            {
                error = "درصد باید بین ۰ و ۱۰۰ باشد";
                return false;
            }
            value = pct;
            return true;
        }
    }
}
