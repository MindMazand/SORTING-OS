using Mazandasht.Domain;
using Xunit;

namespace Mazandasht.Tests
{
    public class MassBalanceTests
    {
        [Fact]
        public void BalancedBatch_HasZeroVariance()
        {
            var r = MassBalance.Check(
                Weight.FromGrams(10000), Weight.FromGrams(9000),
                Weight.FromGrams(500), Weight.FromGrams(300), Weight.FromGrams(100));
            Assert.Equal(200, r.Variance.Grams);
            Assert.True(r.NeedsReview); // 200 > tolerance 100
        }

        [Fact]
        public void WithinTolerance_DoesNotNeedReview()
        {
            var r = MassBalance.Check(
                Weight.FromGrams(10000), Weight.FromGrams(9900),
                Weight.FromGrams(50), Weight.FromGrams(50), Weight.FromGrams(100));
            Assert.Equal(0, r.Variance.Grams);
            Assert.False(r.NeedsReview);
        }
    }
}
