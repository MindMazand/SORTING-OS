#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Machine-readable contract for the owner's 11 import templates.

Source of truth: docs/WORKBOOK_SPEC_FA.md §3 (extracted from the owner's real
files in Google Drive, 2026-11-16). This module is the ONE place the contract
lives; the validator, the mapper, the docs and the C# port all read from here.
If a template column changes, it changes here and nowhere else.

Fidelity rules encoded below (all repeated verbatim in every template):
  R1  match columns by HEADER NAME, never by position
  R2  data sheet has TWO header rows: row 1 English, row 2 Persian
  R3  codes are TEXT; a code that arrives as a number has lost leading zeros
  R4  Jalali dates YYYY/MM/DD; an Excel serial number is an error, not a date
  R5  kg with at most 3 decimals; stored as integer grams
  R6  Rial only, integer; never Toman
  R7  blank != zero
  R8  no formulas / merged cells / total rows inside the data sheet
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Field kinds
# ---------------------------------------------------------------------------
TEXT = "text"          # free text, stored verbatim
CODE = "code"          # stable system code; must stay a string
KIND = "kind"          # small controlled vocabulary (e.g. PERSON/COMPANY)
SHAMSI = "shamsi"      # Jalali date YYYY/MM/DD
TIME = "time"          # HH:mm
KG = "kg"              # kg number, <= 3 decimals -> integer grams
GRAM = "gram"          # already grams (integer)
RIAL = "rial"          # integer Rial, non-negative
RIAL_SIGNED = "rial_signed"   # integer Rial, may be negative (adjustments)
COUNT = "count"        # non-negative integer
PERCENT = "percent"    # 0..100
FLAG01 = "flag01"      # "1"/"0"


@dataclass(frozen=True)
class Field:
    name_en: str
    name_fa: str
    kind: str
    required: bool = False
    db_column: Optional[str] = None      # target column in the local schema
    lookup: Optional[str] = None         # reference table this CODE resolves in
    choices: Optional[List[str]] = None
    max_len: int = 500
    note: str = ""

    @property
    def key(self) -> str:
        return self.name_en


@dataclass(frozen=True)
class Template:
    code: str                     # PARTIES, PRODUCTS, ...
    file_name: str                # expected file name
    module_fa: str
    fields: List[Field]
    header_row_en: int = 1
    header_row_fa: int = 2
    data_start_row: int = 3
    idempotency_field: Optional[str] = None   # the SourceXxxCode field
    notes: str = ""

    def by_en(self, name: str) -> Optional[Field]:
        for f in self.fields:
            if f.name_en.lower() == (name or "").strip().lower():
                return f
        return None

    def by_fa(self, name: str) -> Optional[Field]:
        clean = (name or "").strip()
        for f in self.fields:
            if f.name_fa == clean:
                return f
        return None

    @property
    def required(self) -> List[Field]:
        return [f for f in self.fields if f.required]


def _f(*a, **k) -> Field:
    return Field(*a, **k)


# ===========================================================================
# 01 — Parties
# ===========================================================================
PARTIES = Template(
    code="PARTIES",
    file_name="01_Parties.xlsx",
    module_fa="اشخاص",
    idempotency_field="PartyCode",
    notes="کد حسابداری/مانده افتتاحیه از این قالب ساخته نمی‌شود و باید جداگانه با تأیید ثبت شود.",
    fields=[
        _f("PartyCode", "کد شخص", CODE, True, "code", max_len=40),
        _f("DisplayName", "نام نمایشی", TEXT, True, "display_name", max_len=120),
        _f("PartyType", "نوع شخص", KIND, True, "party_kind",
           choices=["PERSON", "COMPANY"]),
        _f("FullName", "نام کامل / نام شرکت", TEXT, False, None, max_len=200,
           note="ستون مستقل در v002 ندارد؛ در صورت نیاز به 003 منتقل می‌شود"),
        _f("NationalId", "کد ملی / شناسه ملی", CODE, False, "national_code", max_len=20,
           note="متن، برای حفظ صفر ابتدایی"),
        _f("EconomicCode", "شماره اقتصادی", CODE, False, "economic_code", max_len=20),
        _f("Mobile", "موبایل", CODE, False, "mobile", max_len=15),
        _f("Phone", "تلفن", CODE, False, "phone", max_len=20),
        _f("Address", "نشانی", TEXT, False, "address", max_len=400),
        _f("Note", "یادداشت", TEXT, False, None, max_len=400,
           note="parties ستون description ندارد"),
    ],
)

# ===========================================================================
# 02 — Products
# ===========================================================================
PRODUCTS = Template(
    code="PRODUCTS",
    file_name="02_Products.xlsx",
    module_fa="محصولات",
    idempotency_field="ProductCode",
    notes="گروه و واحد باید از اطلاعات پایه داخل نرم‌افزار انتخاب شوند، نه متن آزاد.",
    fields=[
        _f("ProductCode", "کد محصول", CODE, True, "code", max_len=40),
        _f("ProductName", "نام محصول", TEXT, True, "name", max_len=120),
        _f("GroupCode", "کد گروه محصول", CODE, True, "group_id",
           lookup="product_groups:code"),
        _f("UnitCode", "کد واحد", CODE, True, "unit_id", lookup="units:code"),
        _f("VarietyName", "نام تجاری / رقم", TEXT, False, "variety_name", max_len=120),
        _f("IsActive", "فعال", FLAG01, False, "is_active"),
        _f("Note", "یادداشت", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 03 — Weighing In (baskol)
# ===========================================================================
WEIGHING_IN = Template(
    code="WEIGHING_IN",
    file_name="03_Weighing_In.xlsx",
    module_fa="باسکول ورودی",
    idempotency_field="SourceDocCode",
    notes="این قالب فقط ورود بار است؛ خروج موجودی از فاکتور فروش یا سند انتقال ثبت می‌شود. "
          "طبق DEC-NEW-007 باسکول هیچ مبلغی ثبت نمی‌کند.",
    fields=[
        _f("SourceDocCode", "کد سند منبع", CODE, True, "source_key", max_len=60,
           note="کلید Idempotency"),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("Time", "ساعت", TIME, False, "time"),
        _f("Direction", "جهت", KIND, True, "direction", choices=["IN"]),
        _f("PartyCode", "کد طرف حساب", CODE, True, "party_id", lookup="parties:code"),
        _f("ProductCode", "کد محصول", CODE, True, "product_id", lookup="products:code"),
        _f("WarehouseCode", "کد انبار", CODE, True, "warehouse_id", lookup="warehouses:code"),
        _f("ScaleKg", "وزن ناخالص (kg)", KG, True, "gross_grams"),
        _f("TareKg", "وزن ظرف/سبد (kg)", KG, False, "tare_grams"),
        _f("NetKg", "وزن خالص (kg)", KG, True, "net_grams",
           note="بازسازی می‌شود: Net = Gross - Tare، سپس با مقدار فایل مقایسه "
                "و در صورت اختلاف هشدار (تفاوت ثبت می‌شود، پنهان نمی‌شود)"),
        _f("PackageCount", "تعداد بسته", COUNT, False, "package_count"),
        _f("PackagingCode", "کد نوع بسته‌بندی", CODE, False, "packaging_id",
           lookup="packaging_types:code"),
        _f("ReceiptNumber", "شماره قبض", CODE, False, "receipt_number", max_len=40),
        _f("Note", "یادداشت", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 04 — Purchase invoices
# ===========================================================================
PURCHASE_INVOICES = Template(
    code="PURCHASE_INVOICES",
    file_name="04_Purchase_Invoices.xlsx",
    module_fa="فاکتور خرید",
    idempotency_field="SourceInvoiceCode",
    notes="هر ردیف باید به کد باسکول ورودی تأییدشده متصل باشد. فی، ریال بر کیلوگرم است. "
          "فاکتور موجودی را دوباره نمی‌شمارد (DEC-NEW-007).",
    fields=[
        _f("SourceInvoiceCode", "کد فاکتور منبع", CODE, True, "source_key", max_len=60),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("SupplierCode", "کد فروشنده", CODE, True, "party_id", lookup="parties:code"),
        _f("WeighCode", "کد باسکول ورودی", CODE, True, "weigh_ticket_id",
           lookup="weigh_tickets:doc_number"),
        _f("ProductCode", "کد محصول", CODE, True, "product_id", lookup="products:code"),
        _f("PurchaseKg", "وزن خرید (kg)", KG, True, "grams"),
        _f("RateRialPerKg", "فی خرید (ریال/kg)", RIAL, True, "rate_rial_per_kg"),
        _f("DiscountRial", "تخفیف (ریال)", RIAL, False, "discount_rial"),
        _f("FreightRial", "کرایه (ریال)", RIAL, False, "freight_rial"),
        _f("CommissionRial", "کمیسیون (ریال)", RIAL, False, "commission_rial"),
        _f("OtherAdjustmentsRial", "سایر تعدیلات (ریال)", RIAL_SIGNED, False,
           "adjustments_rial"),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 05 — Sales invoices
# ===========================================================================
SALES_INVOICES = Template(
    code="SALES_INVOICES",
    file_name="05_Sales_Invoices.xlsx",
    module_fa="فاکتور فروش",
    idempotency_field="SourceInvoiceCode",
    notes="فروش باید به محصوله موجود و تأییدشده متصل باشد.",
    fields=[
        _f("SourceInvoiceCode", "کد فاکتور منبع", CODE, True, "source_key", max_len=60),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("BuyerCode", "کد خریدار", CODE, True, "party_id", lookup="parties:code"),
        _f("LotCode", "کد محصوله", CODE, True, "lot_id", lookup="lots:code"),
        _f("SortOutputCode", "کد خروجی سورت", CODE, False, "sorting_output_id",
           lookup="sorting_outputs:code"),
        _f("ProductCode", "کد محصول", CODE, True, "product_id", lookup="products:code"),
        _f("SaleKg", "وزن فروش (kg)", KG, True, "grams"),
        _f("RateRialPerKg", "فی فروش (ریال/kg)", RIAL, True, "rate_rial_per_kg"),
        _f("DiscountRial", "تخفیف (ریال)", RIAL, False, "discount_rial"),
        _f("FreightRial", "کرایه (ریال)", RIAL, False, "freight_rial"),
        _f("CommissionRial", "کمیسیون (ریال)", RIAL, False, "commission_rial"),
        _f("OtherCostsRial", "سایر هزینه‌ها (ریال)", RIAL, False, "other_costs_rial"),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 06 — Sorting
# ===========================================================================
SORTING = Template(
    code="SORTING",
    file_name="06_Sorting.xlsx",
    module_fa="سورتینگ",
    idempotency_field="SortDocCode",
    notes="قاعده بنیادی: InputKg = OutputKg + WasteKg + ProcessLossKg + Variance "
          "و |Variance| <= ToleranceKg.",
    fields=[
        _f("SortDocCode", "کد سند سورت", CODE, True, "source_key", max_len=60),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("InputLotCode", "کد محموله ورودی", CODE, True, "lot_id",
           lookup="lots:code"),
        _f("InputWarehouseCode", "کد انبار ورودی", CODE, True, None,
           lookup="warehouses:code"),
        _f("InputKg", "وزن ورودی (kg)", KG, True, "input_grams"),
        _f("OutputProductCode", "کد محصول خروجی", CODE, True, "product_id",
           lookup="products:code"),
        _f("GradeCode", "کد درجه", CODE, False, "grade_id", lookup="grades:code"),
        _f("PackagingCode", "کد بسته‌بندی", CODE, False, "packaging_id",
           lookup="packaging_types:code"),
        _f("OutputWarehouseCode", "کد انبار خروجی", CODE, True, "warehouse_id",
           lookup="warehouses:code"),
        _f("OutputKg", "وزن خروجی (kg)", KG, True, "grams"),
        _f("PackageCount", "تعداد بسته", COUNT, False, "package_count"),
        _f("WasteKg", "ضایعات (kg)", KG, False, "waste_grams"),
        _f("ProcessLossKg", "افت فرآیند (kg)", KG, False, "process_loss_grams"),
        _f("ToleranceKg", "تلورانس (kg)", KG, False, "tolerance_grams"),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 07 — Basket movements
# ===========================================================================
BASKET_MOVEMENTS = Template(
    code="BASKET_MOVEMENTS",
    file_name="07_Basket_Movements.xlsx",
    module_fa="گردش سبد",
    idempotency_field="SourceDocCode",
    notes="گردش تعداد سبد از گردش پولی مستقل است. برگشت امانی فقط در محدوده مانده "
          "امانی تأییدشده مجاز است.",
    fields=[
        _f("SourceDocCode", "کد سند منبع", CODE, True, "source_key", max_len=60),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("MovementType", "نوع عملیات", KIND, True, "event_type",
           choices=["PURCHASE", "ISSUE", "RETURN", "TRANSFER", "OPENING"]),
        _f("BasketTypeCode", "کد نوع سبد", CODE, True, "basket_id", lookup="baskets:code"),
        _f("FromWarehouseCode", "کد انبار مبدأ", CODE, False, "from_warehouse_id",
           lookup="warehouses:code"),
        _f("ToWarehouseCode", "کد انبار مقصد", CODE, False, "to_warehouse_id",
           lookup="warehouses:code"),
        _f("PartyCode", "کد طرف حساب", CODE, False, "party_id", lookup="parties:code"),
        _f("Quantity", "تعداد", COUNT, True, "quantity"),
        _f("PurchaseValueRial", "فی خرید (ریال)", RIAL, False, "rate_rial"),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 08 — Bank transactions
# ===========================================================================
BANK_TRANSACTIONS = Template(
    code="BANK_TRANSACTIONS",
    file_name="08_Bank_Transactions.xlsx",
    module_fa="تراکنش بانکی",
    idempotency_field="SourceTxnCode",
    notes="هر ردیف باید یک جهت مشخص داشته باشد. ورود پول فقط از این ماژول است "
          "(DEC-NEW-007).",
    fields=[
        _f("SourceTxnCode", "کد تراکنش منبع", CODE, True, "source_key", max_len=60),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("Time", "ساعت", TIME, False, "time"),
        _f("BankAccountCode", "کد حساب بانکی", CODE, True, "bank_account_id",
           lookup="bank_accounts:code"),
        _f("Direction", "جهت", KIND, True, "direction", choices=["IN", "OUT"]),
        _f("PartyCode", "کد طرف حساب", CODE, False, "party_id", lookup="parties:code"),
        _f("SubGroupCode", "کد زیرگروه", CODE, False, "sub_group_id",
           lookup="sub_groups:code"),
        _f("AmountRial", "مبلغ اصلی (ریال)", RIAL, True, None),
        _f("FeeRial", "کارمزد (ریال)", RIAL, False, "fee_rial"),
        _f("ReportedBalanceRial", "مانده پس از تراکنش (ریال)", RIAL, False,
           "bank_balance_rial"),
        _f("TrackingNumber", "شماره پیگیری", CODE, False, "tracking_number", max_len=40),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 09 — Cheques
# ===========================================================================
CHEQUES = Template(
    code="CHEQUES",
    file_name="09_Cheques.xlsx",
    module_fa="چک",
    idempotency_field="SourceDocCode",
    notes="شماره چک و شناسه صیادی متنهستند تا صفر ابتدایی حذف نشود. "
          "جهت قالب IN/OUT است اما در دیتابیس RECEIVED/ISSUED ذخیره می‌شود.",
    fields=[
        _f("SourceDocCode", "کد سند منبع", CODE, True, "source_key", max_len=60),
        _f("Direction", "جهت چک", KIND, True, "direction", choices=["IN", "OUT"]),
        _f("PartyCode", "کد طرف حساب", CODE, True, "beneficiary_party_id",
           lookup="parties:code"),
        _f("BankAccountCode", "کد حساب بانکی", CODE, False, "bank_account_id",
           lookup="bank_accounts:code"),
        _f("ChequeNumber", "شماره چک", CODE, True, "cheque_number", max_len=30),
        _f("SayadId", "شناسه صیادی", CODE, False, "sayad_id", max_len=16),
        _f("IssueDateShamsi", "تاریخ صدور", SHAMSI, True, "issue_date_shamsi"),
        _f("DueDateShamsi", "تاریخ سررسید", SHAMSI, True, "due_date_shamsi"),
        _f("AmountRial", "مبلغ (ریال)", RIAL, True, None),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 10 — Settlements (allocations)
# ===========================================================================
SETTLEMENTS = Template(
    code="SETTLEMENTS",
    file_name="10_Settlements.xlsx",
    module_fa="تخصیص تسویه",
    idempotency_field="SourceAllocationCode",
    notes="این قالب فقط سند پرداخت موجود را به فاکتور موجود وصل می‌کند؛ خودش تراکنش "
          "بانکی یا سند حسابداری جدید نمی‌سازد.",
    fields=[
        _f("SourceAllocationCode", "کد سند تخصیص منبع", CODE, True, "source_key", max_len=60),
        _f("PaymentDocNumber", "شماره سند پرداخت", CODE, True, "payment_id",
           lookup="payments:doc_number"),
        _f("InvoiceNumber", "شماره فاکتور", CODE, True, "invoice_id",
           lookup="invoices:doc_number"),
        _f("AllocationRial", "مبلغ تخصیص (ریال)", RIAL, True, "amount_rial"),
        _f("InstrumentType", "نوع ابزار", KIND, True, "instrument_type",
           choices=["BANK", "CHEQUE", "CREDIT_NOTE", "OTHER"]),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

# ===========================================================================
# 11 — Partnership
# ===========================================================================
PARTNERSHIP = Template(
    code="PARTNERSHIP",
    file_name="11_Partnership.xlsx",
    module_fa="عملیات شرکت",
    idempotency_field="SourceRowCode",
    notes="تعداد سبد مصرف‌شده برای تار و تعداد سبد برگشتی امانی دو فیلد مستقل‌اند.",
    fields=[
        _f("SourceRowCode", "کد ردیف منبع", CODE, True, "source_key", max_len=60),
        _f("DateShamsi", "تاریخ شمسی", SHAMSI, True, "date_shamsi"),
        _f("EventType", "نوع عملیات", KIND, True, "event_type",
           choices=["PARTNER_IN", "CUSTODY_OUT", "COLDSTORE_TRANSFER"]),
        _f("PartnerCode", "کد شریک", CODE, True, "party_id",
           lookup="parties:code"),
        _f("ProductCode", "کد محصول", CODE, False, "product_id", lookup="products:code"),
        _f("BasketTypeCode", "کد نوع سبد", CODE, False, "basket_id",
           lookup="baskets:code"),
        _f("WarehouseCode", "کد انبار", CODE, False, "warehouse_id",
           lookup="warehouses:code"),
        _f("GrossKg", "وزن ناخالص (kg)", KG, False, "gross_grams"),
        _f("ConsumedBaskets", "تعداد سبد مصرف‌شده", COUNT, False, "consumed_baskets"),
        _f("CustodyReturnedBaskets", "تعداد سبد برگشتی امانی", COUNT, False,
           "custody_returned_baskets"),
        _f("LossPercent", "درصد افت (%)", PERCENT, False, "loss_percent"),
        _f("ExtraWasteKg", "ضایعات اضافه (kg)", KG, False, "extra_waste_grams"),
        _f("PartnerSharePercent", "درصد سهم شریک (%)", PERCENT, False,
           "partner_share_percent"),
        _f("RoundingUnitKg", "واحد گردکردن (kg)", KG, False, "rounding_unit_grams"),
        _f("RoundingMode", "روش گردکردن", KIND, False, "rounding_mode",
           choices=["NEAREST", "UP", "DOWN", "NONE"]),
        _f("PurchaseAggregationCode", "کد تجمیع خرید", CODE, False,
           "purchase_aggregation_id", lookup="purchase_aggregations:code"),
        _f("ReceiptNumber", "شماره قبض", CODE, False, "receipt_number", max_len=40),
        _f("OriginPlace", "محل مبدأ", TEXT, False, "origin_place", max_len=120),
        _f("DestinationPlace", "محل مقصد", TEXT, False, "destination_place", max_len=120),
        _f("Note", "شرح", TEXT, False, "description", max_len=400),
    ],
)

ALL: Dict[str, Template] = {
    t.code: t for t in (
        PARTIES, PRODUCTS, WEIGHING_IN, PURCHASE_INVOICES, SALES_INVOICES,
        SORTING, BASKET_MOVEMENTS, BANK_TRANSACTIONS, CHEQUES, SETTLEMENTS,
        PARTNERSHIP,
    )
}

# Order matters: later files reference codes created by earlier ones.
IMPORT_ORDER = [
    "PARTIES", "PRODUCTS", "WEIGHING_IN", "PURCHASE_INVOICES", "SALES_INVOICES",
    "SORTING", "BASKET_MOVEMENTS", "BANK_TRANSACTIONS", "CHEQUES",
    "SETTLEMENTS", "PARTNERSHIP",
]

DATA_SHEET_NAMES = ("داده‌ها", "داده ها", "Data", "data")
GUIDE_SHEET_NAMES = ("راهنما", "راهنما ۱", "Guide", "guide")
DICT_SHEET_NAMES = ("فرهنگ داده", "فرهنگ داده‌ها", "Data Dictionary", "Dictionary")
