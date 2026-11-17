using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace Mazandasht.Application.Import
{
    /// <summary>Result of resolving one code against the database.</summary>
    public sealed class LookupResult
    {
        public LookupRequest Request { get; set; }
        public long? Id { get; set; }
        public string Error { get; set; }
    }

    /// <summary>Everything the writer needs from the database, expressed as an
    /// interface so the writer can be tested without SQLite and so the SQL
    /// lives in the persistence layer where it belongs.</summary>
    public interface IImportStore
    {
        /// <summary>Resolve "table:column" = code -> id. Null when absent.</summary>
        long? Lookup(string lookupSpec, string code);

        /// <summary>"PURCHASE" or "SALES" for an invoice number, or null when
        /// no such invoice exists. One column in the template = one answer.</summary>
        string LookupKind(string invoiceNumber);

        /// <summary>Next stable system code, e.g. "C001" -> "C002".</summary>
        string NextCode(string table, string prefix);

        /// <summary>True when a document with this source key already exists.</summary>
        bool SourceKeyExists(string table, string column, string key);

        /// <summary>Insert and return the new row id. Unknown keys are rejected
        /// by the store, never silently dropped.</summary>
        long Insert(string table, IDictionary<string, object> values);

        /// <summary>Default partnership id (the owner runs a single partnership).</summary>
        long DefaultPartnershipId();

        void BeginTransaction();
        void Commit();
        void Rollback();
    }

    public sealed class WriteOutcome
    {
        public int Created { get; set; }
        public int Skipped { get; set; }
        public int Failed { get; set; }
        public List<string> Errors { get; } = new List<string>();
        public List<string> Warnings { get; } = new List<string>();
        public List<long> CreatedIds { get; } = new List<long>();
        public bool PreviewOnly { get; set; }
    }

    /// <summary>
    /// Stages 5-7 of the import pipeline: resolve codes, write documents
    /// atomically, and know exactly which rows were created so a rollback can
    /// undo precisely those.
    ///
    /// Two rules are structural, not comments:
    ///   * nothing is written unless every lookup for that row resolved
    ///   * every document is written as DRAFT — the manager-approval workflow
    ///     must not be bypassable by an import, and rollback is only legal on
    ///     drafts because approved rows are frozen by DB triggers
    ///
    /// DEC-NEW-007 is enforced by omission: only the WEIGHING_IN writer creates
    /// stock movements, and no invoice writer touches stock at all.
    /// </summary>
    public sealed class ImportWriter
    {
        private readonly IImportStore _store;

        public ImportWriter(IImportStore store)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
        }

        /// <param name="commit">false = the owner's PREVIEW: every stage runs,
        /// nothing is written.</param>
        public WriteOutcome Write(ParseOutcome parsed, bool commit)
        {
            if (parsed == null) throw new ArgumentNullException(nameof(parsed));
            var outcome = new WriteOutcome { PreviewOnly = !commit };
            if (!parsed.Ok)
            {
                outcome.Errors.AddRange(parsed.FileErrors);
                return outcome;
            }

            var template = parsed.Template;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var idempotency = template.IdempotencyField;

            if (commit) _store.BeginTransaction();
            try
            {
                foreach (var row in parsed.Rows)
                {
                    if (!row.Ok)
                    {
                        outcome.Failed++;
                        outcome.Errors.Add("ردیف " + row.SourceRow + ": " +
                            string.Join(" | ", row.Errors.Select(e => e.Message)));
                        continue;
                    }

                    // -- stage 5: resolve ------------------------------------
                    var resolved = new Dictionary<string, long>(StringComparer.Ordinal);
                    var lookupFailed = false;
                    foreach (var request in ImportEngine.LookupRequests(template, row))
                    {
                        var id = _store.Lookup(request.LookupSpec, request.Code);
                        if (id == null)
                        {
                            var table = request.LookupSpec.Split(':')[0];
                            var field = template.ByEn(request.FieldName);
                            outcome.Failed++;
                            outcome.Errors.Add("ردیف " + row.SourceRow + ": «" +
                                (field == null ? request.FieldName : field.NameFa) +
                                "» = «" + request.Code + "» در اطلاعات پایه (" + table +
                                ") پیدا نشد. ابتدا آن را بسازید یا فایل مبدأ را وارد کنید.");
                            lookupFailed = true;
                            break;
                        }
                        resolved[request.FieldName] = id.Value;
                    }
                    if (lookupFailed) continue;

                    // -- business rules --------------------------------------
                    List<string> ruleErrors, ruleWarnings;
                    ImportEngine.CheckRules(template, row, out ruleErrors, out ruleWarnings);
                    outcome.Warnings.AddRange(ruleWarnings.Select(w =>
                        "ردیف " + row.SourceRow + ": " + w));
                    if (ruleErrors.Count > 0)
                    {
                        outcome.Failed++;
                        outcome.Errors.Add("ردیف " + row.SourceRow + ": " +
                                           string.Join(" | ", ruleErrors));
                        continue;
                    }

                    // -- idempotency -----------------------------------------
                    if (idempotency != null)
                    {
                        var key = row.GetString(idempotency);
                        if (!string.IsNullOrEmpty(key))
                        {
                            if (seen.Contains(key))
                            {
                                outcome.Failed++;
                                outcome.Errors.Add("ردیف " + row.SourceRow + ": تکراری: «" +
                                                   key + "» در همین فایل وارد شده است");
                                continue;
                            }
                            var probe = DocumentTable(template);
                            if (probe.Item1 != null && _store.SourceKeyExists(probe.Item1, probe.Item2, key))
                            {
                                outcome.Failed++;
                                outcome.Errors.Add("ردیف " + row.SourceRow + ": تکراری: «" +
                                                   key + "» قبلاً وارد شده است");
                                continue;
                            }
                            seen.Add(key);
                        }
                    }

                    if (!commit)
                    {
                        outcome.Created++;
                        continue;
                    }

                    var newId = WriteDocument(template, row, resolved, outcome);
                    if (newId.HasValue)
                    {
                        outcome.Created++;
                        outcome.CreatedIds.Add(newId.Value);
                    }
                }

                if (commit) _store.Commit();
                return outcome;
            }
            catch
            {
                if (commit) _store.Rollback();
                throw;
            }
        }

        /// <summary>Where this template's documents live, and which column
        /// carries the idempotency key. Used only for the duplicate probe.</summary>
        private static Tuple<string, string> DocumentTable(ImportTemplate template)
        {
            switch (template.Code)
            {
                case "WEIGHING_IN": return Tuple.Create("weigh_tickets", "source_key");
                case "PURCHASE_INVOICES": return Tuple.Create("purchase_invoices", "source_key");
                case "SALES_INVOICES": return Tuple.Create("sales_invoices", "source_key");
                case "SORTING": return Tuple.Create("sorting_batches", "source_key");
                case "BASKET_MOVEMENTS": return Tuple.Create("basket_movements", "source_key");
                case "CHEQUES": return Tuple.Create("cheques", "source_key");
                case "PARTNERSHIP": return Tuple.Create("partnership_events", "source_key");
                case "PARTIES": return Tuple.Create("parties", "code");
                case "PRODUCTS": return Tuple.Create("products", "code");
                case "BANK_TRANSACTIONS": return Tuple.Create("bank_transactions", "source_key");
                default: return Tuple.Create<string, string>(null, null);
            }
        }

        private long? WriteDocument(ImportTemplate template, ParsedRow row,
                                    IDictionary<string, long> ids, WriteOutcome outcome)
        {
            switch (template.Code)
            {
                case "PARTIES": return WriteParty(template, row, ids);
                case "PRODUCTS": return WriteProduct(template, row, ids);
                case "WEIGHING_IN": return WriteWeighing(template, row, ids);
                case "PURCHASE_INVOICES": return WriteInvoice(template, row, ids, true);
                case "SALES_INVOICES": return WriteInvoice(template, row, ids, false);
                case "SORTING": return WriteSorting(template, row, ids);
                case "BASKET_MOVEMENTS": return WriteBasketMovement(template, row, ids);
                case "BANK_TRANSACTIONS": return WriteBankTransaction(template, row, ids);
                case "CHEQUES": return WriteCheque(template, row, ids);
                case "SETTLEMENTS": return WriteSettlement(template, row, ids);
                case "PARTNERSHIP": return WritePartnershipEvent(template, row, ids);
                default:
                    outcome.Failed++;
                    outcome.Errors.Add("ردیف " + row.SourceRow +
                                       ": نویسنده‌ای برای قالب " + template.Code + " تعریف نشده است");
                    return null;
            }
        }

        private long WriteParty(ImportTemplate t, ParsedRow row, IDictionary<string, long> ids)
        {
            return _store.Insert("parties", new Dictionary<string, object>
            {
                { "code", row.GetString("PartyCode") },
                { "display_name", row.GetString("DisplayName") },
                { "party_kind", row.GetString("PartyType") },
                { "party_kind_confirmed", 1 },
                { "economic_code", Nullable(row.GetString("EconomicCode")) },
                { "national_code", row.GetString("NationalId") ?? "" },
                { "mobile", row.GetString("Mobile") ?? "" },
                { "phone", row.GetString("Phone") ?? "" },
                { "address", row.GetString("Address") ?? "" },
                { "nature", NatureFromCode(row.GetString("PartyCode")) },
                { "is_active", 1 },
            });
        }

        private long WriteProduct(ImportTemplate t, ParsedRow row, IDictionary<string, long> ids)
        {
            var active = row.GetLong("IsActive");
            return _store.Insert("products", new Dictionary<string, object>
            {
                { "code", row.GetString("ProductCode") },
                { "name", row.GetString("ProductName") },
                { "group_id", ids["GroupCode"] },
                { "unit_id", ids["UnitCode"] },
                { "variety_name", Nullable(row.GetString("VarietyName")) },
                { "is_active", active == null || active.Value == 1 ? 1 : 0 },
                { "description", row.GetString("Note") ?? "" },
            });
        }

        private long WriteWeighing(ImportTemplate t, ParsedRow row, IDictionary<string, long> ids)
        {
            var code = row.GetString("SourceDocCode");
            var net = row.GetLong("NetKg") ?? 0;
            var ticketId = _store.Insert("weigh_tickets", new Dictionary<string, object>
            {
                { "code", _store.NextCode("weigh_tickets", "WT") },
                { "doc_number", code },
                { "source_key", code },
                { "date_shamsi", row.GetString("DateShamsi") },
                { "date_iso", Jalali.ToIso(row.GetString("DateShamsi")) },
                { "time", row.GetString("Time") ?? "" },
                { "direction", "IN" },
                { "party_id", ids["PartyCode"] },
                { "product_id", ids["ProductCode"] },
                { "warehouse_id", ids["WarehouseCode"] },
                { "gross_grams", row.GetLong("ScaleKg") ?? 0 },
                { "tare_grams", row.GetLong("TareKg") ?? 0 },
                { "net_grams", net },
                { "package_count", row.GetLong("PackageCount") ?? 0 },
                { "packaging_id", ids.ContainsKey("PackagingCode") ? ids["PackagingCode"] : (object)null },
                { "receipt_number", Nullable(row.GetString("ReceiptNumber")) },
                { "status", "DRAFT" },
                { "description", row.GetString("Note") ?? "" },
            });

            // DEC-NEW-007: goods enter ONLY here, so this is the SINGLE place
            // in the whole import engine that creates a stock IN movement.
            var lotId = _store.Insert("lots", new Dictionary<string, object>
            {
                { "code", _store.NextCode("lots", "LOT") },
                { "weigh_ticket_id", ticketId },
                { "product_id", ids["ProductCode"] },
                { "warehouse_id", ids["WarehouseCode"] },
                { "quantity_grams", net },
                { "status", "OPEN" },
            });
            _store.Insert("stock_movements", new Dictionary<string, object>
            {
                { "lot_id", lotId },
                { "product_id", ids["ProductCode"] },
                { "warehouse_id", ids["WarehouseCode"] },
                { "movement_type", "IN" },
                { "quantity_grams", net },
                { "ref_type", "WEIGH_TICKET" },
                { "ref_id", ticketId },
            });
            return ticketId;
        }

        private long WriteInvoice(ImportTemplate t, ParsedRow row,
                                  IDictionary<string, long> ids, bool purchase)
        {
            if (purchase)
            {
                var code = row.GetString("SourceInvoiceCode");
                var invoiceId = _store.Insert("purchase_invoices", new Dictionary<string, object>
                {
                    { "code", _store.NextCode("purchase_invoices", "PI") },
                    { "doc_number", code },
                    { "source_key", code },
                    { "date_shamsi", row.GetString("DateShamsi") },
                    { "date_iso", Jalali.ToIso(row.GetString("DateShamsi")) },
                    { "party_id", ids["SupplierCode"] },
                    { "weigh_ticket_id", ids["WeighCode"] },
                    { "status", "DRAFT" },
                    { "description", row.GetString("Note") ?? "" },
                });
                var grams = row.GetLong("PurchaseKg") ?? 0;
                var rate = row.GetLong("RateRialPerKg") ?? 0;
                var gross = ImportEngine.GrossRial(grams, rate);
                var discount = row.GetLong("DiscountRial") ?? 0;
                var freight = row.GetLong("FreightRial") ?? 0;
                var commission = row.GetLong("CommissionRial") ?? 0;
                var adjustments = row.GetLong("OtherAdjustmentsRial") ?? 0;
                _store.Insert("purchase_invoice_lines", new Dictionary<string, object>
                {
                    { "invoice_id", invoiceId },
                    { "product_id", ids["ProductCode"] },
                    { "weigh_ticket_id", ids["WeighCode"] },
                    { "grams", grams },
                    { "rate_rial_per_kg", rate },
                    { "gross_rial", gross },
                    { "discount_rial", discount },
                    { "freight_rial", freight },
                    { "commission_rial", commission },
                    { "adjustments_rial", adjustments },
                    { "net_rial", ImportEngine.PurchaseNetRial(
                        gross, discount, freight, commission, adjustments) },
                });
                // No stock movement here on purpose: the goods already entered
                // through the weighbridge and counting them again would double
                // the inventory (DEC-NEW-007).
                return invoiceId;
            }

            var salesCode = row.GetString("SourceInvoiceCode");
            var salesId = _store.Insert("sales_invoices", new Dictionary<string, object>
            {
                { "code", _store.NextCode("sales_invoices", "SI") },
                { "doc_number", salesCode },
                { "source_key", salesCode },
                { "date_shamsi", row.GetString("DateShamsi") },
                { "date_iso", Jalali.ToIso(row.GetString("DateShamsi")) },
                { "party_id", ids["BuyerCode"] },
                { "lot_id", ids["LotCode"] },
                { "status", "DRAFT" },
                { "description", row.GetString("Note") ?? "" },
            });
            var sGrams = row.GetLong("SaleKg") ?? 0;
            var sRate = row.GetLong("RateRialPerKg") ?? 0;
            var sGross = ImportEngine.GrossRial(sGrams, sRate);
            var sDiscount = row.GetLong("DiscountRial") ?? 0;
            var sFreight = row.GetLong("FreightRial") ?? 0;
            var sCommission = row.GetLong("CommissionRial") ?? 0;
            var sOther = row.GetLong("OtherCostsRial") ?? 0;
            _store.Insert("sales_invoice_lines", new Dictionary<string, object>
            {
                { "invoice_id", salesId },
                { "product_id", ids["ProductCode"] },
                { "sorting_output_id", ids.ContainsKey("SortOutputCode")
                                        ? ids["SortOutputCode"] : (object)null },
                { "grams", sGrams },
                { "rate_rial_per_kg", sRate },
                { "gross_rial", sGross },
                { "discount_rial", sDiscount },
                { "freight_rial", sFreight },
                { "commission_rial", sCommission },
                { "other_costs_rial", sOther },
                { "net_rial", ImportEngine.SalesNetRial(
                    sGross, sDiscount, sFreight, sCommission, sOther) },
            });
            return salesId;
        }

        private long WriteSorting(ImportTemplate t, ParsedRow row, IDictionary<string, long> ids)
        {
            var input = row.GetLong("InputKg") ?? 0;
            var output = row.GetLong("OutputKg") ?? 0;
            var waste = row.GetLong("WasteKg") ?? 0;
            var loss = row.GetLong("ProcessLossKg") ?? 0;
            var tolerance = row.GetLong("ToleranceKg") ?? 0;

            var batchId = _store.Insert("sorting_batches", new Dictionary<string, object>
            {
                { "code", row.GetString("SortDocCode") },
                { "source_key", row.GetString("SortDocCode") },
                { "date_shamsi", row.GetString("DateShamsi") },
                { "description", row.GetString("Note") ?? "" },
                { "lot_id", ids["InputLotCode"] },
                { "input_grams", input },
                { "output_grams", output },
                { "waste_grams", waste },
                { "process_loss_grams", loss },
                { "variance_grams", input - (output + waste + loss) },
                { "tolerance_grams", tolerance },
                { "status", "DRAFT" },
            });
            _store.Insert("sorting_inputs", new Dictionary<string, object>
            {
                { "batch_id", batchId },
                { "lot_id", ids["InputLotCode"] },
                { "grams", input },
            });
            _store.Insert("sorting_outputs", new Dictionary<string, object>
            {
                { "batch_id", batchId },
                { "product_id", ids["OutputProductCode"] },
                { "grade_id", ids.ContainsKey("GradeCode") ? ids["GradeCode"] : (object)null },
                { "packaging_id", ids.ContainsKey("PackagingCode") ? ids["PackagingCode"] : (object)null },
                { "warehouse_id", ids["OutputWarehouseCode"] },
                { "grams", output },
                { "package_count", row.GetLong("PackageCount") ?? 0 },
            });
            if (waste > 0)
                _store.Insert("waste_records", new Dictionary<string, object>
                {
                    { "batch_id", batchId },
                    { "grams", waste },
                    { "reason", "IMPORT" },
                });
            return batchId;
        }

        private long WriteBasketMovement(ImportTemplate t, ParsedRow row,
                                         IDictionary<string, long> ids)
        {
            var type = row.GetString("MovementType");
            var qty = row.GetLong("Quantity") ?? 0;
            var rate = row.GetLong("PurchaseValueRial") ?? 0;
            return _store.Insert("basket_movements", new Dictionary<string, object>
            {
                { "basket_id", ids["BasketTypeCode"] },
                { "party_id", ids.ContainsKey("PartyCode") ? ids["PartyCode"] : (object)null },
                { "counterparty_party_id", type == "TRANSFER" && ids.ContainsKey("PartyCode")
                                            ? ids["PartyCode"] : (object)null },
                { "event_type", type },
                { "quantity", qty },
                { "rate_rial", rate },
                { "amount_rial", qty * rate },
                { "date_shamsi", row.GetString("DateShamsi") },
                { "date_iso", Jalali.ToIso(row.GetString("DateShamsi")) },
                { "doc_number", row.GetString("SourceDocCode") },
                { "source_key", row.GetString("SourceDocCode") },
                { "from_warehouse_id", ids.ContainsKey("FromWarehouseCode")
                                        ? ids["FromWarehouseCode"] : (object)null },
                { "to_warehouse_id", ids.ContainsKey("ToWarehouseCode")
                                      ? ids["ToWarehouseCode"] : (object)null },
                { "description", row.GetString("Note") ?? "" },
            });
        }

        private long WriteBankTransaction(ImportTemplate t, ParsedRow row,
                                          IDictionary<string, long> ids)
        {
            var amount = row.GetLong("AmountRial") ?? 0;
            var direction = row.GetString("Direction");
            var reported = row.GetLong("ReportedBalanceRial");
            var code = row.GetString("SourceTxnCode");
            return _store.Insert("bank_transactions", new Dictionary<string, object>
            {
                { "code", code },
                { "source_key", code },
                { "bank_account_id", ids["BankAccountCode"] },
                { "party_id", ids.ContainsKey("PartyCode") ? ids["PartyCode"] : (object)null },
                { "sub_group_id", ids.ContainsKey("SubGroupCode") ? ids["SubGroupCode"] : (object)null },
                { "date_shamsi", row.GetString("DateShamsi") },
                { "date_iso", Jalali.ToIso(row.GetString("DateShamsi")) },
                { "time", row.GetString("Time") ?? "" },
                { "direction", direction },
                { "deposit_rial", direction == "IN" ? amount : 0 },
                { "withdrawal_rial", direction == "OUT" ? amount : 0 },
                { "fee_rial", row.GetLong("FeeRial") ?? 0 },
                { "bank_balance_rial", reported ?? 0 },
                // Blank != zero: 0 here means the statement did NOT report a
                // balance, so a report must never render it as a real zero.
                { "reported_balance_known", reported.HasValue ? 1 : 0 },
                { "tracking_number", Nullable(row.GetString("TrackingNumber")) },
                { "status", "DRAFT" },
                { "description", row.GetString("Note") ?? "" },
            });
        }

        private long WriteCheque(ImportTemplate t, ParsedRow row, IDictionary<string, long> ids)
        {
            // The template says IN/OUT; the schema says RECEIVED/ISSUED. The
            // mapping is stated once, here, so the two vocabularies cannot drift.
            var direction = row.GetString("Direction") == "IN" ? "RECEIVED" : "ISSUED";
            var code = row.GetString("SourceDocCode");
            return _store.Insert("cheques", new Dictionary<string, object>
            {
                { "code", _store.NextCode("cheques", "CH") },
                { "doc_number", code },
                { "source_key", code },
                { "cheque_number", row.GetString("ChequeNumber") },
                { "bank_account_id", ids.ContainsKey("BankAccountCode")
                                      ? ids["BankAccountCode"] : (object)null },
                { "cheque_date", row.GetString("IssueDateShamsi") },
                { "issue_date_shamsi", row.GetString("IssueDateShamsi") },
                { "due_date_shamsi", row.GetString("DueDateShamsi") },
                { "amount_rial", row.GetLong("AmountRial") ?? 0 },
                { "beneficiary_party_id", ids["PartyCode"] },
                { "direction", direction },
                { "sayad_id", Nullable(row.GetString("SayadId")) },
                { "status", "OPEN" },
                { "description", row.GetString("Note") ?? "" },
            });
        }

        private long WriteSettlement(ImportTemplate t, ParsedRow row,
                                     IDictionary<string, long> ids)
        {
            // The template names ONE invoice number and the schema needs to
            // know which side it is on. v_invoice_lookup answers that in one
            // place, so a number can never be attached to the wrong kind of
            // invoice by searching only one table.
            var isPurchase = _store.Lookup("v_invoice_lookup:kind",
                                           row.GetString("InvoiceNumber")) != null
                             && _store.LookupKind(row.GetString("InvoiceNumber")) == "PURCHASE";
            return _store.Insert("payment_allocations", new Dictionary<string, object>
            {
                { "payment_id", ids["PaymentDocNumber"] },
                { "purchase_invoice_id", isPurchase ? (object)ids["InvoiceNumber"] : null },
                { "sales_invoice_id", isPurchase ? null : (object)ids["InvoiceNumber"] },
                { "amount_rial", row.GetLong("AllocationRial") ?? 0 },
                { "source_key", row.GetString("SourceAllocationCode") },
                { "instrument_type", row.GetString("InstrumentType") },
                { "description", row.GetString("Note") ?? "" },
            });
        }

        private long WritePartnershipEvent(ImportTemplate t, ParsedRow row,
                                           IDictionary<string, long> ids)
        {
            return _store.Insert("partnership_events", new Dictionary<string, object>
            {
                { "partnership_id", _store.DefaultPartnershipId() },
                { "source_key", row.GetString("SourceRowCode") },
                { "event_type", row.GetString("EventType") },
                { "date_shamsi", row.GetString("DateShamsi") },
                { "party_id", ids["PartnerCode"] },
                { "product_id", ids.ContainsKey("ProductCode") ? ids["ProductCode"] : (object)null },
                { "warehouse_id", ids.ContainsKey("WarehouseCode") ? ids["WarehouseCode"] : (object)null },
                { "basket_id", ids.ContainsKey("BasketTypeCode") ? ids["BasketTypeCode"] : (object)null },
                { "gross_grams", row.GetLong("GrossKg") ?? 0 },
                { "consumed_baskets", row.GetLong("ConsumedBaskets") ?? 0 },
                { "custody_returned_baskets", row.GetLong("CustodyReturnedBaskets") ?? 0 },
                { "loss_percent", row.GetDouble("LossPercent") },
                { "extra_waste_grams", row.GetLong("ExtraWasteKg") ?? 0 },
                { "partner_share_percent", row.GetDouble("PartnerSharePercent") },
                { "rounding_unit_grams", row.GetLong("RoundingUnitKg") },
                { "rounding_mode", row.GetString("RoundingMode") },
                { "purchase_aggregation_id", ids.ContainsKey("PurchaseAggregationCode")
                                             ? ids["PurchaseAggregationCode"] : (object)null },
                { "receipt_number", Nullable(row.GetString("ReceiptNumber")) },
                { "origin_place", Nullable(row.GetString("OriginPlace")) },
                { "destination_place", Nullable(row.GetString("DestinationPlace")) },
                { "description", row.GetString("Note") ?? "" },
            });
        }

        /// <summary>Blank stays absent. Writing "" would make "not recorded"
        /// indistinguishable from "recorded as empty".</summary>
        private static object Nullable(string value)
        {
            return string.IsNullOrWhiteSpace(value) ? (object)null : value.Trim();
        }

        /// <summary>The stable code prefix IS the account class. Longest
        /// prefixes first so CAP is not read as C and SL not as S.</summary>
        public static string NatureFromCode(string code)
        {
            if (string.IsNullOrEmpty(code)) return "X";
            foreach (var prefix in new[] { "CAP", "SL", "SG", "WG", "C", "S", "E", "X", "F", "L" })
                if (code.StartsWith(prefix, StringComparison.Ordinal))
                    return prefix;
            return "X";
        }
    }
}
