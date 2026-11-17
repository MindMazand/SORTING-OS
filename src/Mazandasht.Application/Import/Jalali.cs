using System;
using System.Globalization;
using System.Text.RegularExpressions;

namespace Mazandasht.Application.Import
{
    /// <summary>
    /// Jalali (Solar Hijri) date handling for the import layer.
    ///
    /// Why not System.Globalization.PersianCalendar? Because on .NET Framework
    /// 4.8 it is tied to the OS calendar data and its leap-year rule differs
    /// from the 33-year civil cycle the owner's workbooks use for 1343..1472.
    /// A date that shifts by one day silently moves a whole document's period,
    /// so the rule is implemented explicitly and pinned by tests.
    ///
    /// Port of tools/import_parser.py (is_leap_jalali / valid_shamsi) and
    /// tools/import_engine.py (_iso_from_shamsi).
    /// </summary>
    public static class Jalali
    {
        private static readonly int[] DaysInMonth = { 31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29 };

        private static readonly Regex SlashDate =
            new Regex(@"^(\d{4})/(\d{1,2})/(\d{1,2})$", RegexOptions.Compiled);
        private static readonly Regex CompactDate =
            new Regex(@"^\d{8}$", RegexOptions.Compiled);
        private static readonly Regex NumericOnly =
            new Regex(@"^\d+(\.\d+)?$", RegexOptions.Compiled);

        /// <summary>33-year cycle: (year + 12) mod 33 mod 4 == 1.</summary>
        public static bool IsLeap(int year)
        {
            return ((year + 12) % 33) % 4 == 1;
        }

        public static int DaysIn(int year, int month)
        {
            if (month < 1 || month > 12) return 0;
            if (month == 12) return IsLeap(year) ? 30 : 29;
            return DaysInMonth[month - 1];
        }

        /// <summary>
        /// Accepts YYYY/MM/DD or YYYYMMDD only. A bare number is refused on
        /// purpose: an Excel serial (45292) is not a date, and reading it as one
        /// shifts every document by decades.
        /// </summary>
        public static bool TryNormalize(string text, out string normalized, out string error)
        {
            normalized = null;
            error = null;

            if (text == null)
            {
                error = "تاریخ خالی است";
                return false;
            }

            var raw = text.Trim();
            if (CompactDate.IsMatch(raw))
                raw = raw.Substring(0, 4) + "/" + raw.Substring(4, 2) + "/" + raw.Substring(6, 2);

            var m = SlashDate.Match(raw);
            if (!m.Success)
            {
                if (NumericOnly.IsMatch(raw))
                {
                    error = "تاریخ به‌صورت عدد ذخیره شده (Excel serial)؛ باید YYYY/MM/DD باشد";
                    return false;
                }
                error = "قالب تاریخ باید YYYY/MM/DD باشد";
                return false;
            }

            int y, mo, d;
            if (!int.TryParse(m.Groups[1].Value, out y) ||
                !int.TryParse(m.Groups[2].Value, out mo) ||
                !int.TryParse(m.Groups[3].Value, out d))
            {
                error = "قالب تاریخ باید YYYY/MM/DD باشد";
                return false;
            }

            if (y < 1200 || y > 1600)
            {
                error = "سال شمسی خارج از بازه معقول: " + y;
                return false;
            }
            if (mo < 1 || mo > 12)
            {
                error = "ماه نامعتبر: " + mo;
                return false;
            }
            var dim = DaysIn(y, mo);
            if (d < 1 || d > dim)
            {
                error = "روز نامعتبر برای ماه " + mo + ": " + d;
                return false;
            }

            normalized = string.Format(CultureInfo.InvariantCulture, "{0:0000}/{1:00}/{2:00}", y, mo, d);
            return true;
        }

        public static bool IsValid(string text)
        {
            string n, e;
            return TryNormalize(text, out n, out e);
        }

        /// <summary>Jalali -> Gregorian ISO (yyyy-MM-dd). The schema keeps both
        /// columns side by side so ordering and BETWEEN queries work on ISO.</summary>
        public static string ToIso(string shamsi)
        {
            var parts = shamsi.Replace('-', '/').Split('/');
            var y = int.Parse(parts[0], CultureInfo.InvariantCulture);
            var m = int.Parse(parts[1], CultureInfo.InvariantCulture);
            var d = int.Parse(parts[2], CultureInfo.InvariantCulture);

            var jy = y - 979;
            var jm = m - 1;
            var jd = d - 1;

            var jDayNo = 365L * jy + (jy / 33) * 8 + ((jy % 33) + 3) / 4;
            for (var i = 0; i < jm; i++)
                jDayNo += i < 6 ? 31 : 30;
            jDayNo += jd;

            var gDayNo = jDayNo + 79;
            var gy = 1600 + 400 * (int)(gDayNo / 146097);
            gDayNo %= 146097;

            var leap = true;
            if (gDayNo >= 36525)
            {
                gDayNo -= 1;
                gy += 100 * (int)(gDayNo / 36524);
                gDayNo %= 36524;
                if (gDayNo >= 365) gDayNo += 1;
                else leap = false;
            }
            gy += 4 * (int)(gDayNo / 1461);
            gDayNo %= 1461;
            if (gDayNo >= 366)
            {
                leap = false;
                gDayNo -= 1;
                gy += (int)(gDayNo / 365);
                gDayNo %= 365;
            }

            var monthDays = new[] { 31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
            var gm = 0;
            while (gm < 12 && gDayNo >= monthDays[gm])
            {
                gDayNo -= monthDays[gm];
                gm++;
            }

            return string.Format(CultureInfo.InvariantCulture, "{0:0000}-{1:00}-{2:00}",
                                 gy, gm + 1, gDayNo + 1);
        }

        /// <summary>HH:mm or HH:mm:ss -> HH:mm.</summary>
        public static bool TryNormalizeTime(string text, out string normalized)
        {
            normalized = null;
            if (text == null) return false;
            var m = Regex.Match(text.Trim(), @"^(\d{1,2}):(\d{2})(?::(\d{2}))?$");
            if (!m.Success) return false;
            var h = int.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture);
            var mi = int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture);
            if (h > 23 || mi > 59) return false;
            normalized = string.Format(CultureInfo.InvariantCulture, "{0:00}:{1:00}", h, mi);
            return true;
        }
    }
}
