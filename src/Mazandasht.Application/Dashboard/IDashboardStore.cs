using System.Collections.Generic;
using Mazandasht.Domain.Dashboard;

namespace Mazandasht.Application.Dashboard
{
    /// <summary>
    /// What the dashboard is allowed to ask the database.
    ///
    /// An interface, not a connection. The UI must never write SQL: a query
    /// that lives inside a XAML code-behind cannot be tested, and its numbers
    /// cannot be compared against the Python implementation that proved them
    /// (agents/A_dashboard_queries.py).
    /// </summary>
    public interface IDashboardStore
    {
        /// <summary>
        /// All nineteen KPIs of spec ch.11 for the last <paramref name="days"/>
        /// days, keyed by the stable English key (sales, purchase, …).
        ///
        /// An empty database returns nineteen zeroed KPIs, not an empty list.
        /// The UI's empty state depends on getting all nineteen back.
        /// </summary>
        IList<KpiValue> ComputeKpis(int days);

        /// <summary>Diagnostics only: proves which file the numbers came from.</summary>
        string DatabasePath { get; }
    }
}
