namespace Mazandasht.Domain
{
    /// <summary>Result of a sorting mass-balance check (Spec ch. 8).</summary>
    public sealed class MassBalanceResult
    {
        public Weight Input { get; set; }
        public Weight Outputs { get; set; }
        public Weight Waste { get; set; }
        public Weight ProcessLoss { get; set; }
        public Weight Variance { get; set; }
        public Weight Tolerance { get; set; }
        public bool WithinTolerance => Variance.Grams >= -Tolerance.Grams && Variance.Grams <= Tolerance.Grams;
        /// <summary>True when the batch must stay in REVIEW for investigation.</summary>
        public bool NeedsReview => !WithinTolerance;
    }

    /// <summary>
    /// Sorting control formula: Input = Outputs + Waste + ProcessLoss + Variance.
    /// If |Variance| exceeds tolerance, the document stays under review.
    /// </summary>
    public static class MassBalance
    {
        public static MassBalanceResult Check(Weight input, Weight outputs, Weight waste,
                                              Weight processLoss, Weight tolerance)
        {
            var variance = input - outputs - waste - processLoss;
            return new MassBalanceResult
            {
                Input = input,
                Outputs = outputs,
                Waste = waste,
                ProcessLoss = processLoss,
                Variance = variance,
                Tolerance = tolerance
            };
        }
    }
}
