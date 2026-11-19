#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Import engine, stages 1-4: read, detect, map, validate.

Pipeline (each stage is a separate, testable step — the owner's contract says
"upload != commit", so nothing here writes to the database):

    1. READ      xlsx_io.Workbook  (stdlib only)
    2. DETECT    which of the 11 templates this file is
    3. MAP       columns by HEADER NAME, two header rows (en + fa)
    4. VALIDATE  per-cell typing, blank != zero, Jalali dates, formulas

Stage 5 (resolve codes against real DB keys) and stage 6 (atomic commit) live
in import_engine.py so that validation can be proven with zero database.

Design notes that are NOT obvious:
  * A column is matched by English header first, Persian second. If neither
    matches, the file is REJECTED rather than imported with a shifted mapping —
    a shifted mapping silently writes purchase weights into discount columns.
  * Missing required fields are a file-level error (the mapping is wrong),
    while a blank required VALUE is a row-level error (that row is bad).
  * "blank != zero" is enforced by carrying None, never 0, for an absent cell.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import import_contract as C
from import_contract import (CODE, COUNT, FLAG01, GRAM, KG, KIND, PERCENT,
                             RIAL, RIAL_SIGNED, SHAMSI, TEXT, TIME)
from xlsx_io import Workbook, XlsxError, format_number

# ---------------------------------------------------------------------------
# Jalali helpers (no dependency: a wrong calendar is worse than a small table)
# ---------------------------------------------------------------------------
_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]


def is_leap_jalali(year: int) -> bool:
    """33-year cycle, the standard civil approximation used by .NET's
    PersianCalendar for 1343..1472."""
    return ((year + 12) % 33) % 4 == 1


def valid_shamsi(text: str) -> Tuple[bool, str]:
    """Accept only YYYY/MM/DD or YYYYMMDD. A bare number is rejected on
    purpose: an Excel serial (e.g. 45292) is NOT a date and silently
    misreading it shifts every document by decades."""
    if text is None:
        return False, "تاریخ خالی است"
    raw = str(text).strip()
    if re.fullmatch(r"\d{8}", raw):
        raw = f"{raw[0:4]}/{raw[4:6]}/{raw[6:8]}"
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", raw)
    if not m:
        if re.fullmatch(r"\d+(\.\d+)?", str(text).strip()):
            return False, "تاریخ به‌صورت عدد ذخیره شده (Excel serial)؛ باید YYYY/MM/DD باشد"
        return False, "قالب تاریخ باید YYYY/MM/DD باشد"
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1200 <= y <= 1600):
        return False, f"سال شمسی خارج از بازه معقول: {y}"
    if not (1 <= mo <= 12):
        return False, f"ماه نامعتبر: {mo}"
    dim = _DAYS_IN_MONTH[mo - 1]
    if mo == 12 and is_leap_jalali(y):
        dim = 30
    if not (1 <= d <= dim):
        return False, f"روز نامعتبر برای ماه {mo}: {d}"
    return True, f"{y:04d}/{mo:02d}/{d:02d}"


def valid_time(text: str) -> Tuple[bool, str]:
    raw = str(text).strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
    if not m:
        return False, "ساعت باید HH:mm باشد"
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return False, "ساعت خارج از بازه"
    return True, f"{h:02d}:{mi:02d}"


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------
@dataclass
class RowError:
    field: str
    message: str


@dataclass
class ParsedRow:
    source_row: int
    values: Dict[str, object] = field(default_factory=dict)   # en name -> typed value
    blanks: List[str] = field(default_factory=list)           # fields blank in source
    errors: List[RowError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    numeric_codes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ParseResult:
    template: Optional[C.Template] = None
    sheet_name: str = ""
    header_map: Dict[str, int] = field(default_factory=dict)   # en name -> column
    unmatched_headers: List[str] = field(default_factory=list)
    file_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    rows: List[ParsedRow] = field(default_factory=list)
    ignored_blank_rows: int = 0

    @property
    def ok(self) -> bool:
        return not self.file_errors

    @property
    def valid_rows(self) -> List[ParsedRow]:
        return [r for r in self.rows if r.ok]

    @property
    def invalid_rows(self) -> List[ParsedRow]:
        return [r for r in self.rows if not r.ok]


# ---------------------------------------------------------------------------
# Stage 2 — detect
# ---------------------------------------------------------------------------
def detect_template(wb: Workbook) -> Tuple[Optional[C.Template], str, List[str]]:
    """Score each template by how many of its English/Persian headers appear in
    the first few rows of the data sheet. Returns (template, sheet, notes)."""
    notes: List[str] = []
    sheet = _find_data_sheet(wb, notes)
    if sheet is None:
        return None, "", notes + ["شیت «داده‌ها» پیدا نشد."]

    sh = wb.sheet(sheet)
    header_cells = set()
    for r in (1, 2):
        for c in range(1, min(sh.max_col, 60) + 1):
            txt = sh.cell(r, c).text.strip()
            if txt:
                header_cells.add(txt.lower())

    best, best_score = None, 0.0
    for tpl in C.ALL.values():
        hits = 0
        for f in tpl.fields:
            if f.name_en.lower() in header_cells or f.name_fa in header_cells:
                hits += 1
        score = hits / max(1, len(tpl.fields))
        if score > best_score:
            best, best_score = tpl, score

    if best is None or best_score < 0.5:
        return None, sheet, notes + [
            "نوع فایل شناسایی نشد: کمتر از نیمی از سرستون‌ها با هیچ‌کدام از "
            "۱۱ قالب رسمی نمی‌خواند."]
    return best, sheet, notes


def _find_data_sheet(wb: Workbook, notes: List[str]) -> Optional[str]:
    for name in wb.sheets:
        if name.strip() in C.DATA_SHEET_NAMES:
            return name
    # Fall back to the sheet that looks most like a data sheet.
    for name in wb.sheets:
        sh = wb.sheet(name)
        if sh.max_col >= 3 and sh.max_row >= 2:
            notes.append(f"شیت استاندارد «داده‌ها» نبود؛ از شیت «{name}» استفاده شد.")
            return name
    return None


# ---------------------------------------------------------------------------
# Stage 3 — map headers
# ---------------------------------------------------------------------------
def _header_row_candidates(tpl: C.Template, sh) -> List[int]:
    """Which rows may hold a header.

    The contract originally assumed TWO rows: English then Persian. The owner's
    real workbooks under `داده‌ها` carry a SINGLE Persian header row — the
    English row only exists in the `فرهنگ داده` sheet. Importing
    `01_Parties.xlsx` from Drive therefore failed with "required headers are
    missing" while every column was in fact present and correctly labelled.

    Accepting either language in either of the first two rows costs nothing and
    removes an assumption the fixtures had quietly baked in.
    """
    rows = []
    for row_no in (tpl.header_row_en, tpl.header_row_fa):
        if row_no not in rows and row_no <= max(sh.max_row, 1):
            rows.append(row_no)
    return rows


def _last_header_row(tpl: C.Template, sh) -> int:
    """The last row that actually holds header labels.

    Counting headers by POSITION is wrong in both directions: the contract's
    two-row layout puts data at row 3, and the owner's real single-header files
    put data at row 2. Asking the file which rows contain field labels answers
    both, and cannot silently skip the owner's first data row.
    """
    labels = set()
    for f in tpl.fields:
        labels.add(f.name_en.lower())
        labels.add(f.name_fa)
    last = 0
    for row_no in _header_row_candidates(tpl, sh):
        for c in range(1, min(sh.max_col, 200) + 1):
            txt = sh.cell(row_no, c).text.strip()
            if txt and txt.lower() in labels:
                last = max(last, row_no)
                break
    return last or tpl.header_row_en


def map_headers(tpl: C.Template, sh) -> Tuple[Dict[str, int], List[str]]:
    """Match by header NAME, in either language, in either header row.

    English row first so a bilingual file prefers its English labels; the
    Persian row is the fallback and also catches a single-header file.
    """
    mapping: Dict[str, int] = {}
    used = set()

    for row_no in _header_row_candidates(tpl, sh):
        for c in range(1, min(sh.max_col, 200) + 1):
            txt = sh.cell(row_no, c).text.strip()
            if not txt:
                continue
            f = tpl.by_en(txt) or tpl.by_fa(txt)
            if f and f.name_en not in mapping and c not in used:
                mapping[f.name_en] = c
                used.add(c)

    unmatched = []
    for c in range(1, min(sh.max_col, 200) + 1):
        txt = sh.cell(tpl.header_row_en, c).text.strip() or \
              sh.cell(tpl.header_row_fa, c).text.strip()
        if txt and c not in used:
            unmatched.append(f"{txt} (ستون {c})")
    return mapping, unmatched


# ---------------------------------------------------------------------------
# Stage 4 — validate values
# ---------------------------------------------------------------------------
def _to_grams(cell) -> Tuple[Optional[int], Optional[str]]:
    """kg -> integer grams, max 3 decimals. More than 3 decimals is refused
    instead of silently rounded: the owner asked for traceability, and a
    silently rounded weight cannot be traced back."""
    if cell.is_blank:
        return None, None
    if cell.kind == "number":
        raw = format_number(cell.number)
    else:
        raw = cell.text.strip().replace("٬", "").replace(",", "").replace("٫", ".")
    try:
        val = float(raw)
    except ValueError:
        return None, f"وزن عددی نیست: «{cell.text}»"
    if val < 0:
        return None, "وزن منفی است"
    if "." in raw and len(raw.split(".")[1]) > 3:
        return None, f"وزن بیش از ۳ رقم اعشار دارد: {raw}"
    grams = round(val * 1000)
    # Guard against float noise: 1.5 kg must be exactly 1500, not 1499.
    if abs(grams - val * 1000) > 0.5:
        return None, f"وزن قابل تبدیل به گرم نیست: {raw}"
    return int(grams), None


def _to_int(cell, signed=False) -> Tuple[Optional[int], Optional[str]]:
    if cell.is_blank:
        return None, None
    if cell.kind == "number":
        num = cell.number
    else:
        raw = cell.text.strip().replace("٬", "").replace(",", "").replace("−", "-")
        try:
            num = float(raw)
        except ValueError:
            return None, f"عدد نیست: «{cell.text}»"
    if not signed and num < 0:
        return None, "مقدار منفی مجاز نیست"
    if abs(num - round(num)) > 1e-9:
        return None, f"باید عدد صحیح باشد: {format_number(num)}"
    return int(round(num)), None


def _to_percent(cell) -> Tuple[Optional[float], Optional[str]]:
    if cell.is_blank:
        return None, None
    raw = cell.text.strip()
    try:
        val = float(raw)
    except ValueError:
        return None, f"درصد عددی نیست: «{cell.text}»"
    if not (0 <= val <= 100):
        return None, "درصد باید بین ۰ و ۱۰۰ باشد"
    return val, None


def validate_row(tpl: C.Template, sh, row_no: int,
                 mapping: Dict[str, int]) -> ParsedRow:
    row = ParsedRow(source_row=row_no)
    for f in tpl.fields:
        col = mapping.get(f.name_en)
        cell = sh.cell(row_no, col) if col else None

        if cell is None or cell.is_blank:
            # R7: blank is ABSENT, not zero.
            row.blanks.append(f.name_en)
            row.values[f.name_en] = None
            if f.required:
                row.errors.append(RowError(f.name_en, f"«{f.name_fa}» الزامی است و خالی است"))
            continue

        if cell.formula:
            row.errors.append(RowError(
                f.name_en, f"«{f.name_fa}» فرمول دارد؛ در شیت داده فرمول مجاز نیست"))
            continue

        if f.kind in (CODE,) and cell.is_numeric_text:
            row.numeric_codes.append(f.name_en)
            row.warnings.append(
                f"«{f.name_fa}» به‌صورت عدد ذخیره شده؛ صفرهای ابتدایی ممکن است از دست رفته باشد")

        value, err = _convert(f, cell)
        if err:
            row.errors.append(RowError(f.name_en, err))
            continue

        if f.kind == KIND and f.choices and value not in f.choices:
            row.errors.append(RowError(
                f.name_en, f"مقدار «{value}» مجاز نیست؛ یکی از {', '.join(f.choices)}"))
            continue

        if f.kind == CODE and len(str(value)) > f.max_len:
            row.errors.append(RowError(f.name_en, f"طول مقدار بیش از {f.max_len} است"))
            continue

        row.values[f.name_en] = value
    return row


def _convert(f: C.Field, cell) -> Tuple[object, Optional[str]]:
    if f.kind == TEXT:
        return cell.text.strip(), None
    if f.kind in (CODE, KIND):
        return cell.text.strip(), None
    if f.kind == SHAMSI:
        ok, out = valid_shamsi(cell.text)
        return (out, None) if ok else (None, out)
    if f.kind == TIME:
        ok, out = valid_time(cell.text)
        return (out, None) if ok else (None, out)
    if f.kind == KG:
        return _to_grams(cell)
    if f.kind == GRAM:
        return _to_int(cell)
    if f.kind == RIAL:
        return _to_int(cell)
    if f.kind == RIAL_SIGNED:
        return _to_int(cell, signed=True)
    if f.kind == COUNT:
        return _to_int(cell)
    if f.kind == PERCENT:
        return _to_percent(cell)
    if f.kind == FLAG01:
        raw = cell.text.strip()
        if raw in ("1", "0"):
            return int(raw), None
        if raw.lower() in ("true", "false"):
            return (1 if raw.lower() == "true" else 0), None
        if raw == "":
            return None, None
        return None, "مقدار باید ۱ یا ۰ باشد"
    return cell.text.strip(), None


# ---------------------------------------------------------------------------
# The whole read->detect->map->validate pipeline
# ---------------------------------------------------------------------------
def parse_file(path: str, expected: Optional[str] = None) -> ParseResult:
    res = ParseResult()
    try:
        wb = Workbook(path)
    except XlsxError as e:
        res.file_errors.append(str(e))
        return res

    try:
        tpl, sheet, notes = detect_template(wb)
        res.warnings.extend(notes)
        if tpl is None:
            res.file_errors.extend(notes or ["نوع فایل شناسایی نشد."])
            return res
        res.template = tpl
        res.sheet_name = sheet

        if expected and expected != tpl.code:
            res.file_errors.append(
                f"نوع تشخیص‌داده‌شده ({tpl.code}) با نوع انتخاب‌شده ({expected}) نمی‌خواند.")
            return res

        sh = wb.sheet(sheet)
        _check_layout(tpl, sh, res)
        mapping, unmatched = map_headers(tpl, sh)
        res.header_map = mapping
        res.unmatched_headers = unmatched
        if unmatched:
            res.warnings.append(
                "سرستون‌های ناشناخته نادیده گرفته شد: " + "، ".join(unmatched))

        missing = [f.name_fa for f in tpl.required if f.name_en not in mapping]
        if missing:
            res.file_errors.append(
                "سرستون‌های الزامی گم شده‌اند: " + "، ".join(missing) +
                " — نگاشت ستون‌ها انجام نشد تا داده در جای اشتباه نوشته نشود.")
            return res

        _check_merges(sh, res)

        # Where data starts depends on how many header rows the file actually
        # has, not on a constant. The contract's data_start_row = 3 assumes the
        # two-row English+Persian layout; the owner's real workbooks have ONE
        # Persian header row, so their data begins at row 2. Using the constant
        # silently skipped the owner's first data row on every real file.
        data_start = _last_header_row(tpl, sh) + 1
        row_no = data_start
        while row_no <= max(sh.max_row, data_start):
            cells = [sh.cell(row_no, c) for c in mapping.values()]
            if all(c.is_blank for c in cells):
                res.ignored_blank_rows += 1
                row_no += 1
                continue
            res.rows.append(validate_row(tpl, sh, row_no, mapping))
            row_no += 1

        return res
    finally:
        wb.close()


def _check_layout(tpl: C.Template, sh, res: ParseResult):
    """Two header rows are the contract. If row 2 holds data rather than the
    Persian header, say so loudly: otherwise every Persian label is read as a
    data value and the whole file is silently wrong."""
    fa_row = sh.cell(tpl.header_row_fa, 1).text.strip()
    en_row = sh.cell(tpl.header_row_en, 1).text.strip()
    tpl_fa_first = tpl.fields[0].name_fa
    if not en_row:
        res.file_errors.append("ردیف ۱ (سرستون انگلیسی) خالی است.")
        return
    if fa_row and fa_row not in (tpl_fa_first,) and tpl.by_fa(fa_row) is None:
        res.warnings.append(
            f"ردیف {tpl.header_row_fa} سرستون فارسی قالب نیست («{fa_row}»). "
            "اگر فایل تک‌هدر است، از ردیف ۱ خوانده می‌شود.")
    if not fa_row:
        res.warnings.append(
            f"ردیف {tpl.header_row_fa} خالی است؛ فرض شد فایل تک‌هدر است "
            "و داده از ردیف ۲ شروع می‌شود.")
        # Shift: treat row 2 as data by re-reading from there.
        setattr(res, "_single_header", True)


def _check_merges(sh, res: ParseResult):
    for (r1, c1, r2, c2) in sh.merges:
        if r1 <= 2 and c1 <= sh.max_col:
            continue                       # a merged title above the header is fine
        res.warnings.append(
            f"سلول ادغام‌شده در محدوده داده: ردیف {r1} تا {r2} — طبق قاعده قالب مجاز نیست "
            "و ممکن است باعث از دست رفتن مقدار شود.")
        break
