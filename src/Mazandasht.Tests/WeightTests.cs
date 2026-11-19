using System;
using Mazandasht.Domain;
using Xunit;

namespace Mazandasht.Tests
{
    public class WeightTests
    {
        [Fact]
        public void KgText_ThreeDecimals_ConvertsToIntegerGrams()
        {
            Assert.Equal(10500, Weight.FromKgText("10.500").Grams);
            Assert.Equal(1500, Weight.FromKgText("1.5").Grams);
        }

        [Fact]
        public void KgText_MoreThanThreeDecimals_IsRejected()
        {
            Assert.Throws<FormatException>(() => Weight.FromKgText("1.2345"));
        }

        [Fact]
        public void NetWeight_IsGrossMinusTareMinusLoss()
        {
            var net = SettlementCalculator.NetWeight(
                Weight.FromGrams(10500), Weight.FromGrams(1500), Weight.FromGrams(100));
            Assert.Equal(8900, net.Grams);
        }

        [Fact]
        public void TareFromBaskets_MultipliesPerBasketTare()
        {
            var tare = SettlementCalculator.TareFromBaskets(4, Weight.FromGrams(1500));
            Assert.Equal(6000, tare.Grams);
        }

        [Fact]
        public void LossFromPercent_UsesIntegerGrams()
        {
            var loss = SettlementCalculator.LossFromPercent(Weight.FromGrams(10000), 1m);
            Assert.Equal(100, loss.Grams);
        }
    }
}
