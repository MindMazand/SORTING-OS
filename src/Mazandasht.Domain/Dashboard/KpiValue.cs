using System;
using System.Collections.Generic;

namespace Mazandasht.Domain.Dashboard
{
    /// <summary>
    /// One KPI as the dashboard is allowed to show it.
    ///
    /// Three numbers, not one. Spec ch.11 requires every KPI to be reported
    /// with approved and under-review split apart. A dashboard that shows only
    /// the total reports money the owner has not yet confirmed as earned.
    /// </summary>
    public sealed class KpiValue
    {
        /// <summary>Unit of <see cref="Approved"/>/<see cref="Review"/>/<see cref="Total"/>.</summary>
        public enum UnitKind { Rial, Grams, Count }

        public string Key { get; private set; }
        public string LabelFa { get; private set; }
        public UnitKind Unit { get; private set; }

        /// <summary>Confirmed documents only — the book of record.</summary>
        public decimal Approved { get; private set; }

        /// <summary>DRAFT and REVIEW documents. Excludes VOIDED entirely.</summary>
        public decimal Review { get; private set; }

        /// <summary>Approved + Review. What physically exists in the system.</summary>
        public decimal Total { get { return Approved + Review; } }

        public KpiValue(string key, string labelFa, UnitKind unit,
                        decimal approved, decimal review)
        {
            if (string.IsNullOrEmpty(key)) throw new ArgumentException("key", "key");
            Key = key;
            LabelFa = labelFa;
            Unit = unit;
            Approved = approved;
            Review = review;
        }

        /// <summary>
        /// True when nothing at all has been recorded. The UI shows an explicit
        /// empty state for this, never a zero that looks like a real figure.
        /// </summary>
        public bool IsEmpty { get { return Approved == 0m && Review == 0m; } }

        public bool HasPending { get { return Review != 0m; } }

        /// <summary>
        /// Rial formatted for a Persian dashboard: no decimals (the schema
        /// stores whole Rial), thousands separated, minus sign preserved.
        ///
        /// Deliberately does NOT convert to Toman. The schema is Rial
        /// end-to-end; a display-only conversion is how a number gets divided
        /// by ten twice and nobody notices for a month.
        /// </summary>
        public string FormatApproved()
        {
            return Format(Approved);
        }

        public string Format(UnitKind unit, decimal amount)
        {
            if (unit == UnitKind.Grams)
                return (amount / 1000m).ToString("N3", System.Globalization.CultureInfo.InvariantCulture) + " kg";
            if (unit == UnitKind.Count)
                return ((long)amount).ToString("N0", System.Globalization.CultureInfo.InvariantCulture);
            return ((long)amount).ToString("N0", System.Globalization.CultureInfo.InvariantCulture);
        }

        public string Format(decimal amount)
        {
            return Format(Unit, amount);
        }

        public string UnitLabelFa
        {
            get
            {
                if (Unit == UnitKind.Rial) return "ریال";
                if (Unit == UnitKind.Grams) return "گرم";
                return "عدد";
            }
        }
    }
}
