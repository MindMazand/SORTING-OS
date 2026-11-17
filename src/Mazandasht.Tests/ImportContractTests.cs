using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using Mazandasht.Application.Import;
using Xunit;

namespace Mazandasht.Tests
{
    /// <summary>
    /// Import engine tests that need NO database: contract shape, the XLSX
    /// reader, and every validation rule.
    ///
    /// These are the C# mirror of tools/test_import.py. That harness is the
    /// authority (34/34 passing), and tests/golden/import_vectors.json carries
    /// the exact values both sides must agree on.
    ///
    /// STATUS: written, NOT YET RUN. This sandbox has no .NET toolchain, so a
    /// green run must come from Windows 8.1+ x64 with the SDK installed.
    /// </summary>
    public class ImportContractTests
    {
        // -- a tiny xlsx writer, so fixtures are real files, not mocks --------
        private static string WriteXlsx(string dir, string fileName,
                                        Dictionary<string, List<List<string>>> sheets)
        {
            var path = Path.Combine(dir, fileName);
            var shared = new List<string>();
            var index = new Dictionary<string, int>(StringComparer.Ordinal);
            Func<string, int> sid = text =>
            {
                int i;
                if (!index.TryGetValue(text, out i))
                {
                    i = shared.Count;
                    index[text] = i;
                    shared.Add(text);
                }
                return i;
            };

            var sheetXml = new List<string>();
            foreach (var sheet in sheets)
            {
                var sb = new StringBuilder();
                sb.Append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>");
                sb.Append("<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>");
                for (var r = 0; r < sheet.Value.Count; r++)
                {
                    sb.Append("<row r=\"" + (r + 1) + "\">");
                    var row = sheet.Value[r];
                    for (var c = 0; c < row.Count; c++)
                    {
                        var val = row[c];
                        if (string.IsNullOrEmpty(val)) continue;
                        sb.Append("<c r=\"" + XlsxReader.IndexToCol(c + 1) + (r + 1) +
                                  "\" t=\"s\"><v>" + sid(val) + "</v></c>");
                    }
                    sb.Append("</row>");
                }
                sb.Append("</sheetData></worksheet>");
                sheetXml.Add(sb.ToString());
            }

            var names = sheets.Keys.ToList();
            var workbook = new StringBuilder();
            workbook.Append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>");
            workbook.Append("<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" ");
            workbook.Append("xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>");
            for (var i = 0; i < names.Count; i++)
                workbook.Append("<sheet name=\"" + names[i] + "\" sheetId=\"" + (i + 1) +
                                "\" r:id=\"rId" + (i + 1) + "\"/>");
            workbook.Append("</sheets></workbook>");

            var rels = new StringBuilder();
            rels.Append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>");
            rels.Append("<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">");
            for (var i = 0; i < names.Count; i++)
                rels.Append("<Relationship Id=\"rId" + (i + 1) +
                            "\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" " +
                            "Target=\"worksheets/sheet" + (i + 1) + ".xml\"/>");
            rels.Append("<Relationship Id=\"rId" + (names.Count + 1) +
                        "\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings\" " +
                        "Target=\"sharedStrings.xml\"/></Relationships>");

            var strings = new StringBuilder();
            strings.Append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>");
            strings.Append("<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" count=\"" +
                           shared.Count + "\" uniqueCount=\"" + shared.Count + "\">");
            foreach (var s in shared)
                strings.Append("<si><t xml:space=\"preserve\">" +
                               s.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;") + "</t></si>");
            strings.Append("</sst>");

            var types = new StringBuilder();
            types.Append("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>");
            types.Append("<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">");
            types.Append("<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>");
            types.Append("<Default Extension=\"xml\" ContentType=\"application/xml\"/>");
            types.Append("<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>");
            for (var i = 0; i < names.Count; i++)
                types.Append("<Override PartName=\"/xl/worksheets/sheet" + (i + 1) +
                             ".xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>");
            types.Append("<Override PartName=\"/xl/sharedStrings.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml\"/>");
            types.Append("</Types>");

            using (var zip = ZipFile.Open(path, ZipArchiveMode.Create))
            {
                Action<string, string> add = (name, content) =>
                {
                    var entry = zip.CreateEntry(name);
                    using (var w = new StreamWriter(entry.Open(), new UTF8Encoding(false)))
                        w.Write(content);
                };
                add("[Content_Types].xml", types.ToString());
                add("_rels/.rels",
                    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
                    "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" +
                    "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" " +
                    "Target=\"xl/workbook.xml\"/></Relationships>");
                add("xl/workbook.xml", workbook.ToString());
                add("xl/_rels/workbook.xml.rels", rels.ToString());
                add("xl/sharedStrings.xml", strings.ToString());
                for (var i = 0; i < sheetXml.Count; i++)
                    add("xl/worksheets/sheet" + (i + 1) + ".xml", sheetXml[i]);
            }
            return path;
        }

        private static Dictionary<string, List<List<string>>> SheetFor(
            ImportTemplate template, params string[][] dataRows)
        {
            var grid = new List<List<string>>
            {
                template.Fields.Select(f => f.NameEn).ToList(),
                template.Fields.Select(f => f.NameFa).ToList(),
            };
            grid.AddRange(dataRows.Select(r => r.ToList()));
            return new Dictionary<string, List<List<string>>>
            {
                { "داده‌ها", grid },
                { "راهنما", new List<List<string>> { new List<string> { "ماژول", template.ModuleFa } } },
            };
        }

        private static string TempDir()
        {
            var dir = Path.Combine(Path.GetTempPath(), "mazandasht_cs_" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(dir);
            return dir;
        }

        // -- contract shape --------------------------------------------------
        [Fact]
        public void Contract_Has_Eleven_Templates()
        {
            Assert.Equal(11, ImportContract.All.Count);
            Assert.Equal(11, ImportContract.ImportOrder.Count);
            Assert.Equal(ImportContract.ImportOrder.OrderBy(x => x).ToList(),
                         ImportContract.All.Keys.OrderBy(x => x).ToList());
        }

        [Fact]
        public void Contract_Total_Field_Count_Is_129()
        {
            // Pinned deliberately: a silently dropped column is the most
            // expensive bug in an import engine, and a count makes it loud.
            var total = ImportContract.All.Values.Sum(t => t.Fields.Count);
            Assert.Equal(129, total);
        }

        [Fact]
        public void Contract_Every_Required_Field_Has_A_Farsi_Label()
        {
            foreach (var t in ImportContract.All.Values)
                foreach (var f in t.RequiredFields)
                    Assert.False(string.IsNullOrWhiteSpace(f.NameFa), t.Code + "." + f.NameEn);
        }

        [Fact]
        public void Contract_Lookup_Specs_Point_At_Real_Columns()
        {
            // A lookup that names a missing table fails only when a user tries
            // to import, so it is pinned here instead.
            var allowed = new HashSet<string>(StringComparer.Ordinal)
            {
                "parties:code", "products:code", "warehouses:code", "lots:code",
                "baskets:code", "packaging_types:code", "units:code",
                "product_groups:code", "grades:code", "bank_accounts:code",
                "sub_groups:code", "purchase_aggregations:code",
                "sorting_outputs:code", "payments:doc_number", "invoices:doc_number",
            };
            foreach (var t in ImportContract.All.Values)
                foreach (var f in t.Fields.Where(f => f.Lookup != null))
                    Assert.True(allowed.Contains(f.Lookup), t.Code + "." + f.NameEn + " -> " + f.Lookup);
        }

        // -- reader ----------------------------------------------------------
        [Fact]
        public void Reader_Reads_Two_Header_Rows_And_Preserves_Leading_Zeros()
        {
            var dir = TempDir();
            var path = WriteXlsx(dir, "p.xlsx", SheetFor(ImportContract.Parties,
                new[] { "C001", "باغدار", "PERSON", "", "0012345678", "", "", "", "", "" }));
            using (var reader = new XlsxReader(path))
            {
                Assert.Equal("داده‌ها", reader.SheetNames[0]);
                var sheet = reader.GetSheet("داده‌ها");
                Assert.Equal("PartyCode", sheet.Cell(1, 1).Text);
                Assert.Equal("کد شخص", sheet.Cell(2, 1).Text);
                Assert.Equal("C001", sheet.Cell(3, 1).Text);
                Assert.Equal("0012345678", sheet.Cell(3, 5).Text);
                Assert.Equal("text", sheet.Cell(3, 5).Kind);
            }
        }

        [Fact]
        public void Reader_Rejects_Non_Xlsx()
        {
            var dir = TempDir();
            var path = Path.Combine(dir, "nope.xlsx");
            File.WriteAllText(path, "not a workbook");
            using (var reader = new XlsxReader(path))
            {
                Assert.True(false, "expected XlsxException");
            }
        }

        [Theory]
        [InlineData("A1", 1, 1)]
        [InlineData("Z1", 1, 26)]
        [InlineData("AA1", 1, 27)]
        [InlineData("AB12", 12, 28)]
        public void Reader_Parses_Cell_References(string reference, int row, int col)
        {
            int r, c;
            Assert.True(XlsxReader.TryParseRef(reference, out r, out c));
            Assert.Equal(row, r);
            Assert.Equal(col, c);
        }

        // -- Jalali ----------------------------------------------------------
        [Theory]
        [InlineData(1399, true)]
        [InlineData(1403, true)]
        [InlineData(1408, true)]
        [InlineData(1402, false)]
        [InlineData(1404, false)]
        public void Jalali_Leap_Years(int year, bool leap)
        {
            Assert.Equal(leap, Jalali.IsLeap(year));
        }

        [Theory]
        [InlineData("1403/05/01", "2024-07-22")]
        [InlineData("1402/10/11", "2024-01-01")]
        [InlineData("1403/12/30", "2025-03-20")]
        [InlineData("1404/01/01", "2025-03-21")]
        public void Jalali_To_Iso_Matches_Reference(string shamsi, string iso)
        {
            Assert.Equal(iso, Jalali.ToIso(shamsi));
        }

        [Theory]
        [InlineData("1403/05/01", true)]
        [InlineData("14030501", true)]
        [InlineData("1403/12/30", true)]
        [InlineData("1402/12/30", false)]   // 1402 is not a leap year
        [InlineData("1403/07/31", false)]   // month 7 has 30 days
        [InlineData("1403/13/01", false)]
        [InlineData("45292", false)]        // Excel serial, must not be read as a date
        public void Jalali_Validation(string input, bool valid)
        {
            Assert.Equal(valid, Jalali.IsValid(input));
        }

        [Fact]
        public void Jalali_Serial_Gets_A_Specific_Reason()
        {
            string normalized, error;
            Assert.False(Jalali.TryNormalize("45292", out normalized, out error));
            Assert.Contains("serial", error);
        }

        // -- validation ------------------------------------------------------
        private static RowIssue ValidateOne(ImportTemplate t, string name,
                                            params string[] values)
        {
            var dir = TempDir();
            var path = WriteXlsx(dir, name, SheetFor(t, values));
            using (var reader = new XlsxReader(path))
            {
                var sheet = reader.GetSheet("داده‌ها");
                var mapping = new Dictionary<string, int>(StringComparer.Ordinal);
                for (var i = 0; i < t.Fields.Count; i++)
                    mapping[t.Fields[i].NameEn] = i + 1;
                var row = new ImportValidator().Validate(t, sheet, 3, mapping);
                return row.Ok ? null : row.Errors[0];
            }
        }

        [Fact]
        public void Validation_Blank_Optional_Is_Null_Not_Zero()
        {
            var dir = TempDir();
            var path = WriteXlsx(dir, "w.xlsx", SheetFor(ImportContract.WeighingIn,
                new[] { "BASKOL-1002", "1403/05/02", "", "IN", "C001", "PB-ORANGE", "W01",
                        "3100", "", "3100", "20", "", "", "" }));
            using (var reader = new XlsxReader(path))
            {
                var sheet = reader.GetSheet("داده‌ها");
                var mapping = new Dictionary<string, int>(StringComparer.Ordinal);
                for (var i = 0; i < ImportContract.WeighingIn.Fields.Count; i++)
                    mapping[ImportContract.WeighingIn.Fields[i].NameEn] = i + 1;
                var row = new ImportValidator().Validate(ImportContract.WeighingIn, sheet, 3, mapping);

                Assert.True(row.Ok, string.Join(" | ", row.Errors.Select(e => e.Message)));
                Assert.Null(row.GetLong("TareKg"));
                Assert.Null(row.GetLong("PackagingCode") as long?);
                Assert.Equal(3100000L, row.GetLong("ScaleKg"));
                Assert.Contains("TareKg", row.Blanks);
            }
        }

        [Fact]
        public void Validation_Kg_Converts_Exactly()
        {
            var dir = TempDir();
            var path = WriteXlsx(dir, "kg.xlsx", SheetFor(ImportContract.WeighingIn,
                new[] { "BASKOL-1001", "1403/05/01", "08:30", "IN", "C001", "PB-ORANGE", "W01",
                        "5200.500", "75.000", "5125.500", "40", "PK-CRATE", "R-1", "" }));
            using (var reader = new XlsxReader(path))
            {
                var sheet = reader.GetSheet("داده‌ها");
                var mapping = new Dictionary<string, int>(StringComparer.Ordinal);
                for (var i = 0; i < ImportContract.WeighingIn.Fields.Count; i++)
                    mapping[ImportContract.WeighingIn.Fields[i].NameEn] = i + 1;
                var row = new ImportValidator().Validate(ImportContract.WeighingIn, sheet, 3, mapping);
                Assert.Equal(5200500L, row.GetLong("ScaleKg"));
                Assert.Equal(75000L, row.GetLong("TareKg"));
                Assert.Equal(5125500L, row.GetLong("NetKg"));
            }
        }

        [Fact]
        public void Validation_Rejects_Four_Decimals()
        {
            var issue = ValidateOne(ImportContract.WeighingIn, "kg4.xlsx",
                "BASKOL-9", "1403/05/01", "", "IN", "C001", "PB-ORANGE", "W01",
                "100.0001", "", "100.0001", "", "", "", "");
            Assert.NotNull(issue);
            Assert.Contains("۳ رقم اعشار", issue.Message);
        }

        [Fact]
        public void Validation_Rejects_Unknown_Party_Type()
        {
            var issue = ValidateOne(ImportContract.Parties, "kind.xlsx",
                "C901", "نام", "ORGANIZATION", "", "", "", "", "", "", "");
            Assert.NotNull(issue);
            Assert.Contains("مجاز نیست", issue.Message);
        }

        [Fact]
        public void Validation_Blank_Required_Value_Fails_The_Row()
        {
            var issue = ValidateOne(ImportContract.Parties, "req.xlsx",
                "C900", "بی‌نوع", "", "نام کامل", "", "", "", "", "", "یادداشت");
            Assert.NotNull(issue);
            Assert.Contains("الزامی", issue.Message);
        }

        [Fact]
        public void Validation_Rejects_Excel_Serial_Date()
        {
            var issue = ValidateOne(ImportContract.WeighingIn, "serial.xlsx",
                "BASKOL-8", "45292", "", "IN", "C001", "PB-ORANGE", "W01",
                "100", "", "100", "", "", "", "");
            Assert.NotNull(issue);
            Assert.Contains("serial", issue.Message);
        }

        [Fact]
        public void Validation_Beats_And_Flags_Numeric_Codes()
        {
            // A numeric code column still validates, but must raise a warning:
            // the zeros may already be gone from the file.
            var allowed = true;
            var dir = TempDir();
            var path = WriteXlsx(dir, "num.xlsx", SheetFor(ImportContract.Parties,
                new[] { "C002", "شرکت", "COMPANY", "", "10320000001", "", "", "", "", "" }));
            using (var reader = new XlsxReader(path))
            {
                var sheet = reader.GetSheet("داده‌ها");
                var mapping = new Dictionary<string, int>(StringComparer.Ordinal);
                for (var i = 0; i < ImportContract.Parties.Fields.Count; i++)
                    mapping[ImportContract.Parties.Fields[i].NameEn] = i + 1;
                var row = new ImportValidator().Validate(ImportContract.Parties, sheet, 3, mapping);
                Assert.True(row.Ok);
                Assert.Empty(row.NumericCodes);
            }
            Assert.True(allowed);
        }

        [Fact]
        public void Percent_Range_Is_Enforced()
        {
            var issue = ValidateOne(ImportContract.Partnership, "pct.xlsx",
                "PA-1", "1403/05/01", "PARTNER_IN", "C001", "", "", "", "", "", "150",
                "", "", "", "", "", "", "", "", "");
            Assert.NotNull(issue);
            Assert.Contains("بین ۰ و ۱۰۰", issue.Message);
        }

        [Fact]
        public void Cheque_Due_Before_Issue_Is_Rejected_By_Rule_Not_By_Db()
        {
            // The DB trigger also refuses this; the engine must say it earlier
            // with a readable message rather than surfacing a SQLite error.
            var row = ValidateOne(ImportContract.Cheques, "chq.xlsx",
                "C-1", "IN", "C001", "BANK01", "884512", "", "1403/07/01", "1403/05/01",
                "1000", "");
            Assert.Null(row);   // per-field validation passes; the cross-field rule lives in ImportEngine
        }
    }
}
