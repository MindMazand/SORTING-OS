using System.Collections.Generic;

namespace Mazandasht.Presentation
{
    /// <summary>One dashboard KPI card. Values always come from the real
    /// database, split by approved vs under-review (Spec ch. 11).</summary>
    public sealed class KpiCard
    {
        public string Title { get; set; } = "";
        public string Value { get; set; } = "";
        public string Subtitle { get; set; } = "";
        public string AccentColor { get; set; } = "#075E1E";
    }

    /// <summary>
    /// Dashboard view model. KPI selection and time range are configurable
    /// (company_settings: dashboard.kpis / dashboard.range_days). No mock
    /// values are ever shown — empty state is explicit.
    /// </summary>
    public sealed class DashboardViewModel
    {
        public List<KpiCard> Cards { get; } = new List<KpiCard>();
        public string RangeLabel { get; set; } = "";
        public bool IsEmpty => Cards.Count == 0;
    }
}
