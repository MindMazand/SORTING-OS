namespace Mazandasht.Domain
{
    /// <summary>Document approval states (Spec ch. 10).</summary>
    public enum DocumentStatus
    {
        Draft = 0,    // پیش‌نویس
        Review = 1,   // ثبت‌شده و منتظر بررسی
        Approved = 2, // تأییدشده و قطعی
        Voided = 3    // ابطال‌شده با دلیل
    }

    /// <summary>
    /// Approval state machine. Approved documents are immutable; corrections
    /// happen through reversal/adjustment documents, never silent edits.
    /// </summary>
    public static class ApprovalWorkflow
    {
        public static bool CanTransition(DocumentStatus from, DocumentStatus to)
        {
            switch (from)
            {
                case DocumentStatus.Draft:
                    return to == DocumentStatus.Review || to == DocumentStatus.Voided;
                case DocumentStatus.Review:
                    return to == DocumentStatus.Approved || to == DocumentStatus.Voided || to == DocumentStatus.Draft;
                case DocumentStatus.Approved:
                    return to == DocumentStatus.Voided; // only via void with reason
                case DocumentStatus.Voided:
                    return false; // terminal
                default:
                    return false;
            }
        }

        public static bool IsImmutable(DocumentStatus status) => status == DocumentStatus.Approved;

        public static void EnsureTransition(DocumentStatus from, DocumentStatus to, string voidReason = null)
        {
            if (!CanTransition(from, to))
                throw new System.InvalidOperationException(
                    $"Transition {from} -> {to} is not allowed.");
            if (to == DocumentStatus.Voided && string.IsNullOrWhiteSpace(voidReason))
                throw new System.ArgumentException("Voiding requires a reason.", nameof(voidReason));
        }
    }
}
