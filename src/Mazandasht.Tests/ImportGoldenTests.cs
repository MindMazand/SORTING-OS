using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Mazandasht.Application.Import;
using Xunit;

namespace Mazandasht.Tests
{
    /// <summary>
    /// Golden-vector tests: the C# port must reproduce exactly the values the
    /// Python reference produced and tools/test_import.py already proved
    /// (34/34). tests/golden/import_vectors.json is the contract.
    ///
    /// Why this file matters more than the others: the Python harness cannot
    /// run on the target machine and this suite cannot run here. The vectors
    /// are the only thing both sides can be held against, so a failure here
    /// means the port drifted, not that the test is wrong.
    ///
    /// STATUS: written, NOT RUN. No .NET toolchain in the build sandbox.
    /// Running these on Windows 8.1+ x64 is what turns IMPLEMENTED into TESTED.
    /// </summary>
    public class ImportGoldenTests
    {
        private static Dictionary<string, object> _vectors;

        private static Dictionary<string, object> Vectors()
        {
            if (_vectors != null) return _vectors;

            // Prefer the copy next to the test binary (csproj CopyToOutput),
            // then walk up to the repository root. Both paths are tried so the
            // test behaves the same in the IDE and on CI.
            string path = null;
            var beside = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,
                                      "tests", "golden", "import_vectors.json");
            if (File.Exists(beside)) path = beside;

            if (path == null)
            {
                var dir = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
                while (dir != null && !File.Exists(
                           Path.Combine(dir.FullName, "tests", "golden", "import_vectors.json")))
                    dir = dir.Parent;
                if (dir != null)
                    path = Path.Combine(dir.FullName, "tests", "golden", "import_vectors.json");
            }
            if (path == null)
                throw new FileNotFoundException("tests/golden/import_vectors.json پیدا نشد");
            _vectors = MiniJson.ParseObject(File.ReadAllText(path));
            return _vectors;
        }

        // -- Jalali ---------------------------------------------------------
        [Fact]
        public void Jalali_To_Iso_Matches_Every_Vector()
        {
            var table = (Dictionary<string, object>)Vectors()["jalali_to_iso"];
            Assert.NotEmpty(table);
            foreach (var pair in table)
                Assert.Equal((string)pair.Value, Jalali.ToIso(pair.Key));
        }

        [Fact]
        public void Jalali_Leap_Matches_Every_Vector()
        {
            var table = (Dictionary<string, object>)Vectors()["jalali_leap"];
            Assert.NotEmpty(table);
            foreach (var pair in table)
                Assert.Equal((bool)pair.Value, Jalali.IsLeap(int.Parse(pair.Key)));
        }

        [Fact]
        public void Jalali_Validity_Matches_Every_Vector()
        {
            var list = (List<object>)Vectors()["jalali_valid"];
            Assert.NotEmpty(list);
            foreach (var item in list.Cast<Dictionary<string, object>>())
            {
                var input = (string)item["input"];
                var valid = (bool)item["valid"];
                string normalized, error;
                var got = Jalali.TryNormalize(input, out normalized, out error);

                Assert.Equal(valid, got);
                if (valid)
                {
                    Assert.Equal((string)item["normalized"], normalized);
                }
                else if (item.ContainsKey("reason_contains"))
                {
                    Assert.Contains((string)item["reason_contains"], error);
                }
            }
        }

        // -- weights --------------------------------------------------------
        [Fact]
        public void Kg_To_Grams_Matches_Every_Vector()
        {
            var list = (List<object>)Vectors()["kg_to_grams"];
            Assert.NotEmpty(list);
            foreach (var item in list.Cast<Dictionary<string, object>>())
            {
                var cell = new XlsxCell { Kind = "text", Text = (string)item["input"] };
                object grams;
                string error;
                Assert.True(ImportValidator.TryGrams(cell, out grams, out error), error);
                Assert.Equal(Convert.ToInt64(item["grams"]), Convert.ToInt64(grams));
            }
        }

        [Fact]
        public void Kg_Rejections_Match_Every_Vector()
        {
            var list = (List<object>)Vectors()["kg_rejected"];
            Assert.NotEmpty(list);
            foreach (var item in list.Cast<Dictionary<string, object>>())
            {
                var cell = new XlsxCell { Kind = "text", Text = (string)item["input"] };
                object grams;
                string error;
                Assert.False(ImportValidator.TryGrams(cell, out grams, out error),
                             "expected rejection for " + item["input"]);
                Assert.Contains((string)item["reason_contains"], error);
            }
        }

        // -- money ----------------------------------------------------------
        [Fact]
        public void Gross_Rial_Matches_Every_Vector()
        {
            var list = (List<object>)Vectors()["rial_gross"];
            Assert.NotEmpty(list);
            foreach (var item in list.Cast<Dictionary<string, object>>())
            {
                var grams = Convert.ToInt64(item["grams"]);
                var rate = Convert.ToInt64(item["rate"]);
                Assert.Equal(Convert.ToInt64(item["gross_rial"]),
                             ImportEngine.GrossRial(grams, rate));
            }
        }

        [Fact]
        public void Net_Invoice_Rial_Matches_Every_Vector()
        {
            var list = (List<object>)Vectors()["net_invoice"];
            Assert.NotEmpty(list);
            foreach (var item in list.Cast<Dictionary<string, object>>())
            {
                var gross = Convert.ToInt64(item["gross"]);
                var discount = Convert.ToInt64(item["discount"]);
                var freight = Convert.ToInt64(item["freight"]);
                var commission = Convert.ToInt64(item["commission"]);
                var expected = Convert.ToInt64(item["net_rial"]);

                long actual;
                if (item.ContainsKey("adjustments"))
                {
                    actual = ImportEngine.PurchaseNetRial(
                        gross, discount, freight, commission,
                        Convert.ToInt64(item["adjustments"]));
                }
                else
                {
                    actual = ImportEngine.SalesNetRial(
                        gross, discount, freight, commission,
                        Convert.ToInt64(item["other"]));
                }
                Assert.Equal(expected, actual);
            }
        }

        // -- percentages ----------------------------------------------------
        [Fact]
        public void Percent_Accepts_And_Rejects_As_Recorded()
        {
            foreach (var item in ((List<object>)Vectors()["percent"])
                     .Cast<Dictionary<string, object>>())
            {
                var cell = new XlsxCell { Kind = "text", Text = (string)item["input"] };
                object value;
                string error;
                Assert.True(ImportValidator.TryPercent(cell, out value, out error), error);
                Assert.Equal(Convert.ToDouble(item["value"]), Convert.ToDouble(value), 6);
            }

            foreach (var item in ((List<object>)Vectors()["percent_rejected"])
                     .Cast<Dictionary<string, object>>())
            {
                var cell = new XlsxCell { Kind = "text", Text = (string)item["input"] };
                object value;
                string error;
                Assert.False(ImportValidator.TryPercent(cell, out value, out error));
                Assert.Contains((string)item["reason_contains"], error);
            }
        }

        // -- classification -------------------------------------------------
        [Fact]
        public void Party_Nature_From_Code_Matches_Every_Vector()
        {
            var table = (Dictionary<string, object>)Vectors()["party_nature_from_code"];
            Assert.NotEmpty(table);
            foreach (var pair in table)
                Assert.Equal((string)pair.Value, ImportWriter.NatureFromCode(pair.Key));
        }

        // -- net weight (DEC-NEW-008) ---------------------------------------
        [Fact]
        public void Net_Weight_Formula_Matches_Every_Vector()
        {
            var block = (Dictionary<string, object>)Vectors()["net_weight_check"];
            var cases = (List<object>)block["cases"];
            Assert.NotEmpty(cases);

            foreach (var item in cases.Cast<Dictionary<string, object>>())
            {
                var scale = Convert.ToInt64(item["scale_grams"]);
                var baskets = Convert.ToInt64(item["basket_count"]);
                var p01 = Convert.ToInt64(item["p01_grams"]);
                var p02 = Convert.ToDouble(item["p02_percent"]);

                // DEC-NEW-008, purchase class:
                //   tare = baskets * P01
                //   net  = (scale - tare) * (1 - P02/100)
                var tare = baskets * p01;
                Assert.Equal(Convert.ToInt64(item["expected_tare_grams"]), tare);

                var net = (long)Math.Round((scale - tare) * (1.0 - p02 / 100.0),
                                           MidpointRounding.AwayFromZero);
                Assert.Equal(Convert.ToInt64(item["expected_net_grams"]), net);
            }
        }

        // A deliberately tiny JSON reader. Pulling a NuGet JSON package into a
        // test project is acceptable, but the application projects have zero
        // third-party dependencies by design and this keeps the test project
        // consistent with that rule.
        private static class MiniJson
        {
            public static Dictionary<string, object> ParseObject(string text)
            {
                var i = 0;
                var value = ParseValue(text, ref i) as Dictionary<string, object>;
                if (value == null) throw new FormatException("root is not an object");
                return value;
            }

            private static void SkipWhitespace(string s, ref int i)
            {
                while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
            }

            private static object ParseValue(string s, ref int i)
            {
                SkipWhitespace(s, ref i);
                if (i >= s.Length) throw new FormatException("unexpected end");
                switch (s[i])
                {
                    case '{': return ParseObj(s, ref i);
                    case '[': return ParseArr(s, ref i);
                    case '"': return ParseString(s, ref i);
                    case 't': i += 4; return true;
                    case 'f': i += 5; return false;
                    case 'n': i += 4; return null;
                    default: return ParseNumber(s, ref i);
                }
            }

            private static Dictionary<string, object> ParseObj(string s, ref int i)
            {
                var result = new Dictionary<string, object>(StringComparer.Ordinal);
                i++;                                   // {
                SkipWhitespace(s, ref i);
                if (i < s.Length && s[i] == '}') { i++; return result; }
                while (true)
                {
                    SkipWhitespace(s, ref i);
                    var key = ParseString(s, ref i);
                    SkipWhitespace(s, ref i);
                    if (s[i] != ':') throw new FormatException("expected ':'");
                    i++;
                    result[key] = ParseValue(s, ref i);
                    SkipWhitespace(s, ref i);
                    if (s[i] == ',') { i++; continue; }
                    if (s[i] == '}') { i++; return result; }
                    throw new FormatException("expected ',' or '}'");
                }
            }

            private static List<object> ParseArr(string s, ref int i)
            {
                var result = new List<object>();
                i++;                                   // [
                SkipWhitespace(s, ref i);
                if (i < s.Length && s[i] == ']') { i++; return result; }
                while (true)
                {
                    result.Add(ParseValue(s, ref i));
                    SkipWhitespace(s, ref i);
                    if (s[i] == ',') { i++; continue; }
                    if (s[i] == ']') { i++; return result; }
                    throw new FormatException("expected ',' or ']'");
                }
            }

            private static string ParseString(string s, ref int i)
            {
                if (s[i] != '"') throw new FormatException("expected string");
                i++;
                var sb = new System.Text.StringBuilder();
                while (i < s.Length)
                {
                    var c = s[i];
                    if (c == '"') { i++; return sb.ToString(); }
                    if (c == '\\')
                    {
                        i++;
                        switch (s[i])
                        {
                            case 'n': sb.Append('\n'); break;
                            case 't': sb.Append('\t'); break;
                            case 'r': sb.Append('\r'); break;
                            case '"': sb.Append('"'); break;
                            case '\\': sb.Append('\\'); break;
                            case '/': sb.Append('/'); break;
                            case 'u':
                                sb.Append((char)Convert.ToInt32(s.Substring(i + 1, 4), 16));
                                i += 4;
                                break;
                            default: sb.Append(s[i]); break;
                        }
                        i++;
                        continue;
                    }
                    sb.Append(c);
                    i++;
                }
                throw new FormatException("unterminated string");
            }

            private static object ParseNumber(string s, ref int i)
            {
                var start = i;
                while (i < s.Length && (char.IsDigit(s[i]) || s[i] == '-' || s[i] == '+' ||
                                        s[i] == '.' || s[i] == 'e' || s[i] == 'E')) i++;
                var raw = s.Substring(start, i - start);
                if (raw.IndexOf('.') >= 0 || raw.IndexOf('e') >= 0 || raw.IndexOf('E') >= 0)
                    return double.Parse(raw, CultureInfo.InvariantCulture);
                return long.Parse(raw, CultureInfo.InvariantCulture);
            }
        }
    }
}
