using Mazandasht.Domain;
using Xunit;

namespace Mazandasht.Tests
{
    public class SettlementTests
    {
        [Fact]
        public void InvoiceTotals_GrossMinusAdjustmentsEqualsNet()
        {
            var input = new InvoiceTotalsInput
            {
                Weight = Weight.FromGrams(10000), // 10 kg
                RateRialPerKg = Money.FromRial(50000),
                Discount = Money.FromRial(10000),
                Freight = Money.FromRial(5000),
                Commission = Money.FromRial(5000)
            };
            var totals = SettlementCalculator.Calculate(input, Money.FromRial(400000));
            Assert.Equal(500000, totals.Gross.Rial);
            Assert.Equal(480000, totals.Net.Rial);
            Assert.Equal(80000, totals.Balance.Rial);
        }

        [Fact]
        public void NoHardcodedRates_AllInputsComeFromCaller()
        {
            var input = new InvoiceTotalsInput
            {
                Weight = Weight.FromGrams(1000),
                RateRialPerKg = Money.FromRial(12345)
            };
            var totals = SettlementCalculator.Calculate(input, Money.Zero);
            Assert.Equal(12345, totals.Gross.Rial);
        }
    }
}
