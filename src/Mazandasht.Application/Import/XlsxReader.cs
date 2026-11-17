using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace Mazandasht.Application.Import
{
    /// <summary>One grid cell. <see cref="Text"/> is what the user sees;
    /// <see cref="IsNumericText"/> is true when a code-like value arrived as a
    /// real number.</summary>
    public sealed class XlsxCell
    {
        public int Row { get; set; }
        public int Col { get; set; }
        public string Ref { get; set; } = "";
        public string Text { get; set; } = "";
        public double? Number { get; set; }
        public string Kind { get; set; } = "empty";   // empty|text|number|bool|error
        public bool HasFormula { get; set; }

        public bool IsBlank => Kind == "empty" || string.IsNullOrWhiteSpace(Text);
        public bool IsNumericText => Kind == "number";
    }

    public sealed class XlsxSheet
    {
        public string Name { get; set; } = "";
        public Dictionary<int, Dictionary<int, XlsxCell>> Rows { get; } =
            new Dictionary<int, Dictionary<int, XlsxCell>>();
        public int MaxRow { get; set; }
        public int MaxCol { get; set; }
        /// <summary>Merged ranges: (top,left,bottom,right). The owner's golden
        /// rule 8 forbids them inside data, so the importer must SEE them.</summary>
        public List<Tuple<int, int, int, int>> Merges { get; } =
            new List<Tuple<int, int, int, int>>();

        public XlsxCell Cell(int row, int col)
        {
            Dictionary<int, XlsxCell> line;
            if (Rows.TryGetValue(row, out line))
            {
                XlsxCell c;
                if (line.TryGetValue(col, out c)) return c;
            }
            return new XlsxCell { Row = row, Col = col };
        }
    }

    public sealed class XlsxException : Exception
    {
        public XlsxException(string message) : base(message) { }
    }

    /// <summary>
    /// Reads .xlsx with System.IO.Compression only — no third-party package.
    /// The product must install on an offline Windows 8.1 x64 machine, and
    /// every extra NuGet dependency is one more thing that can fail there.
    ///
    /// This is a port of tools/xlsx_io.py. Behaviour that matters and is
    /// deliberately identical:
    ///   * shared strings, inline strings, cached formula results
    ///   * <see cref="XlsxCell.IsNumericText"/> stays true for a code stored as
    ///     a number, because the leading zeros are already gone from the file
    ///   * merged-cell ranges are collected, not silently flattened
    /// </summary>
    public sealed class XlsxReader : IDisposable
    {
        private static readonly XNamespace Main =
            "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
        private static readonly XNamespace Rel =
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
        private static readonly XNamespace PkgRel =
            "http://schemas.openxmlformats.org/package/2006/relationships";

        private readonly ZipArchive _zip;
        private readonly List<string> _shared = new List<string>();
        private readonly Dictionary<string, string> _sheetPaths =
            new Dictionary<string, string>(StringComparer.Ordinal);
        private readonly Dictionary<string, XlsxSheet> _cache =
            new Dictionary<string, XlsxSheet>(StringComparer.Ordinal);

        public IReadOnlyList<string> SheetNames { get; private set; } =
            new List<string>();

        public XlsxReader(string path)
        {
            try
            {
                _zip = ZipFile.OpenRead(path);
            }
            catch (Exception e) when (e is InvalidDataException || e is FileNotFoundException)
            {
                throw new XlsxException("فایل قابل خواندن نیست (xlsx معتبر نیست): " + e.Message);
            }

            if (_zip.GetEntry("xl/workbook.xml") == null)
            {
                Dispose();
                throw new XlsxException("ساختار xlsx ناقص است: xl/workbook.xml پیدا نشد.");
            }
            ReadSharedStrings();
            ReadWorkbook();
        }

        // -- internals ------------------------------------------------------
        private string ReadEntry(string name)
        {
            var entry = _zip.GetEntry(name);
            if (entry == null) return null;
            using (var stream = entry.Open())
            using (var reader = new StreamReader(stream, Encoding.UTF8))
                return reader.ReadToEnd();
        }

        private void ReadSharedStrings()
        {
            var xml = ReadEntry("xl/sharedStrings.xml");
            if (xml == null) return;
            var doc = XDocument.Parse(xml);
            foreach (var si in doc.Root.Elements(Main + "si"))
                _shared.Add(CollectText(si));
        }

        /// <summary>All &lt;t&gt; runs except phonetic (&lt;rPh&gt;) ones, which
        /// would otherwise duplicate the visible string.</summary>
        private static string CollectText(XElement node)
        {
            var sb = new StringBuilder();
            foreach (var child in node.Elements())
            {
                if (child.Name == Main + "t") sb.Append(child.Value);
                else if (child.Name == Main + "r")
                    foreach (var t in child.Descendants(Main + "t")) sb.Append(t.Value);
            }
            // shared string may be <si><t>text</t></si> directly
            if (sb.Length == 0 && node.Element(Main + "t") != null)
                sb.Append(node.Element(Main + "t").Value);
            return sb.ToString();
        }

        private void ReadWorkbook()
        {
            var rels = new Dictionary<string, string>(StringComparer.Ordinal);
            var relsXml = ReadEntry("xl/_rels/workbook.xml.rels");
            if (relsXml != null)
            {
                var rdoc = XDocument.Parse(relsXml);
                foreach (var r in rdoc.Root.Elements(PkgRel + "Relationship"))
                {
                    var target = (string)r.Attribute("Target") ?? "";
                    if (target.StartsWith("/", StringComparison.Ordinal)) target = target.Substring(1);
                    else if (!target.StartsWith("xl/", StringComparison.Ordinal)) target = "xl/" + target;
                    rels[(string)r.Attribute("Id")] = target;
                }
            }

            var doc = XDocument.Parse(ReadEntry("xl/workbook.xml"));
            var sheets = doc.Root.Element(Main + "sheets");
            if (sheets == null) throw new XlsxException("هیچ شیتی در فایل نیست.");

            var names = new List<string>();
            int i = 0;
            foreach (var sh in sheets.Elements(Main + "sheet"))
            {
                i++;
                var name = (string)sh.Attribute("name") ?? ("Sheet" + i);
                var rid = (string)sh.Attribute(Rel + "id");
                string path;
                if (rid == null || !rels.TryGetValue(rid, out path))
                    path = "xl/worksheets/sheet" + i + ".xml";
                names.Add(name);
                _sheetPaths[name] = path;
            }
            SheetNames = names;
        }

        public XlsxSheet GetSheet(string name)
        {
            XlsxSheet cached;
            if (_cache.TryGetValue(name, out cached)) return cached;

            string path;
            if (!_sheetPaths.TryGetValue(name, out path))
                throw new XlsxException("شیت «" + name + "» در فایل وجود ندارد.");

            var xml = ReadEntry(path);
            if (xml == null)
                throw new XlsxException("شیت «" + name + "» در فایل وجود ندارد.");
            var sheet = ParseSheet(name, xml);
            _cache[name] = sheet;
            return sheet;
        }

        private XlsxSheet ParseSheet(string name, string xml)
        {
            var sheet = new XlsxSheet { Name = name };
            var doc = XDocument.Parse(xml);

            var merges = doc.Root.Element(Main + "mergeCells");
            if (merges != null)
            {
                foreach (var m in merges.Elements(Main + "mergeCell"))
                {
                    var reference = (string)m.Attribute("ref") ?? "";
                    var parts = reference.Split(':');
                    if (parts.Length != 2) continue;
                    int r1, c1, r2, c2;
                    if (TryParseRef(parts[0], out r1, out c1) &&
                        TryParseRef(parts[1], out r2, out c2))
                        sheet.Merges.Add(Tuple.Create(r1, c1, r2, c2));
                }
            }

            var data = doc.Root.Element(Main + "sheetData");
            if (data == null) return sheet;

            foreach (var rowEl in data.Elements(Main + "row"))
            {
                int rowNum;
                if (!int.TryParse((string)rowEl.Attribute("r"), out rowNum) || rowNum == 0)
                    rowNum = sheet.MaxRow + 1;

                foreach (var c in rowEl.Elements(Main + "c"))
                {
                    var reference = (string)c.Attribute("r") ?? "";
                    int r, col;
                    if (!TryParseRef(reference, out r, out col)) continue;
                    var cell = ParseCell(c, r, col, reference);
                    if (cell.Kind == "empty") continue;

                    Dictionary<int, XlsxCell> line;
                    if (!sheet.Rows.TryGetValue(r, out line))
                    {
                        line = new Dictionary<int, XlsxCell>();
                        sheet.Rows[r] = line;
                    }
                    line[col] = cell;
                    if (r > sheet.MaxRow) sheet.MaxRow = r;
                    if (col > sheet.MaxCol) sheet.MaxCol = col;
                }
            }
            return sheet;
        }

        private XlsxCell ParseCell(XElement c, int row, int col, string reference)
        {
            var type = (string)c.Attribute("t") ?? "n";
            var cell = new XlsxCell { Row = row, Col = col, Ref = reference };
            if (c.Element(Main + "f") != null) cell.HasFormula = true;

            var v = c.Element(Main + "v");

            if (type == "inlineStr")
            {
                var isEl = c.Element(Main + "is");
                cell.Text = isEl == null ? "" : CollectText(isEl);
                cell.Kind = cell.Text.Length == 0 ? "empty" : "text";
                return cell;
            }
            if (v == null || v.Value == null) return cell;

            var raw = v.Value;
            switch (type)
            {
                case "s":
                    int idx;
                    if (!int.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out idx)
                        || idx < 0 || idx >= _shared.Count)
                        throw new XlsxException("ارجاع رشته نامعتبر در سلول " + reference);
                    cell.Text = _shared[idx];
                    cell.Kind = cell.Text.Length == 0 ? "empty" : "text";
                    return cell;
                case "str":
                    cell.Text = raw;
                    cell.Kind = raw.Length == 0 ? "empty" : "text";
                    return cell;
                case "b":
                    cell.Text = raw == "1" ? "TRUE" : "FALSE";
                    cell.Kind = "bool";
                    return cell;
                case "e":
                    cell.Text = raw;
                    cell.Kind = "error";
                    return cell;
                case "d":
                    cell.Text = raw;
                    cell.Kind = "text";
                    return cell;
            }

            double num;
            if (!double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out num))
            {
                cell.Text = raw;
                cell.Kind = "text";
                return cell;
            }
            cell.Number = num;
            cell.Kind = "number";
            cell.Text = FormatNumber(num);
            return cell;
        }

        /// <summary>Render a stored number without inventing decimals:
        /// 1500 -> "1500", 1500.5 -> "1500.5".</summary>
        public static string FormatNumber(double num)
        {
            if (num == Math.Floor(num) && Math.Abs(num) < 1e15)
                return ((long)num).ToString(CultureInfo.InvariantCulture);
            return num.ToString("0.##########", CultureInfo.InvariantCulture);
        }

        public static int ColToIndex(string letters)
        {
            int n = 0;
            foreach (var ch in letters)
                n = n * 26 + (ch - 'A' + 1);
            return n;
        }

        public static string IndexToCol(int n)
        {
            var sb = new StringBuilder();
            while (n > 0)
            {
                var rem = (n - 1) % 26;
                sb.Insert(0, (char)('A' + rem));
                n = (n - 1) / 26;
            }
            return sb.ToString();
        }

        public static bool TryParseRef(string reference, out int row, out int col)
        {
            row = 0;
            col = 0;
            if (string.IsNullOrEmpty(reference)) return false;
            int i = 0;
            while (i < reference.Length && char.IsLetter(reference[i])) i++;
            if (i == 0 || i == reference.Length) return false;
            col = ColToIndex(reference.Substring(0, i).ToUpperInvariant());
            return int.TryParse(reference.Substring(i), NumberStyles.Integer,
                                CultureInfo.InvariantCulture, out row) && row > 0;
        }

        public void Dispose()
        {
            if (_zip != null) _zip.Dispose();
        }
    }
}
