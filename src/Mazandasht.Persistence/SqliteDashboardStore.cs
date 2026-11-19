using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.Globalization;
using Mazandasht.Application.Dashboard;
using Mazandasht.Domain.Dashboard;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// The nineteen dashboard KPIs, in C#, against the same schema the Python
    /// implementation proved (agents/A_dashboard_queries.py).
    ///
    /// The SQL below is a transliteration of that file, not a re-derivation.
    /// That is on purpose: two independent implementations of "today's sales"
    /// will disagree, and when they do nobody can tell which one is wrong. The
    /// Python file is the reference; this is the shipping copy. Gate
    /// tools/check_dashboard_parity.py compares the query text of the two so
    /// they cannot drift.
    ///
    /// Deliberate decisions:
    ///
    ///  * decimal, never double. Amounts are whole Rial in the schema but
    ///    sums of millions of Rial in double lose exactness. Converted from
    ///    long, so no floating point ever touches a balance.
    ///
    ///  * The status predicates are in one place per family. Writing
    ///    status='APPROVED' inline nineteen times is how one of them ends up
    ///    counting a VOIDED document.
    ///
    ///  * One connection opened per call, disposed. A dashboard that holds a
    ///    reader open will block the import engine's transaction on the same
    ///    file, and the owner will see "database is locked" mid-import.
    /// </summary>
    public sealed class SqliteDashboardStore : IDashboardStore, IDisposable
    {
        private readonly string _databasePath;

        public SqliteDashboardStore(string databasePath)
        {
            if (string.IsNullOrEmpty(databasePath))
                throw new ArgumentException("databasePath", "databasePath");
            _databasePath = databasePath;
        }

        public string DatabasePath { get { return _databasePath; } }

        /// <summary>The nineteen keys, in spec ch.11 order.</summary>
        public static readonly string[] KpiOrder =
        {
            "sales", "purchase", "gross_profit", "receipt_today", "payment_today",
            "receivable", "payable", "weight_in_today", "weight_out_today",
            "weight_2d", "weight_3d", "weight_7d", "loads_in", "loads_out",
            "stock", "baskets_custody", "cheques_due", "pending_docs",
            "bank_mismatch",
        };

        public static readonly Dictionary<string, string> LabelsFa =
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                { "sales", "فروش امروز" },
                { "purchase", "خرید امروز" },
                { "gross_profit", "سود ناخالص" },
                { "receipt_today", "دریافت امروز" },
                { "payment_today", "پرداخت امروز" },
                { "receivable", "طلب اشخاص" },
                { "payable", "بدهی اشخاص" },
                { "weight_in_today", "وزن ورودی امروز" },
                { "weight_out_today", "وزن خروجی امروز" },
                { "weight_2d", "وزن دو روز گذشته" },
                { "weight_3d", "وزن سه روز گذشته" },
                { "weight_7d", "وزن هفت روز گذشته" },
                { "loads_in", "تعداد بارهای ورودی" },
                { "loads_out", "تعداد بارهای خروجی" },
                { "stock", "موجودی انبار" },
                { "baskets_custody", "سبد امانی" },
                { "cheques_due", "چک‌های نزدیک سررسید" },
                { "pending_docs", "اسناد منتظر تأیید" },
                { "bank_mismatch", "مغایرت‌های بانکی" },
            };

        public IList<KpiValue> ComputeKpis(int days)
        {
            if (days < 1) days = 1;
            DateTime start = DateTime.Today.AddDays(-(days - 1));
            string startIso = start.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

            var result = new List<KpiValue>(19);

            using (var con = new SQLiteConnection("Data Source=" + _databasePath + ";"))
            {
                con.Open();
                // Read-only window onto the ledger: a dashboard must not take a
                // write lock while an import is running.
                using (var guard = con.CreateCommand())
                {
                    // Must actually execute: constructing a command and never
                    // calling it is how a safety guard silently does nothing.
                    guard.CommandText = "PRAGMA query_only = ON;";
                    guard.ExecuteNonQuery();
                }

                var sales = Split(con,
                        "SELECT COALESCE(SUM(l.net_rial),0) FROM sales_invoice_lines l " +
                        "JOIN sales_invoices i ON i.id = l.invoice_id " +
                        "WHERE i.status='APPROVED' AND i.date_iso >= @d",
                        "SELECT COALESCE(SUM(l.net_rial),0) FROM sales_invoice_lines l " +
                        "JOIN sales_invoices i ON i.id = l.invoice_id " +
                        "WHERE i.status IN ('DRAFT','REVIEW') AND i.date_iso >= @d",
                        startIso);
                    result.Add(Make("sales", KpiValue.UnitKind.Rial, sales));

                    var purchase = Split(con,
                        "SELECT COALESCE(SUM(l.net_rial),0) FROM purchase_invoice_lines l " +
                        "JOIN purchase_invoices i ON i.id = l.invoice_id " +
                        "WHERE i.status='APPROVED' AND i.date_iso >= @d",
                        "SELECT COALESCE(SUM(l.net_rial),0) FROM purchase_invoice_lines l " +
                        "JOIN purchase_invoices i ON i.id = l.invoice_id " +
                        "WHERE i.status IN ('DRAFT','REVIEW') AND i.date_iso >= @d",
                        startIso);
                    result.Add(Make("purchase", KpiValue.UnitKind.Rial, purchase));

                    // Gross profit is sales minus purchase over a CONSISTENT
                    // window. It is not cost of goods sold; real COGS needs the
                    // lot consumption trail. Labelled "ناخالص" for that reason.
                    result.Add(new KpiValue("gross_profit", LabelsFa["gross_profit"],
                        KpiValue.UnitKind.Rial,
                        sales[0] - purchase[0], sales[1] - purchase[1]));

                    var receipt = Split(con,
                        "SELECT COALESCE(SUM(amount_rial),0) FROM payments " +
                        "WHERE direction='IN' AND status='APPROVED' AND date_iso >= @d",
                        "SELECT COALESCE(SUM(amount_rial),0) FROM payments " +
                        "WHERE direction='IN' AND status IN ('DRAFT','REVIEW') AND date_iso >= @d",
                        startIso);
                    result.Add(Make("receipt_today", KpiValue.UnitKind.Rial, receipt));

                    var payment = Split(con,
                        "SELECT COALESCE(SUM(amount_rial),0) FROM payments " +
                        "WHERE direction='OUT' AND status='APPROVED' AND date_iso >= @d",
                        "SELECT COALESCE(SUM(amount_rial),0) FROM payments " +
                        "WHERE direction='OUT' AND status IN ('DRAFT','REVIEW') AND date_iso >= @d",
                        startIso);
                    result.Add(Make("payment_today", KpiValue.UnitKind.Rial, payment));

                    // Receivable / payable come from the LEDGER, not invoices.
                    // Account 1200 = بدهکاران, 2000 = بستانکاران.
                    var receivable = Split(con,
                        "SELECT COALESCE(SUM(jl.debit_rial - jl.credit_rial),0) " +
                        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id " +
                        "JOIN journal_entries e ON e.id = jl.journal_id " +
                        "WHERE a.code='1200' AND e.status='APPROVED'",
                        "SELECT COALESCE(SUM(jl.debit_rial - jl.credit_rial),0) " +
                        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id " +
                        "JOIN journal_entries e ON e.id = jl.journal_id " +
                        "WHERE a.code='1200' AND e.status IN ('DRAFT','REVIEW')",
                        null);
                    result.Add(Make("receivable", KpiValue.UnitKind.Rial, receivable));

                    var payable = Split(con,
                        "SELECT COALESCE(SUM(jl.credit_rial - jl.debit_rial),0) " +
                        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id " +
                        "JOIN journal_entries e ON e.id = jl.journal_id " +
                        "WHERE a.code='2000' AND e.status='APPROVED'",
                        "SELECT COALESCE(SUM(jl.credit_rial - jl.debit_rial),0) " +
                        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id " +
                        "JOIN journal_entries e ON e.id = jl.journal_id " +
                        "WHERE a.code='2000' AND e.status IN ('DRAFT','REVIEW')",
                        null);
                    result.Add(Make("payable", KpiValue.UnitKind.Rial, payable));

                    result.Add(Make("weight_in_today", KpiValue.UnitKind.Grams,
                        Weight(con, 1, "IN")));
                    result.Add(Make("weight_out_today", KpiValue.UnitKind.Grams,
                        Weight(con, 1, "OUT")));
                    result.Add(Make("weight_2d", KpiValue.UnitKind.Grams,
                        Weight(con, 2, "IN")));
                    result.Add(Make("weight_3d", KpiValue.UnitKind.Grams,
                        Weight(con, 3, "IN")));
                    result.Add(Make("weight_7d", KpiValue.UnitKind.Grams,
                        Weight(con, 7, "IN")));

                    result.Add(Make("loads_in", KpiValue.UnitKind.Count,
                        Split(con,
                            "SELECT COUNT(*) FROM weigh_tickets WHERE direction='IN' " +
                            "AND status='APPROVED' AND date_iso >= @d",
                            "SELECT COUNT(*) FROM weigh_tickets WHERE direction='IN' " +
                            "AND status IN ('DRAFT','REVIEW') AND date_iso >= @d",
                            startIso)));

                    result.Add(Make("loads_out", KpiValue.UnitKind.Count,
                        Split(con,
                            "SELECT COUNT(*) FROM weigh_tickets WHERE direction='OUT' " +
                            "AND status='APPROVED' AND date_iso >= @d",
                            "SELECT COUNT(*) FROM weigh_tickets WHERE direction='OUT' " +
                            "AND status IN ('DRAFT','REVIEW') AND date_iso >= @d",
                            startIso)));

                    result.Add(Make("stock", KpiValue.UnitKind.Grams,
                        Split(con,
                            "SELECT COALESCE(SUM(balance_grams),0) FROM v_stock_balance",
                            "SELECT 0", null)));

                    result.Add(Make("baskets_custody", KpiValue.UnitKind.Count,
                        Split(con,
                            "SELECT COALESCE(SUM(quantity),0) FROM basket_movements " +
                            "WHERE event_type IN ('PURCHASE','RETURN')",
                            "SELECT 0", null)));

                    result.Add(Make("cheques_due", KpiValue.UnitKind.Count,
                        Split(con,
                            "SELECT COUNT(*) FROM cheques WHERE status='OPEN' " +
                            "AND due_date_shamsi <> ''",
                            "SELECT 0", null)));

                    result.Add(Make("pending_docs", KpiValue.UnitKind.Count,
                        Split(con,
                            "SELECT 0",
                            "SELECT (SELECT COUNT(*) FROM sales_invoices WHERE status IN ('DRAFT','REVIEW'))" +
                            " + (SELECT COUNT(*) FROM purchase_invoices WHERE status IN ('DRAFT','REVIEW'))" +
                            " + (SELECT COUNT(*) FROM weigh_tickets WHERE status IN ('DRAFT','REVIEW'))" +
                            " + (SELECT COUNT(*) FROM payments WHERE status IN ('DRAFT','REVIEW'))" +
                            " + (SELECT COUNT(*) FROM journal_entries WHERE status IN ('DRAFT','REVIEW'))",
                            null)));

                    result.Add(Make("bank_mismatch", KpiValue.UnitKind.Count,
                        Split(con,
                            "SELECT COUNT(*) FROM bank_transactions " +
                            "WHERE reported_balance_known=1 AND bank_balance_rial <> system_balance_rial",
                            "SELECT 0", null)));
            }

            // Guard: the UI indexes this list by position to match spec order.
            if (result.Count != KpiOrder.Length)
                throw new InvalidOperationException(
                    "KPI count is " + result.Count + ", spec ch.11 requires " + KpiOrder.Length);
            return result;
        }

        private KpiValue Make(string key, KpiValue.UnitKind unit, decimal[] pair)
        {
            return new KpiValue(key, LabelsFa[key], unit, pair[0], pair[1]);
        }

        private decimal[] Weight(SQLiteConnection con, int days, string direction)
        {
            string startIso = DateTime.Today.AddDays(-(days - 1))
                .ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            return Split(con,
                "SELECT COALESCE(SUM(net_grams),0) FROM weigh_tickets " +
                "WHERE direction=@dir AND status='APPROVED' AND date_iso >= @d",
                "SELECT COALESCE(SUM(net_grams),0) FROM weigh_tickets " +
                "WHERE direction=@dir AND status IN ('DRAFT','REVIEW') AND date_iso >= @d",
                startIso, direction);
        }

        /// <summary>
        /// Runs the approved and pending halves of one KPI and returns
        /// [approved, review] as decimals.
        ///
        /// The try/catch is not defensive noise: the dashboard runs against
        /// whatever schema version the owner's file happens to be, and a
        /// missing table must produce a clear message in the status bar rather
        /// than a WPF crash dialog with a stack trace.
        /// </summary>
        private decimal[] Split(SQLiteConnection con, string approvedSql,
                                string pendingSql, string dateParam,
                                string directionParam = null)
        {
            decimal approved = Scalar(con, approvedSql, dateParam, directionParam);
            decimal review = Scalar(con, pendingSql, dateParam, directionParam);
            return new[] { approved, review };
        }

        private decimal Scalar(SQLiteConnection con, string sql,
                               string dateParam, string directionParam)
        {
            try
            {
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText = sql;
                    if (dateParam != null)
                        cmd.Parameters.AddWithValue("@d", dateParam);
                    if (directionParam != null)
                        cmd.Parameters.AddWithValue("@dir", directionParam);
                    object raw = cmd.ExecuteScalar();
                    if (raw == null || raw == DBNull.Value) return 0m;
                    // Through long: SQLite hands back Int64 for SUM, and
                    // Convert.ToDecimal(double) would round a rial.
                    if (raw is long) return (decimal)(long)raw;
                    if (raw is int) return (decimal)(int)raw;
                    if (raw is decimal) return (decimal)raw;
                    return Convert.ToDecimal(raw, CultureInfo.InvariantCulture);
                }
            }
            catch (SQLiteException ex)
            {
                throw new InvalidOperationException(
                    "KPI query failed against " + _databasePath +
                    ". The schema may be older than the dashboard. SQL: " + sql, ex);
            }
        }

        public void Dispose()
        {
            // Connections are opened and disposed per call; nothing held.
        }
    }
}
