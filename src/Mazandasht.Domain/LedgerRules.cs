using System;
using System.Collections.Generic;
using System.Linq;

namespace Mazandasht.Domain
{
    /// <summary>One journal line: debit XOR credit, integer Rial.</summary>
    public sealed class JournalLineInput
    {
        public long AccountId { get; set; }
        public Money Debit { get; set; }
        public Money Credit { get; set; }
        public string Description { get; set; } = "";
    }

    /// <summary>
    /// Double-entry rules (Spec ch. 9): an approved financial document has at
    /// least two lines and TotalDebit == TotalCredit. Posting is atomic and
    /// idempotent via a unique source key (enforced in the DB as well).
    /// </summary>
    public static class LedgerRules
    {
        public static void ValidateBalanced(IReadOnlyList<JournalLineInput> lines)
        {
            if (lines == null || lines.Count < 2)
                throw new InvalidOperationException("An approved journal entry needs at least two lines.");

            foreach (var l in lines)
            {
                if (l.Debit.Rial < 0 || l.Credit.Rial < 0)
                    throw new InvalidOperationException("Journal amounts cannot be negative.");
                if (l.Debit.Rial != 0 && l.Credit.Rial != 0)
                    throw new InvalidOperationException("A journal line is debit XOR credit.");
                if (l.Debit.Rial == 0 && l.Credit.Rial == 0)
                    throw new InvalidOperationException("A journal line cannot be zero on both sides.");
            }

            var debit = lines.Sum(l => l.Debit.Rial);
            var credit = lines.Sum(l => l.Credit.Rial);
            if (debit != credit)
                throw new InvalidOperationException(
                    $"Journal is unbalanced: debit {debit} != credit {credit}.");
        }

        public static bool IsBalanced(IReadOnlyList<JournalLineInput> lines)
        {
            if (lines == null || lines.Count < 2) return false;
            return lines.Sum(l => l.Debit.Rial) == lines.Sum(l => l.Credit.Rial);
        }
    }
}
