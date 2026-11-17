using System;

namespace Mazandasht.Domain
{
    /// <summary>
    /// Money is stored as integer Rial (Spec ch. 2.1). Toman is display-only:
    /// Toman = Rial / 10. Display conversion never mutates stored amounts.
    /// Internal calculations keep full precision; only the final amount is
    /// rounded to the nearest Rial.
    /// </summary>
    public readonly struct Money : IEquatable<Money>
    {
        public long Rial { get; }

        public Money(long rial)
        {
            Rial = rial;
        }

        public static Money Zero => new Money(0);

        public static Money FromRial(long rial) => new Money(rial);

        /// <summary>Exact conversion: 1 Toman = 10 Rial. No floating point.</summary>
        public static Money FromToman(long toman)
        {
            checked { return new Money(toman * 10L); }
        }

        /// <summary>Display value in Toman (may be fractional for display only).</summary>
        public decimal ToTomanDecimal() => Rial / 10m;

        /// <summary>Display value in Toman rounded to whole Toman (display only).</summary>
        public long ToTomanRounded() => (long)Math.Round(Rial / 10m, MidpointRounding.AwayFromZero);

        public static Money operator +(Money a, Money b) => new Money(a.Rial + b.Rial);
        public static Money operator -(Money a, Money b) => new Money(a.Rial - b.Rial);
        public static Money operator -(Money a) => new Money(-a.Rial);

        /// <summary>
        /// Apply a rounding mode to a multiple of <paramref name="unitRial"/>.
        /// The result is always an integer Rial amount.
        /// </summary>
        public Money Round(RoundingMode mode, long unitRial)
        {
            if (unitRial <= 0) throw new ArgumentOutOfRangeException(nameof(unitRial));
            switch (mode)
            {
                case RoundingMode.None:
                    return this;
                case RoundingMode.Nearest:
                    return new Money((long)Math.Round(Rial / (decimal)unitRial, MidpointRounding.AwayFromZero) * unitRial);
                case RoundingMode.Up:
                    return new Money((long)Math.Ceiling(Rial / (decimal)unitRial) * unitRial);
                case RoundingMode.Down:
                    return new Money((long)Math.Floor(Rial / (decimal)unitRial) * unitRial);
                default:
                    throw new ArgumentOutOfRangeException(nameof(mode));
            }
        }

        public bool Equals(Money other) => Rial == other.Rial;
        public override bool Equals(object obj) => obj is Money m && Equals(m);
        public override int GetHashCode() => Rial.GetHashCode();
        public override string ToString() => Rial + " Rial";
    }
}
