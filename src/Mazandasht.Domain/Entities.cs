namespace Mazandasht.Domain
{
    /// <summary>
    /// Core domain entities. Every document carries a stable internal id, an
    /// independent display number, an approval status and actor stamps
    /// (Spec ch. 3, 10). Money is integer Rial; weight is integer grams.
    /// </summary>

    public sealed class Party
    {
        public long Id { get; set; }
        public string Code { get; set; } = "";          // stable system code
        public string DisplayName { get; set; } = "";   // changeable, safe
        public string Nature { get; set; } = "";        // C/SL/S/E/X/F/L/CAP (account class)
        /// <summary>
        /// PERSON or COMPANY — the 01_Parties template's own vocabulary (G-01).
        /// Independent of Nature: a COMPANY can also be a supplier ('S').
        /// </summary>
        public string PartyKind { get; set; } = "";
        /// <summary>False while the migration backfill is unconfirmed by the owner.</summary>
        public bool PartyKindConfirmed { get; set; }
        public string EconomicCode { get; set; } = "";  // G-02, optional
        public string NationalCode { get; set; } = "";
        public string Phone { get; set; } = "";
        public string Mobile { get; set; } = "";
        public string Address { get; set; } = "";
        public bool IsActive { get; set; } = true;
    }

    public sealed class WeighTicket
    {
        public long Id { get; set; }
        public string Code { get; set; } = "";
        public string DocNumber { get; set; } = "";     // display number
        public string DateIso { get; set; } = "";
        public string DateShamsi { get; set; } = "";
        public string Time { get; set; } = "";
        public long? OperationId { get; set; }
        public string Direction { get; set; } = "IN";   // IN / OUT
        public long? PartyId { get; set; }
        public long? ProductId { get; set; }
        public string GrossKgRaw { get; set; } = "";    // raw input, traceable
        public Weight Gross { get; set; }
        public Weight Tare { get; set; }
        public Weight Loss { get; set; }
        public Weight Net { get; set; }
        public int BasketCount { get; set; }
        public long? BasketId { get; set; }
        public Money Amount { get; set; }
        public DocumentStatus Status { get; set; } = DocumentStatus.Draft;
        public string VoidReason { get; set; } = "";
        public string ParamSnapshot { get; set; } = ""; // effective params at registration
        public long? CreatedBy { get; set; }
        public long? ApprovedBy { get; set; }
        public string Description { get; set; } = "";
    }

    public sealed class StockMovement
    {
        public long Id { get; set; }
        public long? LotId { get; set; }
        public long? ProductId { get; set; }
        public long? GradeId { get; set; }
        public long? PackagingId { get; set; }
        public long? WarehouseId { get; set; }
        public string MovementType { get; set; } = "IN"; // IN / OUT / ADJUST
        public Weight Quantity { get; set; }
        public int QuantityCount { get; set; }
        public string RefType { get; set; } = "";
        public long? RefId { get; set; }
    }

    public sealed class JournalEntry
    {
        public long Id { get; set; }
        public string Code { get; set; } = "";
        public string DocNumber { get; set; } = "";
        public string DateIso { get; set; } = "";
        public string DateShamsi { get; set; } = "";
        public string Description { get; set; } = "";
        public DocumentStatus Status { get; set; } = DocumentStatus.Draft;
        public string VoidReason { get; set; } = "";
        public string SourceType { get; set; } = "";
        public long? SourceId { get; set; }
        public string SourceKey { get; set; } = "";     // idempotency key
        public long? CreatedBy { get; set; }
        public long? ApprovedBy { get; set; }
    }

    public sealed class BankTransaction
    {
        public long Id { get; set; }
        public string Code { get; set; } = "";
        public long BankAccountId { get; set; }
        public long? PartyId { get; set; }
        public long? TxnTypeId { get; set; }
        public Money Deposit { get; set; }
        public Money Withdrawal { get; set; }
        public Money BankBalance { get; set; }
        public Money SystemBalance { get; set; }
        public DocumentStatus Status { get; set; } = DocumentStatus.Draft;
        public string ChequeNumber { get; set; } = "";
        public string SourceKey { get; set; } = "";     // duplicate control
        public string Description { get; set; } = "";
    }
}
