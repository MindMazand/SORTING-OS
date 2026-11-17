#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — XLSX read/write with the standard library only.

WHY NOT openpyxl:
  * The product must install and run fully offline on Windows 8.1 x64 with no
    Python at all; the shipping reader will be C#. This module is the
    *reference implementation* the C# port is checked against, so it must
    mirror the real file format rather than hide behind a library that
    silently keeps values we need to see (see TEXT LOSS below).
  * No third-party dependency means the test harness runs anywhere, including
    a bare sandbox with no pip access.

TEXT LOSS — the reason `cell.text` and `cell.value` are separate:
  The owner's golden rule is "codes are text; read cell.Text, not cell.Value,
  to preserve leading zeros". In XLSX a code typed into a General cell is
  stored as a NUMBER: the leading zeros are already gone from the file, and no
  reader can recover them. So the reader exposes both, and `is_numeric_text`
  lets the import engine *warn* that a code column arrived as a number instead
  of pretending the value is trustworthy.

Supported: shared strings, inline strings, formula cached values, booleans,
numbers, ISO dates, both date systems would need styles.xml (not read here —
the import engine rejects raw serial dates by contract).
"""
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


class XlsxError(Exception):
    """Malformed or unreadable workbook."""


@dataclass
class Cell:
    """One grid cell. `text` is what the user sees; `number` is the raw
    numeric value when the cell really is numeric."""
    row: int
    col: int
    ref: str
    text: str = ""
    number: Optional[float] = None
    kind: str = "empty"          # empty | text | number | bool | error
    formula: bool = False

    @property
    def is_blank(self) -> bool:
        return self.kind == "empty" or self.text.strip() == ""

    @property
    def is_numeric_text(self) -> bool:
        """True when a code-like column arrived as a real number (leading
        zeros may have been lost before the file was even saved)."""
        return self.kind == "number"


@dataclass
class Sheet:
    name: str
    rows: Dict[int, Dict[int, Cell]] = field(default_factory=dict)
    max_row: int = 0
    max_col: int = 0
    # Merged ranges as (top_row, left_col, bottom_row, right_col). The owner's
    # golden rule 8 forbids merged cells inside the data sheet, so the import
    # engine must be able to SEE them rather than silently reading only the
    # top-left cell (which is what every naive reader does).
    merges: List[tuple] = field(default_factory=list)

    def cell(self, row: int, col: int) -> Cell:
        return self.rows.get(row, {}).get(col, Cell(row, col, ""))

    def row_values(self, row: int) -> List[str]:
        return [self.cell(row, c).text for c in range(1, self.max_col + 1)]


def col_to_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def index_to_col(n: int) -> str:
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _text_of(node) -> str:
    """Concatenate all <t> runs, skipping phonetic runs (<rPh>)."""
    parts = []
    for t in node.iter(NS_MAIN + "t"):
        parts.append(t.text or "")
    return "".join(parts)


def _ph_skip(node) -> str:
    parts = []
    for child in node:
        if child.tag == NS_MAIN + "rPh":
            continue
        if child.tag == NS_MAIN + "t":
            parts.append(child.text or "")
        elif child.tag == NS_MAIN + "r":
            for t in child.iter(NS_MAIN + "t"):
                parts.append(t.text or "")
    return "".join(parts)


class Workbook:
    """Read-only workbook view: sheet order, names, and lazily parsed sheets."""

    def __init__(self, path: str):
        self.path = path
        try:
            self._zip = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, FileNotFoundError) as e:
            raise XlsxError(f"فایل قابل خواندن نیست (xlsx معتبر نیست): {e}")
        names = set(self._zip.namelist())
        if "xl/workbook.xml" not in names:
            raise XlsxError("ساختار xlsx ناقص است: xl/workbook.xml پیدا نشد.")
        self._shared = self._read_shared_strings()
        self.sheets: List[str] = []
        self._sheet_paths: Dict[str, str] = {}
        self._read_workbook()
        self._cache: Dict[str, Sheet] = {}

    # -- internals ---------------------------------------------------------
    def _read_shared_strings(self) -> List[str]:
        if "xl/sharedStrings.xml" not in self._zip.namelist():
            return []
        root = ET.fromstring(self._zip.read("xl/sharedStrings.xml"))
        out = []
        for si in root.findall(NS_MAIN + "si"):
            out.append(_ph_skip(si))
        return out

    def _read_workbook(self):
        rels = {}
        if "xl/_rels/workbook.xml.rels" in self._zip.namelist():
            rroot = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
            for rel in rroot.findall(NS_PKG_REL + "Relationship"):
                target = rel.get("Target", "")
                if target.startswith("/"):
                    target = target[1:]
                elif not target.startswith("xl/"):
                    target = "xl/" + target
                rels[rel.get("Id")] = target

        root = ET.fromstring(self._zip.read("xl/workbook.xml"))
        sheets = root.find(NS_MAIN + "sheets")
        if sheets is None:
            raise XlsxError("هیچ شیتی در فایل نیست.")
        for i, sh in enumerate(sheets.findall(NS_MAIN + "sheet"), start=1):
            name = sh.get("name") or f"Sheet{i}"
            rid = sh.get(NS_REL + "id")
            path = rels.get(rid) or f"xl/worksheets/sheet{i}.xml"
            self.sheets.append(name)
            self._sheet_paths[name] = path

    def close(self):
        try:
            self._zip.close()
        except Exception:
            pass

    def sheet(self, name: str) -> Sheet:
        if name in self._cache:
            return self._cache[name]
        path = self._sheet_paths.get(name)
        if not path or path not in self._zip.namelist():
            raise XlsxError(f"شیت «{name}» در فایل وجود ندارد.")
        sh = self._parse_sheet(name, self._zip.read(path))
        self._cache[name] = sh
        return sh

    def _parse_sheet(self, name: str, blob: bytes) -> Sheet:
        sh = Sheet(name=name)
        root = ET.fromstring(blob)
        mc = root.find(NS_MAIN + "mergeCells")
        if mc is not None:
            for m in mc.findall(NS_MAIN + "mergeCell"):
                ref = m.get("ref") or ""
                if ":" not in ref:
                    continue
                a, b = ref.split(":", 1)
                ma, mb = CELL_REF.match(a), CELL_REF.match(b)
                if not ma or not mb:
                    continue
                sh.merges.append((int(ma.group(2)), col_to_index(ma.group(1)),
                                  int(mb.group(2)), col_to_index(mb.group(1))))
        data = root.find(NS_MAIN + "sheetData")
        if data is None:
            return sh
        for row_el in data.findall(NS_MAIN + "row"):
            r = int(row_el.get("r") or 0)
            if r == 0:
                r = sh.max_row + 1
            for c in row_el.findall(NS_MAIN + "c"):
                ref = c.get("r") or ""
                m = CELL_REF.match(ref)
                if not m:
                    continue
                col = col_to_index(m.group(1))
                cell = self._parse_cell(c, r, col, ref)
                if cell.kind == "empty":
                    continue
                sh.rows.setdefault(r, {})[col] = cell
                sh.max_row = max(sh.max_row, r)
                sh.max_col = max(sh.max_col, col)
        return sh

    def _parse_cell(self, c, row: int, col: int, ref: str) -> Cell:
        t = c.get("t") or "n"
        cell = Cell(row=row, col=col, ref=ref)
        f = c.find(NS_MAIN + "f")
        if f is not None:
            cell.formula = True
        v = c.find(NS_MAIN + "v")

        if t == "inlineStr":
            is_el = c.find(NS_MAIN + "is")
            cell.text = _ph_skip(is_el) if is_el is not None else ""
            cell.kind = "text" if cell.text else "empty"
            return cell

        if v is None or v.text is None:
            return cell

        raw = v.text
        if t == "s":
            try:
                cell.text = self._shared[int(raw)]
            except (ValueError, IndexError):
                raise XlsxError(f"ارجاع رشته نامعتبر در سلول {ref}")
            cell.kind = "text" if cell.text else "empty"
            return cell

        if t == "str":                       # formula result, stored as text
            cell.text = raw
            cell.kind = "text" if raw else "empty"
            return cell

        if t == "b":
            cell.text = "TRUE" if raw == "1" else "FALSE"
            cell.kind = "bool"
            return cell

        if t == "e":
            cell.text = raw
            cell.kind = "error"
            return cell

        if t == "d":
            cell.text = raw
            cell.kind = "text"
            return cell

        # numeric
        try:
            num = float(raw)
        except ValueError:
            cell.text = raw
            cell.kind = "text"
            return cell
        cell.number = num
        cell.kind = "number"
        cell.text = format_number(num)
        return cell


def format_number(num: float) -> str:
    """Render a stored number the way a user would read it, without inventing
    decimals: 1500.0 -> '1500', 1500.5 -> '1500.5'."""
    if num == int(num) and abs(num) < 1e15:
        return str(int(num))
    out = f"{num:.10f}".rstrip("0").rstrip(".")
    return out or "0"


# ===========================================================================
# Minimal writer — used ONLY to build test fixtures that look like real Excel
# output (shared strings, two header rows, three sheets). It is deliberately
# not a general-purpose writer: no styles, no formulas.
# ===========================================================================
def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def write_workbook(path: str, sheets: Dict[str, List[List[object]]],
                   numeric_cells: Dict[str, set] = None) -> None:
    """Write a workbook. Every value becomes a STRING (shared string) unless
    (sheet, (row, col)) is listed in `numeric_cells`, which lets a fixture
    reproduce the real-world "code stored as a number" defect."""
    numeric_cells = numeric_cells or {}
    shared: List[str] = []
    index: Dict[str, int] = {}

    def sid(text: str) -> int:
        if text not in index:
            index[text] = len(shared)
            shared.append(text)
        return index[text]

    sheet_xml = []
    for name, grid in sheets.items():
        numeric = numeric_cells.get(name, set())
        parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
                 '<sheetData>']
        for r, row in enumerate(grid, start=1):
            parts.append(f'<row r="{r}">')
            for c, val in enumerate(row, start=1):
                ref = f"{index_to_col(c)}{r}"
                if val is None or val == "":
                    continue
                if (r, c) in numeric:
                    parts.append(f'<c r="{ref}"><v>{val}</v></c>')
                else:
                    parts.append(f'<c r="{ref}" t="s"><v>{sid(str(val))}</v></c>')
            parts.append("</row>")
        parts.append("</sheetData></worksheet>")
        sheet_xml.append("".join(parts))

    names = list(sheets.keys())
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(
            f'<sheet name="{_esc(n)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, n in enumerate(names, start=1))
        + "</sheets></workbook>")

    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(names) + 1))
        + f'<Relationship Id="rId{len(names)+1}" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        '</Relationships>')

    strings_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t xml:space=\"preserve\">{_esc(s)}</t></si>" for s in shared)
        + "</sst>")

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.'
            'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(names) + 1))
        + '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>")

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook_xml)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/sharedStrings.xml", strings_xml)
        for i, xml in enumerate(sheet_xml, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
