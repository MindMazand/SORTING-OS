using System;
using Mazandasht.Domain;

namespace Mazandasht.Application
{
    /// <summary>
    /// Purchase/sales invoice totals (Spec ch. 7). The invoice never touches
    /// stock directly: goods effects come from weigh tickets / warehouse
    /// documents, so invoices cannot double-count inventory.
    /// </summary>
    public static class InvoiceService
    {
        public static InvoiceTotals Calculate(InvoiceTotalsInput input, Money paid)
        {
            return SettlementCalculator.Calculate(input, paid);
        }

        /// <summary>Settlement balance for a party: net minus paid.</summary>
        public static Money SettlementBalance(Money net, Money paid) => net - paid;
    }
}
