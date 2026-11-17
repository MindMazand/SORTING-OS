#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Import engine, stages 5-7: resolve, commit, roll back.

Stage 5  RESOLVE   every CODE cell must resolve to a REAL row id. A code that
                   does not exist is a row error, never a new row: importing an
                   unknown party code would silently invent a person.
Stage 6  COMMIT    one SQLite transaction for the whole batch, ledger-style
                   idempotency via import_batches/import_rows, and stock/money
                   rules from DEC-NEW-007.
Stage 7  ROLLBACK  a committed batch can be undone by deleting exactly the
                   rows it created (tracked by id), and only while those
                   documents are still DRAFT.

Why the import writes DRAFT only:
  Spec ch.6/8 requires manager approval. An imported document that arrives
  pre-approved would bypass the approval workflow entirely, so the importer
  can never produce an APPROVED row. It also means rollback is legal: the
  immutability triggers only guard APPROVED records.

Stock rules enforced here (DEC-NEW-007):
  * goods enter ONLY via the weighbridge -> 03 writes stock IN movements.
  * purchase/sales invoices do NOT move stock. A sales invoice lines up with
    an existing lot and only records money, because the goods already left
    through the weighbridge.
"""
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import import_contract as C
import import_parser as P
from xlsx_io import Workbook

# How a template's resolved values land in the database.
# Each entry: (table, {template field: db column}, extra static columns)
TARGETS = {
    "PARTIES": ("parties", "code"),
    "PRODUCTS": ("products", "code"),
    "WEIGHING_IN": ("weigh_tickets", "source_key"),
    "PURCHASE_INVOICES": ("purchase_invoices", "source_key"),
    "SALES_INVOICES": ("sales_invoices", "source_key"),
    "SORTING": ("sorting_batches", "code"),
    "BASKET_MOVEMENTS": ("basket_movements", None),
    "BANK_TRANSACTIONS": ("bank_transactions", "code"),
    "CHEQUES": ("cheques", "code"),
    "SETTLEMENTS": ("payment_allocations", None),
    "PARTNERSHIP": ("partnership_events", None),
}

# Codes created BY an earlier template, used to verify import order.
CREATES = {
    "PARTIES": "parties",
    "PRODUCTS": "products",
    "WEIGHING_IN": "weigh_tickets",
    "PURCHASE_INVOICES": "purchase_invoices",
    "SALES_INVOICES": "sales_invoices",
    "SORTING": "sorting_batches",
    "BASKET_MOVEMENTS": "basket_movements",
    "BANK_TRANSACTIONS": "bank_transactions",
    "CHEQUES": "cheques",
    "SETTLEMENTS": "payment_allocations",
    "PARTNERSHIP": "partnership_events",
}


@dataclass
class ResolvedRow:
    row: P.ParsedRow
    ids: Dict[str, int] = field(default_factory=dict)     # ref key -> resolved id
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.row.ok


@dataclass
class BatchResult:
    batch_id: Optional[int] = None
    created: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Stage 5 — resolve
# ---------------------------------------------------------------------------
# A virtual lookup target: `invoices:doc_number` is not a table. The owner
# enters ONE invoice number and the system must find it on either side. Before
# migration 004's view existed this lookup raised "no such table: invoices" and
# the settlements template could never import at all.
VIRTUAL_LOOKUPS = {
    "invoices:doc_number": "v_invoice_lookup",
}


def _lookup_row(con, spec: str, code: str):
    """Resolve a code to a row. Returns (id, kind) where kind is only meaningful
    for a virtual lookup."""
    view = VIRTUAL_LOOKUPS.get(spec)
    if view:
        row = con.execute(
            f"SELECT id, kind FROM {view} WHERE doc_number = ?", (code,)).fetchone()
        return (row[0], row[1]) if row else (None, None)
    table, _, column = spec.partition(":")
    column = column or "code"
    row = con.execute(f"SELECT id FROM {table} WHERE {column} = ?", (code,)).fetchone()
    return (row[0], None) if row else (None, None)


def _lookup(con, spec: str, code: str) -> Optional[int]:
    return _lookup_row(con, spec, code)[0]


def resolve_rows(con, tpl: C.Template, rows: List[P.ParsedRow]) -> List[ResolvedRow]:
    out = []
    for r in rows:
        rr = ResolvedRow(row=r)
        if not r.ok:
            rr.errors.extend(e.message for e in r.errors)
            out.append(rr)
            continue
        for f in tpl.fields:
            if not f.lookup:
                continue
            code = r.values.get(f.name_en)
            if code in (None, ""):
                if f.required:
                    rr.errors.append(f"«{f.name_fa}» الزامی است")
                continue
            rid, kind = _lookup_row(con, f.lookup, str(code))
            if rid is None:
                table = VIRTUAL_LOOKUPS.get(f.lookup, f.lookup).split(":")[0]
                rr.errors.append(
                    f"«{f.name_fa}» = «{code}» در اطلاعات پایه ({table}) پیدا نشد. "
                    "ابتدا آن را بسازید یا فایل مبدأ را وارد کنید.")
            else:
                rr.ids[f.name_en] = rid
                if kind is not None:
                    # Which side the invoice was found on decides which FK the
                    # settlement line may fill. Carried under a dunder key so it
                    # can never collide with a template field name.
                    rr.ids["__invoice_kind"] = kind
        out.append(rr)
    return out


# ---------------------------------------------------------------------------
# Cross-file business rules (stage 6 preconditions)
# ---------------------------------------------------------------------------
def check_rules(tpl: C.Template, rr: ResolvedRow) -> None:
    v = rr.row.values
    if tpl.code == "WEIGHING_IN":
        gross, tare = v.get("ScaleKg"), v.get("TareKg")
        net = v.get("NetKg")
        if net is not None and net < 0:
            rr.errors.append("وزن خالص منفی است — ورودی بار نمی‌تواند منفی باشد")
        natural_net = (gross - (tare or 0)) if gross is not None else None
        if natural_net is not None:
            if net is not None and abs(natural_net - net) > 1000:
                rr.warnings.append(
                    f"وزن خالص فایل ({net/1000:.3f} kg) با «ناخالص − تار» "
                    f"({natural_net/1000:.3f} kg) بیش از ۱ کیلو اختلاف دارد؛ مقدار فایل ثبت می‌شود.")
        if v.get("Direction") not in (None, "IN"):
            rr.errors.append("در قالب باسکول ورودی، جهت فقط IN مجاز است")

    if tpl.code == "SORTING":
        input_g = v.get("InputKg") or 0
        out_g = v.get("OutputKg") or 0
        waste = v.get("WasteKg") or 0
        loss = v.get("ProcessLossKg") or 0
        tol = v.get("ToleranceKg")
        variance = input_g - (out_g + waste + loss)
        if tol is None:
            rr.warnings.append(
                "تلورانس ذکر نشده؛ مغایرت با تلورانس پیش‌فرض سیستم سنجیده می‌شود")
            tol = 0
        if abs(variance) > max(tol, 0):
            rr.errors.append(
                f"موازنه جرم برقرار نیست: ورودی {input_g/1000:.3f} ≠ خروجی+ضایعات+افت "
                f"{(out_g+waste+loss)/1000:.3f} (مغایرت {variance/1000:.3f} kg، "
                f"تلورانس {tol/1000:.3f} kg)")

    if tpl.code == "BASKET_MOVEMENTS":
        qty = v.get("Quantity")
        if qty is not None and qty < 0:
            rr.errors.append("تعداد سبد نمی‌تواند منفی باشد")
        if v.get("MovementType") == "TRANSFER":
            if not v.get("FromWarehouseCode"):
                rr.errors.append("انتقال سبد نیازمند انبار مبدأ است")
            if not v.get("ToWarehouseCode"):
                rr.errors.append("انتقال سبد نیازمند انبار مقصد است")
        if v.get("MovementType") in ("PURCHASE", "ISSUE", "RETURN") and not v.get("PartyCode"):
            rr.warnings.append("طرف حساب برای این نوع گردش معمولاً لازم است")

    if tpl.code == "CHEQUES":
        sid = v.get("SayadId")
        if sid and (len(str(sid)) != 16 or not str(sid).isdigit()):
            rr.errors.append("شناسه صیادی باید دقیقاً ۱۶ رقم باشد")
        i, d = v.get("IssueDateShamsi"), v.get("DueDateShamsi")
        if i and d and d < i:
            rr.errors.append("تاریخ سررسید نمی‌تواند قبل از تاریخ صدور باشد")

    if tpl.code == "PURCHASE_INVOICES":
        grams, rate = v.get("PurchaseKg"), v.get("RateRialPerKg")
        if grams is not None and rate is not None:
            gross = (grams * rate + 500) // 1000     # Rial, half-up on Rial
            if gross <= 0:
                rr.errors.append("مبلغ ناخالص فاکتور صفر یا منفی است")

    if tpl.code == "PURCHASE_INVOICES" or tpl.code == "SALES_INVOICES":
        for name in ("DiscountRial", "FreightRial", "CommissionRial"):
            val = v.get(name)
            grams, rate = v.get("PurchaseKg") or v.get("SaleKg"), v.get("RateRialPerKg")
            if val and grams and rate:
                gross = (grams * rate) // 1000
                if val > gross:
                    rr.warnings.append(
                        f"{name} از مبلغ ناخالص ({gross:,} ریال) بیشتر است؛ بررسی شود")

    if tpl.code == "SETTLEMENTS":
        if (v.get("AllocationRial") or 0) <= 0:
            rr.errors.append("مبلغ تخصیص باید مثبت باشد")


# ---------------------------------------------------------------------------
# Stage 6 — commit
# ---------------------------------------------------------------------------
def _next_code(con, table: str, prefix: str) -> str:
    """Generate the next stable system code (e.g. C001) from the highest one
    already present. Display names stay editable; codes never change."""
    rows = con.execute(
        f"SELECT code FROM {table} WHERE code LIKE ? ORDER BY length(code) DESC, code DESC LIMIT 1",
        (prefix + "%",)).fetchall()
    if not rows:
        return f"{prefix}001"
    tail = rows[0][0][len(prefix):]
    n = int(tail) if tail.isdigit() else 0
    return f"{prefix}{n + 1:03d}"


def _select_columns(con, table: str, wanted: Dict[str, object]) -> Dict[str, object]:
    """Refuse keys the table does not have.

    This used to DROP unknown keys "so a contract typo cannot become a runtime
    crash". The price was silent data loss: the contract mapped the partner to
    `partner_party_id`, the column is `party_id`, and every partnership event
    was imported with a NULL partner and no warning. A loud failure at the first
    row is far cheaper than a quiet NULL discovered months later.
    """
    info = list(con.execute(f"PRAGMA table_info({table})"))
    cols = {r[1] for r in info}
    unknown = sorted(set(wanted) - cols)
    if unknown:
        raise ValueError(
            f"ستون‌های ناشناخته برای جدول {table}: {', '.join(unknown)} — "
            "نگاشت قرارداد با اسکیما نمی‌خواند")

    # A blank cell is None here, and "blank is not zero" is a product rule, so
    # None must not be turned into 0. But writing an explicit NULL over a column
    # declared NOT NULL DEFAULT '' is a different thing: it overrides the
    # default the schema chose for "not supplied" and fails the insert. For
    # those columns the correct move is to OMIT the key and let the schema
    # speak, which is what dropping it here does. Nullable columns keep their
    # None, so a blank loss_percent stays NULL rather than becoming 0%.
    omitted = {r[1] for r in info if r[3] == 1 and r[4] is not None}
    return {k: v for k, v in wanted.items() if not (v is None and k in omitted)}


def _insert(con, table: str, values: Dict[str, object]) -> int:
    values = _select_columns(con, table, values)
    keys = list(values.keys())
    sql = (f"INSERT INTO {table} ({', '.join(keys)}) "
           f"VALUES ({', '.join('?' for _ in keys)})")
    cur = con.execute(sql, [values[k] for k in keys])
    return cur.lastrowid


def import_file(con, path: str, expected: Optional[str] = None,
                created_by: Optional[int] = None,
                commit: bool = True) -> BatchResult:
    """Read, validate, resolve and (optionally) commit one file.

    `commit=False` is the PREVIEW path: it does everything except write
    documents, which is what the owner's "upload != commit" rule requires.
    """
    res = P.parse_file(path, expected)
    out = BatchResult()
    if not res.ok:
        out.errors.extend(res.file_errors)
        return out

    tpl = res.template
    table, key_column = TARGETS[tpl.code]

    if commit:
        con.execute("BEGIN IMMEDIATE")
    try:
        existing_keys = set()
        if key_column:
            col = "source_key" if key_column == "code" and "source_key" in {
                r[1] for r in con.execute(f"PRAGMA table_info({table})")} else key_column
            existing_keys = {r[0] for r in con.execute(
                f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL")}
        seen_in_file = set()

        resolved = resolve_rows(con, tpl, res.rows)
        for rr in resolved:
            check_rules(tpl, rr)
            if rr.ok and tpl.idempotency_field:
                key = rr.row.values.get(tpl.idempotency_field)
                if key in existing_keys or key in seen_in_file:
                    where = "در همین فایل" if key in seen_in_file else "قبلاً"
                    rr.errors.append(f"تکراری: «{key}» {where} وارد شده است")
                    rr.warnings.append("DUPLICATE")
                seen_in_file.add(key)

        batch_id = None
        if commit:
            batch_id = _insert(con, "import_batches", {
                "code": f"IMP-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
                "file_name": os.path.basename(path),
                "file_type": "XLSX",
                "detected_type": tpl.code,
                "header_row": tpl.header_row_en,
                "header_row_second": tpl.header_row_fa,
                "file_sha256": file_sha256(path),
                "status": "REVIEW",
                "total_rows": len(res.rows),
                "valid_rows": len([r for r in resolved if r.ok]),
                "duplicate_rows": len([r for r in resolved if "DUPLICATE" in r.warnings]),
                "invalid_rows": len([r for r in resolved if not r.ok]),
                "created_by": created_by,
            })
            out.batch_id = batch_id

        for rr in resolved:
            row_id = None
            if commit and batch_id:
                row_id = _insert(con, "import_rows", {
                    "batch_id": batch_id,
                    "row_number": rr.row.source_row,
                    "source_row_number": rr.row.source_row,
                    "raw_json": json.dumps(rr.row.values, ensure_ascii=False, default=str),
                    "mapped_json": json.dumps(rr.ids, ensure_ascii=False),
                    "blank_fields_json": json.dumps(rr.row.blanks, ensure_ascii=False),
                    "status": "INVALID" if not rr.ok else "VALID",
                    "error_message": " | ".join(rr.errors)[:900],
                })

            if not rr.ok:
                out.failed += 1
                out.errors.append(f"ردیف {rr.row.source_row}: " + " | ".join(rr.errors))
                continue

            if not commit:
                out.created += 1
                continue

            try:
                new_id = _write_document(con, tpl, rr)
                if row_id:
                    con.execute(
                        "UPDATE import_rows SET status='IMPORTED', mapped_json=? WHERE id=?",
                        (json.dumps({"new_id": new_id}, ensure_ascii=False), row_id))
                out.created += 1
            except sqlite3.Error as e:
                out.failed += 1
                out.errors.append(f"ردیف {rr.row.source_row}: پایگاه داده رد کرد — {e}")
                if row_id:
                    con.execute(
                        "UPDATE import_rows SET status='INVALID', error_message=? WHERE id=?",
                        (str(e)[:900], row_id))

        if commit:
            con.execute(
                "UPDATE import_batches SET status='APPROVED' WHERE id=?", (batch_id,))
            con.execute("COMMIT")
        return out
    except Exception:
        if commit:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
        raise


def _write_document(con, tpl: C.Template, rr: ResolvedRow) -> int:
    v = rr.row.values
    ids = rr.ids
    code = tpl.code

    if code == "PARTIES":
        return _insert(con, "parties", {
            "code": v["PartyCode"],
            "display_name": v["DisplayName"],
            "party_kind": v["PartyType"],
            "party_kind_confirmed": 1,
            "economic_code": v.get("EconomicCode"),
            "national_code": v.get("NationalId") or "",
            "mobile": v.get("Mobile") or "",
            "phone": v.get("Phone") or "",
            "address": v.get("Address") or "",
            # `nature` is the account class the stable code encodes; the
            # template does not carry it, so it is derived from the prefix.
            "nature": _nature_from_code(v["PartyCode"]),
            "is_active": 1,
        })

    if code == "PRODUCTS":
        return _insert(con, "products", {
            "code": v["ProductCode"],
            "name": v["ProductName"],
            "group_id": ids.get("GroupCode"),
            "unit_id": ids.get("UnitCode"),
            "variety_name": v.get("VarietyName"),
            "is_active": 1 if v.get("IsActive") in (None, 1) else 0,
            "description": v.get("Note") or "",
        })

    if code == "WEIGHING_IN":
        gross, tare, net = v.get("ScaleKg"), v.get("TareKg"), v.get("NetKg")
        wid = _insert(con, "weigh_tickets", {
            "code": _next_code(con, "weigh_tickets", "WT"),
            "doc_number": v["SourceDocCode"],
            "source_key": v["SourceDocCode"],
            "date_iso": _iso_from_shamsi(v["DateShamsi"]),
            "date_shamsi": v["DateShamsi"],
            "time": v.get("Time") or "",
            "direction": "IN",
            "party_id": ids.get("PartyCode"),
            "product_id": ids.get("ProductCode"),
            "warehouse_id": ids.get("WarehouseCode"),   # v003
            "gross_grams": gross or 0,
            "tare_grams": tare or 0,
            "net_grams": net or 0,
            "package_count": v.get("PackageCount") or 0,
            "packaging_id": ids.get("PackagingCode"),
            "receipt_number": v.get("ReceiptNumber"),
            "status": "DRAFT",
            "description": v.get("Note") or "",
        })
        # Goods enter ONLY here (DEC-NEW-007): stock IN movement.
        lot_id = _insert(con, "lots", {
            "code": _next_code(con, "lots", "LOT"),
            "weigh_ticket_id": wid,
            "product_id": ids.get("ProductCode"),
            "warehouse_id": ids.get("WarehouseCode"),
            "quantity_grams": net or 0,
            "status": "OPEN",
        })
        _insert(con, "stock_movements", {
            "lot_id": lot_id,
            "product_id": ids.get("ProductCode"),
            "warehouse_id": ids.get("WarehouseCode"),
            "movement_type": "IN",
            "quantity_grams": net or 0,
            "ref_type": "WEIGH_TICKET",
            "ref_id": wid,
        })
        return wid

    if code == "PURCHASE_INVOICES":
        return _write_invoice(con, rr, kind="PURCHASE")

    if code == "SALES_INVOICES":
        return _write_invoice(con, rr, kind="SALES")

    if code == "SORTING":
        inp = v.get("InputKg") or 0
        out = v.get("OutputKg") or 0
        waste = v.get("WasteKg") or 0
        loss = v.get("ProcessLossKg") or 0
        tol = v.get("ToleranceKg") or 0
        bid = _insert(con, "sorting_batches", {
            "code": v["SortDocCode"],
            "source_key": v["SortDocCode"],          # v003 idempotency
            "date_shamsi": v["DateShamsi"],          # v003
            "description": v.get("Note") or "",      # v003
            "lot_id": ids.get("InputLotCode"),
            "input_grams": inp,
            "output_grams": out,
            "waste_grams": waste,
            "process_loss_grams": loss,
            "variance_grams": inp - (out + waste + loss),
            "tolerance_grams": tol,
            "status": "DRAFT",
        })
        _insert(con, "sorting_inputs", {
            "batch_id": bid, "lot_id": ids.get("InputLotCode"), "grams": inp})
        _insert(con, "sorting_outputs", {
            "batch_id": bid,
            "product_id": ids.get("OutputProductCode"),
            "grade_id": ids.get("GradeCode"),
            "packaging_id": ids.get("PackagingCode"),
            "warehouse_id": ids.get("OutputWarehouseCode"),
            "grams": out,
            "package_count": v.get("PackageCount") or 0,
        })
        if waste:
            _insert(con, "waste_records", {
                "batch_id": bid, "grams": waste, "reason": "IMPORT"})
        return bid

    if code == "BASKET_MOVEMENTS":
        return _insert(con, "basket_movements", {
            "basket_id": ids.get("BasketTypeCode"),
            "party_id": ids.get("PartyCode"),
            "counterparty_party_id": ids.get("PartyCode") if v["MovementType"] == "TRANSFER" else None,
            "event_type": v["MovementType"],
            "quantity": v.get("Quantity") or 0,
            "rate_rial": v.get("PurchaseValueRial") or 0,
            "amount_rial": (v.get("Quantity") or 0) * (v.get("PurchaseValueRial") or 0),
            "date_iso": _iso_from_shamsi(v["DateShamsi"]),
            "date_shamsi": v["DateShamsi"],
            "doc_number": v["SourceDocCode"],
            "source_key": v["SourceDocCode"],        # v003
            "from_warehouse_id": ids.get("FromWarehouseCode"),   # v003
            "to_warehouse_id": ids.get("ToWarehouseCode"),       # v003
            "description": v.get("Note") or "",
        })

    if code == "BANK_TRANSACTIONS":
        amount = v["AmountRial"]
        direction = v["Direction"]
        return _insert(con, "bank_transactions", {
            "code": v["SourceTxnCode"],
            "source_key": v["SourceTxnCode"],
            "bank_account_id": ids.get("BankAccountCode"),
            "party_id": ids.get("PartyCode"),
            "sub_group_id": ids.get("SubGroupCode"),
            "date_iso": _iso_from_shamsi(v["DateShamsi"]),
            "date_shamsi": v["DateShamsi"],
            "time": v.get("Time") or "",
            "direction": direction,
            "deposit_rial": amount if direction == "IN" else 0,
            "withdrawal_rial": amount if direction == "OUT" else 0,
            "fee_rial": v.get("FeeRial") or 0,
            "bank_balance_rial": v.get("ReportedBalanceRial") or 0,
            "reported_balance_known": 1 if v.get("ReportedBalanceRial") is not None else 0,
            "tracking_number": v.get("TrackingNumber"),
            "status": "DRAFT",
            "description": v.get("Note") or "",
        })

    if code == "CHEQUES":
        # Template says IN/OUT; the schema says RECEIVED/ISSUED. Mapping is
        # explicit here so the two vocabularies can never drift apart.
        db_dir = "RECEIVED" if v["Direction"] == "IN" else "ISSUED"
        return _insert(con, "cheques", {
            "code": _next_code(con, "cheques", "CH"),
            "cheque_number": v["ChequeNumber"],
            "source_key": v["SourceDocCode"],        # v003 idempotency
            "doc_number": v["SourceDocCode"],        # v003 document number
            "bank_account_id": ids.get("BankAccountCode"),
            "cheque_date": v["IssueDateShamsi"],
            "issue_date_shamsi": v["IssueDateShamsi"],
            "due_date_shamsi": v["DueDateShamsi"],
            "amount_rial": v["AmountRial"],
            "beneficiary_party_id": ids.get("PartyCode"),
            "direction": db_dir,
            "sayad_id": v.get("SayadId"),
            "status": "OPEN",
            "description": v.get("Note") or "",
        })

    if code == "SETTLEMENTS":
        invoice_kind = rr.ids.get("__invoice_kind")
        return _insert(con, "payment_allocations", {
            "payment_id": ids.get("PaymentDocNumber"),
            "purchase_invoice_id": ids.get("InvoiceNumber") if invoice_kind == "PURCHASE" else None,
            "sales_invoice_id": ids.get("InvoiceNumber") if invoice_kind == "SALES" else None,
            "amount_rial": v["AllocationRial"],
            "source_key": v["SourceAllocationCode"],
            "instrument_type": v.get("InstrumentType"),      # v003
            "description": v.get("Note") or "",              # v003
        })

    if code == "PARTNERSHIP":
        return _insert(con, "partnership_events", {
            "partnership_id": _default_partnership(con),
            "source_key": v["SourceRowCode"],                 # v003
            "event_type": v["EventType"],
            "date_shamsi": v["DateShamsi"],
            "party_id": ids.get("PartnerCode"),
            "product_id": ids.get("ProductCode"),             # v003
            "warehouse_id": ids.get("WarehouseCode"),         # v003
            "basket_id": ids.get("BasketTypeCode"),           # v003
            "gross_grams": v.get("GrossKg") or 0,             # v003
            "consumed_baskets": v.get("ConsumedBaskets") or 0,          # v003
            "custody_returned_baskets": v.get("CustodyReturnedBaskets") or 0,  # v003
            "extra_waste_grams": v.get("ExtraWasteKg") or 0,
            "loss_percent": v.get("LossPercent"),
            "partner_share_percent": v.get("PartnerSharePercent"),    # v003
            "rounding_unit_grams": v.get("RoundingUnitKg"),           # v003
            "rounding_mode": v.get("RoundingMode"),
            "purchase_aggregation_id": ids.get("PurchaseAggregationCode"),  # v003
            "receipt_number": v.get("ReceiptNumber"),
            "origin_place": v.get("OriginPlace"),
            "destination_place": v.get("DestinationPlace"),
            "description": v.get("Note") or "",               # v003
        })

    raise ValueError(f"no writer for {tpl.code}")


def _write_invoice(con, rr: ResolvedRow, kind: str) -> int:
    v = rr.row.values
    ids = rr.ids
    if kind == "PURCHASE":
        inv_id = _insert(con, "purchase_invoices", {
            "code": _next_code(con, "purchase_invoices", "PI"),
            "doc_number": v["SourceInvoiceCode"],
            "source_key": v["SourceInvoiceCode"],
            "date_iso": _iso_from_shamsi(v["DateShamsi"]),
            "date_shamsi": v["DateShamsi"],
            "party_id": ids.get("SupplierCode"),
            "weigh_ticket_id": ids.get("WeighCode"),
            "status": "DRAFT",
            "description": v.get("Note") or "",
        })
        grams = v["PurchaseKg"]
        rate = v["RateRialPerKg"]
        gross = (grams * rate + 500) // 1000
        discount = v.get("DiscountRial") or 0
        freight = v.get("FreightRial") or 0
        commission = v.get("CommissionRial") or 0
        adjustments = v.get("OtherAdjustmentsRial") or 0
        _insert(con, "purchase_invoice_lines", {
            "invoice_id": inv_id,
            "product_id": ids.get("ProductCode"),
            "weigh_ticket_id": ids.get("WeighCode"),
            "grams": grams,
            "rate_rial_per_kg": rate,
            "gross_rial": gross,
            "discount_rial": discount,
            "freight_rial": freight,
            "commission_rial": commission,
            "adjustments_rial": adjustments,
            "net_rial": gross + freight + commission + adjustments - discount,
        })
        # DEC-NEW-007: the invoice does NOT move stock. Goods already entered
        # through the weighbridge; a second IN movement would double-count.
        return inv_id

    inv_id = _insert(con, "sales_invoices", {
        "code": _next_code(con, "sales_invoices", "SI"),
        "doc_number": v["SourceInvoiceCode"],
        "source_key": v["SourceInvoiceCode"],
        "date_iso": _iso_from_shamsi(v["DateShamsi"]),
        "date_shamsi": v["DateShamsi"],
        "party_id": ids.get("BuyerCode"),
        "lot_id": ids.get("LotCode"),
        "status": "DRAFT",
        "description": v.get("Note") or "",
    })
    grams = v["SaleKg"]
    rate = v["RateRialPerKg"]
    gross = (grams * rate + 500) // 1000
    discount = v.get("DiscountRial") or 0
    freight = v.get("FreightRial") or 0
    commission = v.get("CommissionRial") or 0
    other = v.get("OtherCostsRial") or 0
    _insert(con, "sales_invoice_lines", {
        "invoice_id": inv_id,
        "product_id": ids.get("ProductCode"),
        "sorting_output_id": ids.get("SortOutputCode"),   # v003
        "grams": grams,
        "rate_rial_per_kg": rate,
        "gross_rial": gross,
        "discount_rial": discount,
        "freight_rial": freight,
        "commission_rial": commission,
        "other_costs_rial": other,
        "net_rial": gross - freight - commission - other - discount,
    })
    return inv_id


def _default_partnership(con) -> int:
    row = con.execute("SELECT id FROM partnerships ORDER BY id LIMIT 1").fetchone()
    if row:
        return row[0]
    return _insert(con, "partnerships", {
        "code": "PS01", "description": "شراکت اصلی"})


def _iso_from_shamsi(shamsi: str) -> str:
    """Store a Gregorian ISO date alongside the Jalali one so ordering and
    BETWEEN queries work. Jalali -> Gregorian is done arithmetically, not with
    a table, because the schema keeps both columns side by side."""
    y, m, d = (int(x) for x in shamsi.replace("-", "/").split("/"))
    jy = y - 979
    jm = m - 1
    jd = d - 1
    j_day_no = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4
    for i in range(jm):
        j_day_no += 31 if i < 6 else 30
    j_day_no += jd
    g_day_no = j_day_no + 79
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097
    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False
    gy += 4 * (g_day_no // 1461)
    g_day_no %= 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365
    md = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 12 and g_day_no >= md[gm]:
        g_day_no -= md[gm]
        gm += 1
    return f"{gy:04d}-{gm + 1:02d}-{g_day_no + 1:02d}"


def _nature_from_code(code: str) -> str:
    """The stable prefix IS the account class. Longest prefix first so CAP and
    SL are not mistaken for C and S."""
    for prefix in ("CAP", "SL", "SG", "WG", "C", "S", "E", "X", "F", "L"):
        if code.startswith(prefix):
            return prefix
    return "X"


# ---------------------------------------------------------------------------
# Stage 7 — rollback
# ---------------------------------------------------------------------------
# Deletion plan per template: an ORDERED list of steps, children first.
#
# A flat list of table names is not enough, and a one-level "children" map is
# not either. The real chain is TWO levels deep:
#     weigh_tickets -> lots -> stock_movements
# Deleting `lots` while `stock_movements` still point at them fails on the
# foreign key. Both of those mistakes were made and then caught by
# tools/test_import.py ("برگشت: باسکول با فرزندانش"); this plan is the fix.
#
# Each step is (table, column, parent) and always means
#     DELETE FROM table WHERE column IN (<ids>)
# where <ids> is either [created document id] (parent is None) or the ids
# collected for `parent` in an earlier step.
#
# So ("stock_movements", "lot_id", "lots") deletes the movements of those lots,
# and ("lots", "weigh_ticket_id", None) deletes the lots OF THIS TICKET — it does
# NOT delete the ticket itself. Writing that step as if it deleted the root was
# exactly the bug the tests caught.
ROLLBACK_PLAN = {
    # Order matters: a step can only reference a parent whose ids an EARLIER
    # step collected. Writing this list parent-first (stock before lots) made
    # the stock step silently skip, and the lot delete then failed on the FK.
    "WEIGHING_IN": [
        ("lots", "weigh_ticket_id", None),      # lots of this ticket
        ("stock_movements", "lot_id", "lots"),  # their movements
        ("weigh_tickets", "id", None),          # finally the ticket
    ],
    "SORTING": [
        ("waste_records", "batch_id", None),
        ("sorting_outputs", "batch_id", None),
        ("sorting_inputs", "batch_id", None),
        ("sorting_batches", "id", None),
    ],
    "PURCHASE_INVOICES": [
        ("purchase_invoice_lines", "invoice_id", None),
        ("purchase_invoices", "id", None),
    ],
    "SALES_INVOICES": [
        ("sales_invoice_lines", "invoice_id", None),
        ("sales_invoices", "id", None),
    ],
    "PARTIES": [("parties", "id", None)],
    "PRODUCTS": [("products", "id", None)],
    "BASKET_MOVEMENTS": [("basket_movements", "id", None)],
    "BANK_TRANSACTIONS": [("bank_transactions", "id", None)],
    "CHEQUES": [("cheques", "id", None)],
    "SETTLEMENTS": [("payment_allocations", "id", None)],
    "PARTNERSHIP": [("partnership_events", "id", None)],
}



def _children_ids(con, table: str, column: str, parent_ids: List[int]) -> List[int]:
    if not parent_ids:
        return []
    marks = ",".join("?" for _ in parent_ids)
    return [r[0] for r in con.execute(
        f"SELECT id FROM {table} WHERE {column} IN ({marks})", parent_ids)]


def _delete_ids(con, table: str, ids: List[int]) -> int:
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    con.execute(f"DELETE FROM {table} WHERE id IN ({marks})", ids)
    return len(ids)


def _run_rollback_plan(con, plan, root_id: int) -> int:
    """Delete one imported document and everything hanging off it.

    Collection runs forwards (a child's ids are only findable once its
    parent's are known); deletion runs by DEPENDENCY DEPTH, deepest first,
    root last. Neither "plan order" nor "reverse plan order" is correct:

        collect:  lots -> stock_movements -> ticket
        delete :  stock_movements (depth 2) -> lots (1) -> ticket (root)

    Deleting a lot before its stock movements fails on the foreign key, and
    deleting the ticket first fails too. Both were real failures before this
    comment was true.
    """
    collected = {}
    levels = []          # [(table, ids, depth, is_root)]
    depth_of = {}

    for table, column, parent in plan:
        candidate = [root_id] if parent is None else collected.get(parent, [])
        if not candidate:
            continue
        found = candidate if column == "id" else _children_ids(con, table, column, candidate)
        if not found:
            continue
        depth = 0 if parent is None else depth_of.get(parent, 0) + 1
        depth_of[table] = depth
        collected[table] = found
        levels.append((table, found, depth, column == "id"))

    # Deeper first; at equal depth, non-root before root so a parent document
    # is never removed while its lines still point at it.
    for table, ids, _depth, _is_root in sorted(
            levels, key=lambda x: (x[2], 0 if not x[3] else -1), reverse=True):
        _delete_ids(con, table, ids)
    return 1


def rollback_batch(con, batch_id: int) -> BatchResult:
    """Undo exactly one import batch.

    Refuses to run if any document it created has left DRAFT: an approved
    document is immutable by contract (Spec ch.6), and deleting it would
    destroy an audit trail rather than correct it.
    """
    out = BatchResult(batch_id=batch_id)
    batch = con.execute(
        "SELECT id, detected_type, status FROM import_batches WHERE id=?",
        (batch_id,)).fetchone()
    if not batch:
        out.errors.append("دسته واردسازی پیدا نشد")
        return out
    if batch[2] == "ROLLED_BACK":
        out.errors.append("این دسته قبلاً برگشت خورده است")
        return out

    tpl_code = batch[1]
    table, _ = TARGETS[tpl_code]
    plan = ROLLBACK_PLAN.get(tpl_code)
    if not plan:
        out.errors.append(f"ترتیب حذف برای قالب {tpl_code} تعریف نشده است")
        return out
    rows = con.execute(
        "SELECT id, mapped_json FROM import_rows WHERE batch_id=? AND status='IMPORTED'",
        (batch_id,)).fetchall()

    frozen = _frozen_documents(con, tpl_code)
    if frozen:
        out.errors.append(
            "برگشت ممکن نیست: اسناد تأییدشده‌ای در این دسته وجود دارند "
            f"({', '.join(frozen)}). اصلاح باید با سند معکوس انجام شود، نه حذف.")
        return out

    try:
        con.execute("BEGIN IMMEDIATE")
        for row_id, mapped in rows:
            try:
                new_id = json.loads(mapped or "{}").get("new_id")
            except json.JSONDecodeError:
                new_id = None
            if new_id is None:
                continue
            deleted = _run_rollback_plan(con, plan, new_id)
            out.created += deleted
        con.execute(
            "UPDATE import_rows SET status='SKIPPED' WHERE batch_id=?", (batch_id,))
        con.execute(
            "UPDATE import_batches SET status='ROLLED_BACK' WHERE id=?", (batch_id,))
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return out


def _frozen_documents(con, tpl_code: str) -> List[str]:
    table, _ = TARGETS.get(tpl_code, (None, None))
    if not table:
        return []
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if "status" not in cols or "source_key" not in cols:
        return []
    n = con.execute(
        f"SELECT COUNT(*) FROM {table} WHERE status='APPROVED' AND source_key IS NOT NULL"
    ).fetchone()[0]
    return [f"{table}: {n} سند تأییدشده"] if n else []
