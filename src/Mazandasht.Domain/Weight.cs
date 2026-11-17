using System;
using System.Globalization;

namespace Mazandasht.Domain
{
    /// <summary>
    /// Weight base unit is integer grams (Spec ch. 2.1). Raw input (e.g. kg
    /// text with up to 3 decimals) is kept traceable alongside the
    /// standardized grams value. Rounding to 2 decimals in the core engine
    /// is forbidden; display rounding never reduces calculation precision.
    /// </summary>
    public readonly struct Weight : IEquatable<Weight>
    {
        public long Grams { get; }

        public Weight(long grams)
        {
            Grams = grams;
        }

        public static Weight Zero => new Weight(0);

        public static Weight FromGrams(long grams) => new Weight(grams);

        /// <summary>
        /// Parse kg input with at most <paramref name="maxDecimals"/> decimals
        /// (default 3 per current templates) into integer grams.
        /// </summary>
        public static Weight FromKgText(string text, int maxDecimals = 3)
        {
            if (string.IsNullOrWhiteSpace(text))
                throw new FormatException("Weight input is empty.");
            var t = text.Trim().Replace(',', '.');
            var dot = t.IndexOf('.');
            if (dot >= 0 && t.Length - dot - 1 > maxDecimals)
                throw new FormatException($"Weight allows at most {maxDecimals} decimals of kg: '{text}'.");
            if (!decimal.TryParse(t, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint,
                    CultureInfo.InvariantCulture, out var kg))
                throw new FormatException($"Invalid weight: '{text}'.");
            var grams = Math.Round(kg * 1000m, MidpointRounding.AwayFromZero);
            return new Weight((long)grams);
        }

        public decimal ToKgDecimal() => Grams / 1000m;

        public static Weight operator +(Weight a, Weight b) => new Weight(a.Grams + b.Grams);
        public static Weight operator -(Weight a, Weight b) => new Weight(a.Grams - b.Grams);

        /// <summary>Apply a rounding mode to a multiple of <paramref name="unitGrams"/>.</summary>
        public Weight Round(RoundingMode mode, long unitGrams)
        {
            if (unitGrams <= 0) throw new ArgumentOutOfRangeException(nameof(unitGrams));
            switch (mode)
            {
                case RoundingMode.None:
                    return this;
                case RoundingMode.Nearest:
                    return new Weight((long)Math.Round(Grams / (decimal)unitGrams, MidpointRounding.AwayFromZero) * unitGrams);
                case RoundingMode.Up:
                    return new Weight((long)Math.Ceiling(Grams / (decimal)unitGrams) * unitGrams);
                case RoundingMode.Down:
                    return new Weight((long)Math.Floor(Grams / (decimal)unitGrams) * unitGrams);
                default:
                    throw new ArgumentOutOfRangeException(nameof(mode));
            }
        }

        public bool Equals(Weight other) => Grams == other.Grams;
        public override bool Equals(object obj) => obj is Weight w && Equals(w);
        public override int GetHashCode() => Grams.GetHashCode();
        public override string ToString() => Grams + " g";
    }
}
