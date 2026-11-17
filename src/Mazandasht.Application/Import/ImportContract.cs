using System;
using System.Collections.Generic;
using System.Linq;

namespace Mazandasht.Application.Import
{
    /// <summary>
    /// Field kinds. Kept as string constants (not an enum) so the value that
    /// reaches the database and the log is the exact token the Python
    /// reference uses — a numeric enum would silently renumber.
    /// </summary>
    public static class FieldKind
    {
        public const string Text = "text";
        public const string Code = "code";
        public const string Kind = "kind";
        public const string Shamsi = "shamsi";
        public const string Time = "time";
        public const string Kg = "kg";
        public const string Gram = "gram";
        public const string Rial = "rial";
        public const string RialSigned = "rial_signed";
        public const string Count = "count";
        public const string Percent = "percent";
        public const string Flag01 = "flag01";
    }

    public sealed class ImportField
    {
        public string NameEn { get; }
        public string NameFa { get; }
        public string Kind { get; }
        public bool Required { get; }
        public string DbColumn { get; }
        public string Lookup { get; }
        public IReadOnlyList<string> Choices { get; }
        public int MaxLen { get; }
        public string Note { get; }

        public ImportField(string nameEn, string nameFa, string kind, bool required = false,
                           string dbColumn = null, string lookup = null,
                           IReadOnlyList<string> choices = null, int maxLen = 500,
                           string note = "")
        {
            NameEn = nameEn ?? throw new ArgumentNullException(nameof(nameEn));
            NameFa = nameFa ?? throw new ArgumentNullException(nameof(nameFa));
            Kind = kind ?? throw new ArgumentNullException(nameof(kind));
            Required = required;
            DbColumn = dbColumn;
            Lookup = lookup;
            Choices = choices;
            MaxLen = maxLen;
            Note = note ?? "";
        }
    }

    /// <summary>
    /// One of the owner's 11 import templates.
    /// Source of truth: docs/WORKBOOK_SPEC_FA.md §3, mirrored from
    /// tools/import_contract.py. If a column changes it changes in BOTH places;
    /// tools/check_contract_parity.py fails the build when they disagree.
    /// </summary>
    public sealed class ImportTemplate
    {
        public string Code { get; }
        public string FileName { get; }
        public string ModuleFa { get; }
        public IReadOnlyList<ImportField> Fields { get; }
        public int HeaderRowEn { get; }
        public int HeaderRowFa { get; }
        public int DataStartRow { get; }
        public string IdempotencyField { get; }
        public string Notes { get; }

        public ImportTemplate(string code, string fileName, string moduleFa,
                              IReadOnlyList<ImportField> fields,
                              string idempotencyField = null, string notes = "",
                              int headerRowEn = 1, int headerRowFa = 2,
                              int dataStartRow = 3)
        {
            Code = code ?? throw new ArgumentNullException(nameof(code));
            FileName = fileName ?? "";
            ModuleFa = moduleFa ?? "";
            Fields = fields ?? throw new ArgumentNullException(nameof(fields));
            IdempotencyField = idempotencyField;
            Notes = notes ?? "";
            HeaderRowEn = headerRowEn;
            HeaderRowFa = headerRowFa;
            DataStartRow = dataStartRow;
        }

        public IEnumerable<ImportField> RequiredFields =>
            Fields.Where(f => f.Required);

        public ImportField ByEn(string name)
        {
            if (name == null) return null;
            var trimmed = name.Trim();
            return Fields.FirstOrDefault(
                f => string.Equals(f.NameEn, trimmed, StringComparison.OrdinalIgnoreCase));
        }

        public ImportField ByFa(string name)
        {
            if (name == null) return null;
            var trimmed = name.Trim();
            return Fields.FirstOrDefault(f => f.NameFa == trimmed);
        }
    }

    /// <summary>
    /// The contract itself. Field order matters: it is the order the owner's
    /// files carry, and the order `tools/check_contract_parity.py` compares.
    /// </summary>
    public static class ImportContract
    {
        private static ImportField F(string en, string fa, string kind, bool required = false,
                                     string db = null, string lookup = null,
                                     string[] choices = null, int maxLen = 500, string note = "")
            => new ImportField(en, fa, kind, required, db, lookup, choices, maxLen, note);

        private static readonly string[] YesNo01 = { "1", "0" };

        public static readonly ImportTemplate Parties = new ImportTemplate(
            "PARTIES", "01_Parties.xlsx", "اشخاص",
            new[]
            {
                F("PartyCode", "کد شخص", FieldKind.Code, true, "code", maxLen: 40),
                F("DisplayName", "نام نمایشی", FieldKind.Text, true, "display_name", maxLen: 120),
                F("PartyType", "نوع شخص", FieldKind.Kind, true, "party_kind",
                  choices: new[] { "PERSON", "COMPANY" }),
                F("FullName", "نام کامل / نام شرکت", FieldKind.Text, false, null, maxLen: 200,
                  note: "ستون مستقل در v002 ندارد؛ در صورت نیاز به 003 منتقل می‌شود"),
                F("NationalId", "کد ملی / شناسه ملی", FieldKind.Code, false, "national_code",
                  maxLen: 20, note: "متن، برای حفظ صفر ابتدایی"),
                F("EconomicCode", "شماره اقتصادی", FieldKind.Code, false, "economic_code", maxLen: 20),
                F("Mobile", "موبایل", FieldKind.Code, false, "mobile", maxLen: 15),
                F("Phone", "تلفن", FieldKind.Code, false, "phone", maxLen: 20),
                F("Address", "نشانی", FieldKind.Text, false, "address", maxLen: 400),
                F("Note", "یادداشت", FieldKind.Text, false, null, maxLen: 400,
                  note: "parties ستون description ندارد"),
            },
            idempotencyField: "PartyCode",
            notes: "کد حسابداری/مانده افتتاحیه از این قالب ساخته نمی‌شود و باید جداگانه با تأیید ثبت شود.");

        public static readonly ImportTemplate Products = new ImportTemplate(
            "PRODUCTS", "02_Products.xlsx", "محصولات",
            new[]
            {
                F("ProductCode", "کد محصول", FieldKind.Code, true, "code", maxLen: 40),
                F("ProductName", "نام محصول", FieldKind.Text, true, "name", maxLen: 120),
                F("GroupCode", "کد گروه محصول", FieldKind.Code, true, "group_id",
                  lookup: "product_groups:code"),
                F("UnitCode", "کد واحد", FieldKind.Code, true, "unit_id", lookup: "units:code"),
                F("VarietyName", "نام تجاری / رقم", FieldKind.Text, false, "variety_name", maxLen: 120),
                F("IsActive", "فعال", FieldKind.Flag01, false, "is_active"),
                F("Note", "یادداشت", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "ProductCode",
            notes: "گروه و واحد باید از اطلاعات پایه داخل نرم‌افزار انتخاب شوند، نه متن آزاد.");

        public static readonly ImportTemplate WeighingIn = new ImportTemplate(
            "WEIGHING_IN", "03_Weighing_In.xlsx", "باسکول ورودی",
            new[]
            {
                F("SourceDocCode", "کد سند منبع", FieldKind.Code, true, "source_key", maxLen: 60,
                  note: "کلید Idempotency"),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("Time", "ساعت", FieldKind.Time, false, "time"),
                F("Direction", "جهت", FieldKind.Kind, true, "direction", choices: new[] { "IN" }),
                F("PartyCode", "کد طرف حساب", FieldKind.Code, true, "party_id", lookup: "parties:code"),
                F("ProductCode", "کد محصول", FieldKind.Code, true, "product_id", lookup: "products:code"),
                F("WarehouseCode", "کد انبار", FieldKind.Code, true, "warehouse_id",
                  lookup: "warehouses:code"),
                F("ScaleKg", "وزن ناخالص (kg)", FieldKind.Kg, true, "gross_grams"),
                F("TareKg", "وزن ظرف/سبد (kg)", FieldKind.Kg, false, "tare_grams"),
                F("NetKg", "وزن خالص (kg)", FieldKind.Kg, true, "net_grams",
                  note: "بازسازی می‌شود: Net = Gross - Tare، سپس با مقدار فایل مقایسه "
                      + "و در صورت اختلاف هشدار (تفاوت ثبت می‌شود، پنهان نمی‌شود)"),
                F("PackageCount", "تعداد بسته", FieldKind.Count, false, "package_count"),
                F("PackagingCode", "کد نوع بسته‌بندی", FieldKind.Code, false, "packaging_id",
                  lookup: "packaging_types:code"),
                F("ReceiptNumber", "شماره قبض", FieldKind.Code, false, "receipt_number", maxLen: 40),
                F("Note", "یادداشت", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceDocCode",
            notes: "این قالب فقط ورود بار است؛ خروج موجودی از فاکتور فروش یا سند انتقال ثبت می‌شود. "
                 + "طبق DEC-NEW-007 باسکول هیچ مبلغی ثبت نمی‌کند.");

        public static readonly ImportTemplate PurchaseInvoices = new ImportTemplate(
            "PURCHASE_INVOICES", "04_Purchase_Invoices.xlsx", "فاکتور خرید",
            new[]
            {
                F("SourceInvoiceCode", "کد فاکتور منبع", FieldKind.Code, true, "source_key", maxLen: 60),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("SupplierCode", "کد فروشنده", FieldKind.Code, true, "party_id", lookup: "parties:code"),
                F("WeighCode", "کد باسکول ورودی", FieldKind.Code, true, "weigh_ticket_id",
                  lookup: "weigh_tickets:code"),
                F("ProductCode", "کد محصول", FieldKind.Code, true, "product_id", lookup: "products:code"),
                F("PurchaseKg", "وزن خرید (kg)", FieldKind.Kg, true, "grams"),
                F("RateRialPerKg", "فی خرید (ریال/kg)", FieldKind.Rial, true, "rate_rial_per_kg"),
                F("DiscountRial", "تخفیف (ریال)", FieldKind.Rial, false, "discount_rial"),
                F("FreightRial", "کرایه (ریال)", FieldKind.Rial, false, "freight_rial"),
                F("CommissionRial", "کمیسیون (ریال)", FieldKind.Rial, false, "commission_rial"),
                F("OtherAdjustmentsRial", "سایر تعدیلات (ریال)", FieldKind.RialSigned, false,
                  "adjustments_rial"),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceInvoiceCode",
            notes: "هر ردیف باید به کد باسکول ورودی تأییدشده متصل باشد. فی، ریال بر کیلوگرم است. "
                 + "فاکتور موجودی را دوباره نمی‌شمارد (DEC-NEW-007).");

        public static readonly ImportTemplate SalesInvoices = new ImportTemplate(
            "SALES_INVOICES", "05_Sales_Invoices.xlsx", "فاکتور فروش",
            new[]
            {
                F("SourceInvoiceCode", "کد فاکتور منبع", FieldKind.Code, true, "source_key", maxLen: 60),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("BuyerCode", "کد خریدار", FieldKind.Code, true, "party_id", lookup: "parties:code"),
                F("LotCode", "کد محصوله", FieldKind.Code, true, "lot_id", lookup: "lots:code"),
                F("SortOutputCode", "کد خروجی سورت", FieldKind.Code, false, "sorting_output_id",
                  lookup: "sorting_outputs:code"),
                F("ProductCode", "کد محصول", FieldKind.Code, true, "product_id", lookup: "products:code"),
                F("SaleKg", "وزن فروش (kg)", FieldKind.Kg, true, "grams"),
                F("RateRialPerKg", "فی فروش (ریال/kg)", FieldKind.Rial, true, "rate_rial_per_kg"),
                F("DiscountRial", "تخفیف (ریال)", FieldKind.Rial, false, "discount_rial"),
                F("FreightRial", "کرایه (ریال)", FieldKind.Rial, false, "freight_rial"),
                F("CommissionRial", "کمیسیون (ریال)", FieldKind.Rial, false, "commission_rial"),
                F("OtherCostsRial", "سایر هزینه‌ها (ریال)", FieldKind.Rial, false, "other_costs_rial"),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceInvoiceCode",
            notes: "فروش باید به محصوله موجود و تأییدشده متصل باشد.");

        public static readonly ImportTemplate Sorting = new ImportTemplate(
            "SORTING", "06_Sorting.xlsx", "سورتینگ",
            new[]
            {
                F("SortDocCode", "کد سند سورت", FieldKind.Code, true, "source_key", maxLen: 60),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("InputLotCode", "کد محموله ورودی", FieldKind.Code, true, "input_lot_id",
                  lookup: "lots:code"),
                F("InputWarehouseCode", "کد انبار ورودی", FieldKind.Code, true, "input_warehouse_id",
                  lookup: "warehouses:code"),
                F("InputKg", "وزن ورودی (kg)", FieldKind.Kg, true, "input_grams"),
                F("OutputProductCode", "کد محصول خروجی", FieldKind.Code, true, "output_product_id",
                  lookup: "products:code"),
                F("GradeCode", "کد درجه", FieldKind.Code, false, "grade_id", lookup: "grades:code"),
                F("PackagingCode", "کد بسته‌بندی", FieldKind.Code, false, "packaging_id",
                  lookup: "packaging_types:code"),
                F("OutputWarehouseCode", "کد انبار خروجی", FieldKind.Code, true, "output_warehouse_id",
                  lookup: "warehouses:code"),
                F("OutputKg", "وزن خروجی (kg)", FieldKind.Kg, true, "output_grams"),
                F("PackageCount", "تعداد بسته", FieldKind.Count, false, "package_count"),
                F("WasteKg", "ضایعات (kg)", FieldKind.Kg, false, "waste_grams"),
                F("ProcessLossKg", "افت فرآیند (kg)", FieldKind.Kg, false, "process_loss_grams"),
                F("ToleranceKg", "تلورانس (kg)", FieldKind.Kg, false, "tolerance_grams"),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SortDocCode",
            notes: "قاعده بنیادی: InputKg = OutputKg + WasteKg + ProcessLossKg + Variance "
                 + "و |Variance| <= ToleranceKg.");

        public static readonly ImportTemplate BasketMovements = new ImportTemplate(
            "BASKET_MOVEMENTS", "07_Basket_Movements.xlsx", "گردش سبد",
            new[]
            {
                F("SourceDocCode", "کد سند منبع", FieldKind.Code, true, "source_key", maxLen: 60),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("MovementType", "نوع عملیات", FieldKind.Kind, true, "event_type",
                  choices: new[] { "PURCHASE", "ISSUE", "RETURN", "TRANSFER", "OPENING" }),
                F("BasketTypeCode", "کد نوع سبد", FieldKind.Code, true, "basket_id", lookup: "baskets:code"),
                F("FromWarehouseCode", "کد انبار مبدأ", FieldKind.Code, false, "from_warehouse_id",
                  lookup: "warehouses:code"),
                F("ToWarehouseCode", "کد انبار مقصد", FieldKind.Code, false, "to_warehouse_id",
                  lookup: "warehouses:code"),
                F("PartyCode", "کد طرف حساب", FieldKind.Code, false, "party_id", lookup: "parties:code"),
                F("Quantity", "تعداد", FieldKind.Count, true, "quantity"),
                F("PurchaseValueRial", "فی خرید (ریال)", FieldKind.Rial, false, "rate_rial"),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceDocCode",
            notes: "گردش تعداد سبد از گردش پولی مستقل است. برگشت امانی فقط در محدوده مانده "
                 + "امانی تأییدشده مجاز است.");

        public static readonly ImportTemplate BankTransactions = new ImportTemplate(
            "BANK_TRANSACTIONS", "08_Bank_Transactions.xlsx", "تراکنش بانکی",
            new[]
            {
                F("SourceTxnCode", "کد تراکنش منبع", FieldKind.Code, true, "source_key", maxLen: 60),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("Time", "ساعت", FieldKind.Time, false, "time"),
                F("BankAccountCode", "کد حساب بانکی", FieldKind.Code, true, "bank_account_id",
                  lookup: "bank_accounts:code"),
                F("Direction", "جهت", FieldKind.Kind, true, "direction",
                  choices: new[] { "IN", "OUT" }),
                F("PartyCode", "کد طرف حساب", FieldKind.Code, false, "party_id", lookup: "parties:code"),
                F("SubGroupCode", "کد زیرگروه", FieldKind.Code, false, "sub_group_id",
                  lookup: "sub_groups:code"),
                F("AmountRial", "مبلغ اصلی (ریال)", FieldKind.Rial, true, "amount_rial"),
                F("FeeRial", "کارمزد (ریال)", FieldKind.Rial, false, "fee_rial"),
                F("ReportedBalanceRial", "مانده پس از تراکنش (ریال)", FieldKind.Rial, false,
                  "bank_balance_rial"),
                F("TrackingNumber", "شماره پیگیری", FieldKind.Code, false, "tracking_number", maxLen: 40),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceTxnCode",
            notes: "هر ردیف باید یک جهت مشخص داشته باشد. ورود پول فقط از این ماژول است (DEC-NEW-007).");

        public static readonly ImportTemplate Cheques = new ImportTemplate(
            "CHEQUES", "09_Cheques.xlsx", "چک",
            new[]
            {
                F("SourceDocCode", "کد سند منبع", FieldKind.Code, true, "source_key", maxLen: 60),
                F("Direction", "جهت چک", FieldKind.Kind, true, "direction",
                  choices: new[] { "IN", "OUT" }),
                F("PartyCode", "کد طرف حساب", FieldKind.Code, true, "beneficiary_party_id",
                  lookup: "parties:code"),
                F("BankAccountCode", "کد حساب بانکی", FieldKind.Code, false, "bank_account_id",
                  lookup: "bank_accounts:code"),
                F("ChequeNumber", "شماره چک", FieldKind.Code, true, "cheque_number", maxLen: 30),
                F("SayadId", "شناسه صیادی", FieldKind.Code, false, "sayad_id", maxLen: 16),
                F("IssueDateShamsi", "تاریخ صدور", FieldKind.Shamsi, true, "issue_date_shamsi"),
                F("DueDateShamsi", "تاریخ سررسید", FieldKind.Shamsi, true, "due_date_shamsi"),
                F("AmountRial", "مبلغ (ریال)", FieldKind.Rial, true, "amount_rial"),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceDocCode",
            notes: "شماره چک و شناسه صیادی متعهستند تا صفر ابتدایی حذف نشود. "
                 + "جهت قالب IN/OUT است اما در دیتابیس RECEIVED/ISSUED ذخیره می‌شود.");

        public static readonly ImportTemplate Settlements = new ImportTemplate(
            "SETTLEMENTS", "10_Settlements.xlsx", "تخصیص تسویه",
            new[]
            {
                F("SourceAllocationCode", "کد سند تخصیص منبع", FieldKind.Code, true, "source_key",
                  maxLen: 60),
                F("PaymentDocNumber", "شماره سند پرداخت", FieldKind.Code, true, "payment_id",
                  lookup: "payments:doc_number"),
                F("InvoiceNumber", "شماره فاکتور", FieldKind.Code, true, "invoice_id",
                  lookup: "invoices:doc_number"),
                F("AllocationRial", "مبلغ تخصیص (ریال)", FieldKind.Rial, true, "amount_rial"),
                F("InstrumentType", "نوع ابزار", FieldKind.Kind, true, "instrument_type",
                  choices: new[] { "BANK", "CHEQUE", "CREDIT_NOTE", "OTHER" }),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceAllocationCode",
            notes: "این قالب فقط سند پرداخت موجود را به فاکتور موجود وصل می‌کند؛ خودش تراکنش "
                 + "بانکی یا سند حسابداری جدید نمی‌سازد.");

        public static readonly ImportTemplate Partnership = new ImportTemplate(
            "PARTNERSHIP", "11_Partnership.xlsx", "عملیات شرکت",
            new[]
            {
                F("SourceRowCode", "کد ردیف منبع", FieldKind.Code, true, "source_key", maxLen: 60),
                F("DateShamsi", "تاریخ شمسی", FieldKind.Shamsi, true, "date_shamsi"),
                F("EventType", "نوع عملیات", FieldKind.Kind, true, "event_type",
                  choices: new[] { "PARTNER_IN", "CUSTODY_OUT", "COLDSTORE_TRANSFER" }),
                F("PartnerCode", "کد شریک", FieldKind.Code, true, "partner_party_id", lookup: "parties:code"),
                F("ProductCode", "کد محصول", FieldKind.Code, false, "product_id", lookup: "products:code"),
                F("BasketTypeCode", "کد نوع سبد", FieldKind.Code, false, "basket_id", lookup: "baskets:code"),
                F("WarehouseCode", "کد انبار", FieldKind.Code, false, "warehouse_id",
                  lookup: "warehouses:code"),
                F("GrossKg", "وزن ناخالص (kg)", FieldKind.Kg, false, "gross_grams"),
                F("ConsumedBaskets", "تعداد سبد مصرف‌شده", FieldKind.Count, false, "consumed_baskets"),
                F("CustodyReturnedBaskets", "تعداد سبد برگشتی امانی", FieldKind.Count, false,
                  "custody_returned_baskets"),
                F("LossPercent", "درصد افت (%)", FieldKind.Percent, false, "loss_percent"),
                F("ExtraWasteKg", "ضایعات اضافه (kg)", FieldKind.Kg, false, "extra_waste_grams"),
                F("PartnerSharePercent", "درصد سهم شریک (%)", FieldKind.Percent, false,
                  "partner_share_percent"),
                F("RoundingUnitKg", "واحد گردکردن (kg)", FieldKind.Kg, false, "rounding_unit_grams"),
                F("RoundingMode", "روش گردکردن", FieldKind.Kind, false, "rounding_mode",
                  choices: new[] { "NEAREST", "UP", "DOWN", "NONE" }),
                F("PurchaseAggregationCode", "کد تجمیع خرید", FieldKind.Code, false,
                  "purchase_aggregation_id", lookup: "purchase_aggregations:code"),
                F("ReceiptNumber", "شماره قبض", FieldKind.Code, false, "receipt_number", maxLen: 40),
                F("OriginPlace", "محل مبدأ", FieldKind.Text, false, "origin_place", maxLen: 120),
                F("DestinationPlace", "محل مقصد", FieldKind.Text, false, "destination_place", maxLen: 120),
                F("Note", "شرح", FieldKind.Text, false, "description", maxLen: 400),
            },
            idempotencyField: "SourceRowCode",
            notes: "تعداد سبد مصرف‌شده برای تار و تعداد سبد برگشتی امانی دو فیلد مستقل‌اند.");

        /// <summary>All templates by code.</summary>
        public static readonly IReadOnlyDictionary<string, ImportTemplate> All =
            new Dictionary<string, ImportTemplate>(StringComparer.Ordinal)
            {
                { Parties.Code, Parties },
                { Products.Code, Products },
                { WeighingIn.Code, WeighingIn },
                { PurchaseInvoices.Code, PurchaseInvoices },
                { SalesInvoices.Code, SalesInvoices },
                { Sorting.Code, Sorting },
                { BasketMovements.Code, BasketMovements },
                { BankTransactions.Code, BankTransactions },
                { Cheques.Code, Cheques },
                { Settlements.Code, Settlements },
                { Partnership.Code, Partnership },
            };

        /// <summary>
        /// Import order. Later files reference codes created by earlier ones,
        /// so this order is a hard requirement, not a preference.
        /// </summary>
        public static readonly IReadOnlyList<string> ImportOrder = new[]
        {
            "PARTIES", "PRODUCTS", "WEIGHING_IN", "PURCHASE_INVOICES", "SALES_INVOICES",
            "SORTING", "BASKET_MOVEMENTS", "BANK_TRANSACTIONS", "CHEQUES",
            "SETTLEMENTS", "PARTNERSHIP",
        };

        public static readonly IReadOnlyList<string> DataSheetNames =
            new[] { "داده‌ها", "داده ها", "Data", "data" };

        public static readonly IReadOnlyList<string> GuideSheetNames =
            new[] { "راهنما", "راهنما ۱", "Guide", "guide" };

        public static readonly IReadOnlyList<string> DictionarySheetNames =
            new[] { "فرهنگ داده", "فرهنگ داده‌ها", "Data Dictionary", "Dictionary" };
    }
}
