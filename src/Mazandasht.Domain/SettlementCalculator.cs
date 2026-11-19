using System;

namespace Mazandasht.Domain
{
    /// <summary>
    /// Invoice/settlement totals (Spec ch. 7). All rates and adjustments are
    /// inputs from settings/reference data — nothing is hardcoded here.
    /// Money stays integer Rial; only the final amount is rounded to Rial.
    /// </summary>
    public sealed class InvoiceTotalsInput
    {
        public Weight Weight { get; set; }
        public Money RateRialPerKg { get; set; }
        public Money Discount { get; set; } = Money.Zero;
        public Money Freight { get; set; } = Money.Zero;
        public Money Commission { get; set; } = Money.Zero;
        public Money OtherAdjustments { get; set; } = Money.Zero;
    }

    public sealed class InvoiceTotals
    {
        public Money Gross { get; set; }
        public Money Net { get; set; }
        public Money Paid { get; set; }
        public Money Balance { get; set; } // Net - Paid
    }

    public static class SettlementCalculator
    {
        public static InvoiceTotals Calculate(InvoiceTotalsInput input, Money paid)
        {
            if (input == null) throw new ArgumentNullException(nameof(input));
            // Gross = weight(kg) * rate(rial/kg), full precision, round final to Rial.
            var grossRial = Math.Round(input.Weight.ToKgDecimal() * input.RateRialPerKg.Rial,
                                       MidpointRounding.AwayFromZero);
            var gross = new Money((long)grossRial);
            var net = gross - input.Discount - input.Freight - input.Commission - input.OtherAdjustments;
            return new InvoiceTotals
            {
                Gross = gross,
                Net = net,
                Paid = paid,
                Balance = net - paid
            };
        }

        /// <summary>
        /// Weigh-ticket net weight (Spec ch. 5.1):
        /// NetWeight = GrossWeight - TareWeight - LossWeight.
        /// Tare may come from basket count x per-basket tare.
        /// </summary>
        public static Weight NetWeight(Weight gross, Weight tare, Weight loss)
        {
            var net = gross - tare - loss;
            if (net.Grams < 0)
                throw new InvalidOperationException("Net weight cannot be negative.");
            return net;
        }

        public static Weight TareFromBaskets(int basketCount, Weight perBasketTare)
        {
            if (basketCount < 0) throw new ArgumentOutOfRangeException(nameof(basketCount));
            return new Weight(perBasketTare.Grams * basketCount);
        }

        /// <summary>Loss from a percentage (e.g. P02), integer grams.</summary>
        public static Weight LossFromPercent(Weight gross, decimal percent)
        {
            var grams = Math.Round(gross.Grams * percent / 100m, MidpointRounding.AwayFromZero);
            return new Weight((long)grams);
        }
    }
}
