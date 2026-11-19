namespace Mazandasht.Domain
{
    /// <summary>
    /// Rounding modes required by Spec ch. 2.1. Money and weight rounding
    /// settings are independent of each other.
    /// </summary>
    public enum RoundingMode
    {
        None = 0,     // بدون گردکردن
        Nearest = 1,  // نزدیک‌ترین مضرب واحد
        Up = 2,       // گردکردن رو به بالا
        Down = 3      // گردکردن رو به پایین
    }
}
