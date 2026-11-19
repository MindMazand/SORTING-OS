using System.Collections.Generic;
using Mazandasht.Domain;

namespace Mazandasht.Application
{
    /// <summary>
    /// Sorting batch balance (Spec ch. 8). A batch whose variance exceeds the
    /// configured tolerance stays in REVIEW; it cannot be approved until the
    /// difference is explained.
    /// </summary>
    public static class SortingService
    {
        public static MassBalanceResult Evaluate(Weight input, IReadOnlyList<Weight> outputs,
                                                 Weight waste, Weight processLoss, Weight tolerance)
        {
            var totalOut = Weight.Zero;
            foreach (var o in outputs) totalOut += o;
            return MassBalance.Check(input, totalOut, waste, processLoss, tolerance);
        }

        /// <summary>
        /// A batch may be submitted for approval only when its variance is
        /// within tolerance. Approval itself is always a manager action.
        /// </summary>
        public static bool CanSubmitForApproval(MassBalanceResult result)
        {
            return result != null && !result.NeedsReview;
        }
    }
}
