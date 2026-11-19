using Mazandasht.Domain;
using Xunit;

namespace Mazandasht.Tests
{
    public class MoneyTests
    {
        [Fact]
        public void TomanConversion_IsExact10To1()
        {
            var m = Money.FromToman(100);
            Assert.Equal(1000, m.Rial);
            Assert.Equal(100m, m.ToTomanDecimal());
        }

        [Fact]
        public void DisplayConversion_DoesNotMutateStoredAmount()
        {
            var m = Money.FromRial(1005);
            var display = m.ToTomanRounded(); // 101 (display only)
            Assert.Equal(101, display);
            Assert.Equal(1005, m.Rial); // stored value unchanged
        }

        [Theory]
        [InlineData(RoundingMode.None, 1005)]
        [InlineData(RoundingMode.Nearest, 1000)]
        [InlineData(RoundingMode.Up, 1010)]
        [InlineData(RoundingMode.Down, 1000)]
        public void RoundingModes_WorkOnRialUnit(RoundingMode mode, long expected)
        {
            Assert.Equal(expected, Money.FromRial(1005).Round(mode, 10).Rial);
        }
    }
}
