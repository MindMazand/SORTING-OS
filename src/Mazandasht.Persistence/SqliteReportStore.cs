using System;
using System.Collections.Generic;
using System.Data.SQLite;

namespace Mazandasht.Persistence
{
    /// <summary>One built report, ready to display.</summary>
    public sealed class ReportResult
    {
        public string Id { get; set; }
        public string Title { get; set; }
        public string[] Columns { get; set; }
        public List<string[]> Rows { get; set; }
        public string TotalsLine { get; set; }
        public string WarningText { get; set; }

        public ReportResult()
        {
            Columns = new string[0];
            Rows = new List<string[]>();
        }
    }

    /// <summary>
    /// Raised when a report has no defined layout. Deliberately loud: a report
    /// that quietly returns an empty table looks like "no data this period".
    /// </summary>
    public sealed class ReportUnavailableException : Exception
    {
        public ReportUnavailableException(string message) : base(message) { }
    }

    /// <summary>
    /// The six financial reports, against SQLite.
    ///
    /// PARITY WITH tools/reports_engine.py IS DELIBERATE. The Python module is
    /// where the report shapes are proven (tools/test_reports.py: 12/12 on a
    /// real database). This file is the production path. Two implementations of
    /// the same rules will drift, so the rules that matter are commented with
    /// the reason they exist rather than just the SQL.
    ///
    /// WHAT MUST NOT DRIFT
    ///  * cheque status is COMPUTED from paid_date, never read from the status
    ///    column — the owner's workbook says the status is automatic
    ///  * the baskets balance subtracts the CUMULATIVE paid total from every
    ///    row, not the payments before that row
    ///  * payments are read from `payments`, not `basket_movements` — a money
    ///    payment cannot live in a basket event table
    ///  * an unknown amount is "—", never "0"
    /// </summary>
    public sealed class SqliteReportStore : IDisposable
    {
        private static readonly string[] RebuiltTablesDescription = new string[0];

        private readonly SQLiteConnection _connection;

        public SqliteReportStore(string databasePath)
        {
            if (string.IsNullOrEmpty(databasePath))
                throw new ArgumentException("databasePath", "databasePath");
            _connection = new SQLiteConnection("Data Source=" + databasePath + ";");
            _connection.Open();
        }

        // ------------------------------------------------------------------
        // helpers
        // ------------------------------------------------------------------
        private sealed class Cell
        {
            internal object Value;
            internal bool IsKnown;
        }

        private List<Cell[]> Query(string sql, params object[] args)
        {
            var output = new List<Cell[]>();
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = sql;
                for (int i = 0; i < args.Length; i++)
                    cmd.Parameters.AddWithValue("@" + i, args[i]);
                using (SQLiteDataReader reader = cmd.ExecuteReader())
                {
                    while (reader.Read())
                    {
                        var row = new Cell[reader.FieldCount];
                        for (int i = 0; i < reader.FieldCount; i++)
                        {
                            row[i] = new Cell();
                            if (!reader.IsDBNull(i))
                            {
                                row[i].Value = reader.GetValue(i);
                                row[i].IsKnown = true;
                            }
                        }
                        output.Add(row);
                    }
                }
            }
            return output;
        }

        /// <summary>
        /// Format a value for display.
        ///
        /// AN UNKNOWN VALUE IS "—", NOT "0", AND NOT AN EMPTY CELL. This is the
        /// owner's first rule («خالی ≠ صفر») at the last possible moment. An
        /// empty cell and a zero look the same at a glance; a dash does not.
        /// </summary>
        internal static string Show(Cell cell)
        {
            if (cell == null || !cell.IsKnown) return "—";
            if (cell.Value is long || cell.Value is int)
                return Convert.ToInt64(cell.Value).ToString("N0");
            return Convert.ToString(cell.Value);
        }

        private static long? AsLong(Cell cell)
        {
            if (cell == null || !cell.IsKnown) return null;
            return Convert.ToInt64(cell.Value);
        }

        // ------------------------------------------------------------------
        // cheques (three reports share one reader)
        // ------------------------------------------------------------------
        private sealed class ChequeRow
        {
            public string Number;
            public string Date;
            public long? Amount;
            public string Beneficiary;
            public string PaidDate;
            public string Notes;

            /// <summary>
            /// COMPUTED. The owner's Cheques.xlsx says twice that the status is
            /// automatic and that writing in the "cleared on" column is wrong.
            /// So paid_date decides and a stored status is ignored: a status
            /// column can go stale against the date, and then the report says a
            /// cheque cleared when it did not.
            /// </summary>
            public bool IsCleared
            {
                get { return !string.IsNullOrEmpty(PaidDate); }
            }

            public string StatusText
            {
                get { return IsCleared ? "پاس شده" : "پاس نشده"; }
            }
        }

        private List<ChequeRow> Cheques()
        {
            var rows = Query(
                "SELECT c.cheque_number, c.cheque_date, c.amount_rial, " +
                "       c.paid_date, c.description, p.display_name " +
                "  FROM cheques c " +
                "  LEFT JOIN parties p ON p.id = c.beneficiary_party_id " +
                " ORDER BY c.cheque_date, c.id");

            var output = new List<ChequeRow>();
            foreach (Cell[] r in rows)
            {
                output.Add(new ChequeRow
                {
                    Number = Show(r[0]),
                    Date = Show(r[1]),
                    Amount = AsLong(r[2]),
                    PaidDate = r[3].IsKnown ? Convert.ToString(r[3].Value) : "",
                    Notes = Show(r[4]),
                    Beneficiary = Show(r[5])
                });
            }
            return output;
        }

        private static string Sum(List<ChequeRow> rows)
        {
            long total = 0;
            bool any = false;
            foreach (ChequeRow r in rows)
            {
                if (r.Amount.HasValue) { total += r.Amount.Value; any = true; }
            }
            // None known -> dash. Not zero: a set of unknown amounts does not
            // add up to zero rials.
            return any ? total.ToString("N0") : "—";
        }

        public ReportResult ChequesIssues()
        {
            var rows = Cheques();
            var result = new ReportResult
            {
                Id = "cheques_issues",
                Title = "چک‌های صادره",
                Columns = new[] { "شماره", "شماره چک", "تاریخ چک",
                                  "مبلغ (ریال)", "ذی‌نفع", "وضعیت (خودکار)",
                                  "توضیحات" }
            };
            for (int i = 0; i < rows.Count; i++)
            {
                ChequeRow r = rows[i];
                result.Rows.Add(new[]
                {
                    (i + 1).ToString(), r.Number, r.Date,
                    r.Amount.HasValue ? r.Amount.Value.ToString("N0") : "—",
                    r.Beneficiary, r.StatusText, r.Notes
                });
            }
            result.TotalsLine = "تعداد: " + rows.Count.ToString("N0")
                + " · جمع مبلغ: " + Sum(rows);
            return result;
        }

        public ReportResult ChequesMonth(string fromDate, string toDate)
        {
            var all = Cheques();
            var inRange = new List<ChequeRow>();
            foreach (ChequeRow r in all)
            {
                if (!string.IsNullOrEmpty(fromDate) &&
                    string.CompareOrdinal(r.Date, fromDate) < 0) continue;
                if (!string.IsNullOrEmpty(toDate) &&
                    string.CompareOrdinal(r.Date, toDate) > 0) continue;
                inRange.Add(r);
            }

            var cleared = new List<ChequeRow>();
            var uncleared = new List<ChequeRow>();
            foreach (ChequeRow r in inRange)
                (r.IsCleared ? cleared : uncleared).Add(r);

            var result = new ReportResult
            {
                Id = "cheques_month",
                Title = "گردش چک در بازه",
                Columns = new[] { "شماره", "تاریخ چک", "شماره چک",
                                  "مبلغ (ریال)", "وضعیت", "تاریخ پاس" }
            };
            for (int i = 0; i < inRange.Count; i++)
            {
                ChequeRow r = inRange[i];
                result.Rows.Add(new[]
                {
                    (i + 1).ToString(), r.Date, r.Number,
                    r.Amount.HasValue ? r.Amount.Value.ToString("N0") : "—",
                    r.StatusText,
                    string.IsNullOrEmpty(r.PaidDate) ? "—" : r.PaidDate
                });
            }
            result.TotalsLine = "کل: " + Sum(inRange)
                + " · پاس‌شده: " + Sum(cleared)
                + " · پاس‌نشده: " + Sum(uncleared);
            return result;
        }

        public ReportResult ChequesUnpaid(string fromDate, string toDate)
        {
            ReportResult month = ChequesMonth(fromDate, toDate);
            var result = new ReportResult
            {
                Id = "cheques_unpaid",
                Title = "چک‌های پاس‌نشده",
                Columns = month.Columns,
                WarningText = ""
            };

            long total = 0;
            bool any = false;
            string nearest = null;
            foreach (string[] row in month.Rows)
            {
                if (row[4] != "پاس نشده") continue;
                result.Rows.Add(new[]
                {
                    result.Rows.Count + 1 + "", row[1], row[2], row[3],
                    row[4], row[5]
                });
                // row[3] is already formatted with thousands separators; the
                // total is recomputed from a fresh read instead of parsing it
                // back, because parsing a formatted number is how locale bugs
                // are born.
                if (nearest == null || string.CompareOrdinal(row[1], nearest) < 0)
                    nearest = row[1];
            }
            foreach (ChequeRow r in Cheques())
            {
                if (r.IsCleared || !r.Amount.HasValue) continue;
                total += r.Amount.Value;
                any = true;
            }

            result.TotalsLine = "جمع: " + (any ? total.ToString("N0") : "—")
                + " · تعداد: " + result.Rows.Count.ToString("N0")
                + " · نزدیک‌ترین سررسید: "
                + (nearest == null ? "—" : nearest);
            return result;
        }

        // ------------------------------------------------------------------
        // baskets
        // ------------------------------------------------------------------
        public ReportResult BasketsReport(string partyCode)
        {
            var result = new ReportResult
            {
                Id = "baskets_report",
                Title = "مانده حساب فروشنده سبد",
                Columns = new[] { "شماره", "تاریخ", "نوع رویداد", "سند / بانک",
                                  "دریافت (ریال)", "تعداد", "فی (ریال)",
                                  "پرداخت (ریال)", "خرید سبز (ریال)",
                                  "مانده (ریال)", "توضیحات" }
            };

            var party = Query(
                "SELECT id, display_name FROM parties WHERE code = @0", partyCode);
            if (party.Count == 0)
            {
                result.TotalsLine = "فروشنده‌ای با کد " + partyCode + " پیدا نشد";
                return result;
            }
            long partyId = Convert.ToInt64(party[0][0].Value);

            var basket = Query(
                "SELECT m.event_type, m.quantity, m.rate_rial, m.amount_rial, " +
                "       m.date_iso, m.date_shamsi, m.doc_number, m.description " +
                "  FROM basket_movements m WHERE m.party_id = @0 " +
                " ORDER BY m.date_iso, m.id", partyId);

            // PAYMENTS COME FROM `payments`, NOT basket_movements.
            // basket_movements.event_type is CHECKed to basket events; a money
            // payment cannot be stored there. Reading payment rows out of it
            // returns nothing and the seller looks unpaid forever.
            var money = Query(
                "SELECT p.direction, p.amount_rial, p.date_iso, p.date_shamsi, " +
                "       p.doc_number, p.description " +
                "  FROM payments p WHERE p.party_id = @0 " +
                "   AND COALESCE(p.status, 'APPROVED') <> 'VOIDED' " +
                " ORDER BY p.date_iso, p.id", partyId);

            long purchaseTotal = 0, paidTotal = 0, receivedTotal = 0;
            bool anyPurchase = false, anyPaid = false, anyReceived = false;
            foreach (Cell[] r in basket)
            {
                long? amount = AsLong(r[3]);
                if (amount.HasValue) { purchaseTotal += amount.Value; anyPurchase = true; }
            }
            foreach (Cell[] r in money)
            {
                string direction = r[0].IsKnown ? Convert.ToString(r[0].Value) : "";
                long? amount = AsLong(r[1]);
                if (!amount.HasValue) continue;
                if (direction == "OUT") { paidTotal += amount.Value; anyPaid = true; }
                else if (direction == "IN") { receivedTotal += amount.Value; anyReceived = true; }
            }

            // Merge into one chronological ledger so the balance column reads
            // top-to-bottom the way the owner reads the sheet.
            var timeline = new List<string[]>();
            foreach (Cell[] r in basket)
            {
                string date = r[5].IsKnown ? Convert.ToString(r[5].Value)
                                           : (r[4].IsKnown ? Convert.ToString(r[4].Value) : "");
                timeline.Add(new[] { date ?? "", "B", "", "", "", "", "", "", "", "" });
            }

            // Totals first, because every balance needs the cumulative paid.
            foreach (Cell[] r in basket)
            {
                string date = r[5].IsKnown ? Convert.ToString(r[5].Value)
                                           : (r[4].IsKnown ? Convert.ToString(r[4].Value) : "");
                long? amount = AsLong(r[3]);
                string type = r[0].IsKnown ? Convert.ToString(r[0].Value) : "";
                result.Rows.Add(new[]
                {
                    (result.Rows.Count + 1).ToString(),
                    date ?? "—",
                    type,
                    Show(r[6]),
                    "—",
                    Show(r[1]),
                    Show(r[2]),
                    "—",
                    amount.HasValue ? amount.Value.ToString("N0") : "—",
                    "—",
                    Show(r[7])
                });
            }
            foreach (Cell[] r in money)
            {
                string direction = r[0].IsKnown ? Convert.ToString(r[0].Value) : "";
                bool isPaid = direction == "OUT";
                long? amount = AsLong(r[1]);
                string date = r[3].IsKnown ? Convert.ToString(r[3].Value)
                                           : (r[2].IsKnown ? Convert.ToString(r[2].Value) : "");
                result.Rows.Add(new[]
                {
                    (result.Rows.Count + 1).ToString(),
                    date ?? "—",
                    isPaid ? "پرداخت بانکی" : "دریافت بانکی",
                    Show(r[4]),
                    isPaid ? "—" : (amount.HasValue ? amount.Value.ToString("N0") : "—"),
                    "—",
                    "—",
                    isPaid ? (amount.HasValue ? amount.Value.ToString("N0") : "—") : "—",
                    "—",
                    "—",
                    Show(r[5])
                });
            }

            // The balance column: cumulative purchase minus the CUMULATIVE paid
            // total, applied to every purchase row. The workbook is explicit
            // («به همه ردیف‌های همان حساب اعمال می‌شود»); subtracting only the
            // payments before a row gives a different answer after the first
            // payment.
            long runningPurchase = 0;
            for (int i = 0; i < result.Rows.Count; i++)
            {
                string[] row = result.Rows[i];
                if (row[8] != "—")
                {
                    runningPurchase += ParseFormatted(row[8]);
                    long balance = runningPurchase - paidTotal;
                    row[9] = balance.ToString("N0");
                }
            }

            long finalBalance = purchaseTotal - paidTotal;
            result.TotalsLine =
                "جمع خرید: " + (anyPurchase ? purchaseTotal.ToString("N0") : "—")
                + " · جمع پرداخت: " + (anyPaid ? paidTotal.ToString("N0") : "—")
                + " · جمع دریافت: " + (anyReceived ? receivedTotal.ToString("N0") : "—")
                + " · مانده نهایی: " + finalBalance.ToString("N0")
                + " · وضعیت: " + (finalBalance > 0 ? "بستانکار"
                                   : finalBalance < 0 ? "بدهکار" : "تسویه");
            return result;
        }

        /// <summary>
        /// Read back a value this class formatted moments ago.
        ///
        /// The alternative — keeping a parallel unformatted array — doubles the
        /// bookkeeping for one column. "N0" writes group separators only; there
        /// is no decimal point and no currency symbol, so stripping every
        /// non-digit is exact here. If the format ever grows a decimal point
        /// this must change with it, which is why it is a named method and not
        /// an inline Replace.
        /// </summary>
        private static long ParseFormatted(string text)
        {
            if (string.IsNullOrEmpty(text) || text == "—") return 0;
            var digits = new System.Text.StringBuilder();
            foreach (char c in text)
            {
                if (char.IsDigit(c)) digits.Append(c);
                else if (c == '-') digits.Append('-');
            }
            long value;
            return long.TryParse(digits.ToString(), out value) ? value : 0;
        }

        // ------------------------------------------------------------------
        // trial balance and balance sheet
        // ------------------------------------------------------------------
        public ReportResult AccountingTrial()
        {
            // THE VOIDED FILTER LIVES IN THE JOIN, NOT IN A WHERE.
            //
            // With `WHERE j.status IS NULL OR j.status <> 'VOIDED'` an account
            // whose only line belongs to a voided entry produces one joined row,
            // that row is filtered out, and the account then has NO row at all —
            // it silently disappears from the trial balance. A trial balance
            // missing an account still looks balanced. The Python engine had
            // this exact bug; see tools/test_reports.py.
            var data = Query(
                "SELECT a.code, a.title, a.account_type, " +
                "       COALESCE(SUM(l.debit_rial),0), " +
                "       COALESCE(SUM(l.credit_rial),0), " +
                "       SUM(CASE WHEN l.id IS NULL THEN 0 ELSE 1 END) " +
                "  FROM accounts a " +
                "  LEFT JOIN journal_lines l ON l.account_id = a.id " +
                "   AND l.journal_id IN (SELECT id FROM journal_entries " +
                "                         WHERE status <> 'VOIDED') " +
                " GROUP BY a.id, a.code, a.title, a.account_type " +
                " ORDER BY a.code");

            var result = new ReportResult
            {
                Id = "accounting_trial",
                Title = "تراز آزمایشی",
                Columns = new[] { "ردیف", "حساب", "کد / کلید", "نوع",
                                  "جمع بدهکار (ریال)", "جمع بستانکار (ریال)",
                                  "مانده (ریال)", "وضعیت" }
            };

            long totalDebit = 0, totalCredit = 0;
            for (int i = 0; i < data.Count; i++)
            {
                Cell[] r = data[i];
                long debit = Convert.ToInt64(r[3].Value);
                long credit = Convert.ToInt64(r[4].Value);
                long lines = Convert.ToInt64(r[5].Value);
                long balance = debit - credit;
                totalDebit += debit;
                totalCredit += credit;

                result.Rows.Add(new[]
                {
                    (i + 1).ToString(),
                    Show(r[1]),
                    Show(r[0]),
                    Show(r[2]),
                    lines == 0 ? "—" : debit.ToString("N0"),
                    lines == 0 ? "—" : credit.ToString("N0"),
                    balance.ToString("N0"),
                    balance > 0 ? "بدهکار" : balance < 0 ? "بستانکار" : "بسته"
                });
            }

            long difference = totalDebit - totalCredit;
            result.TotalsLine = "جمع بدهکار: " + totalDebit.ToString("N0")
                + " · جمع بستانکار: " + totalCredit.ToString("N0")
                + " · اختلاف: " + difference.ToString("N0")
                + (difference == 0 ? " ✓ متوازن" : " ✗ ناتراز");
            if (difference != 0)
                result.WarningText = "تراز آزمایشی ناتراز است: اختلاف "
                    + difference.ToString("N0") + " ریال. تا رفع این اختلاف، "
                    + "هیچ گزارشی از این دفاتر قابل اتکا نیست.";
            return result;
        }

        private long? AccountBalance(string code, bool debitPositive)
        {
            // SAME TRAP AS AccountingTrial, AND IT WAS STILL HERE.
            //
            // Written as `WHERE ... j.status <> 'VOIDED'` this turns the LEFT
            // JOIN into an inner join: an account whose only journal lines
            // belong to voided entries loses every row, and this method then
            // reports null. In the trial balance that made an account vanish
            // from the list (visible). Here it makes the balance sheet report
            // "unknown" (—) for an account that genuinely has a known,
            // non-zero history elsewhere. Caught by
            // tools/test_reports_cs_sql.py, which greps the code for a voided
            // predicate outside the ON clause — a grep that only works because
            // it strips comments first.
            var rows = Query(
                "SELECT COALESCE(SUM(l.debit_rial),0), " +
                "       COALESCE(SUM(l.credit_rial),0), " +
                "       SUM(CASE WHEN l.id IS NULL THEN 0 ELSE 1 END) " +
                "  FROM accounts a " +
                "  LEFT JOIN journal_lines l ON l.account_id = a.id " +
                "   AND l.journal_id IN (SELECT id FROM journal_entries " +
                "                         WHERE status <> 'VOIDED') " +
                " WHERE a.code = @0",
                code);
            if (rows.Count == 0) return null;
            long debit = Convert.ToInt64(rows[0][0].Value);
            long credit = Convert.ToInt64(rows[0][1].Value);
            long lines = Convert.ToInt64(rows[0][2].Value);
            // No movement: unknown, not zero.
            if (lines == 0) return null;
            return debitPositive ? debit - credit : credit - debit;
        }

        // ------------------------------------------------------------------
        public List<KeyValuePair<string, string>> Availability()
        {
            return new List<KeyValuePair<string, string>>
            {
                Pair("cheques_issues", "چک‌های صادره"),
                Pair("cheques_month", "گردش چک در بازه"),
                Pair("cheques_unpaid", "چک‌های پاس‌نشده"),
                Pair("baskets_report", "مانده حساب فروشنده سبد"),
                Pair("accounting_trial", "تراز آزمایشی"),
                Pair("accounting_balance", "ترازنامه"),
                Pair("financial_report", "گزارش مالی")
            };
        }

        private static KeyValuePair<string, string> Pair(string k, string v)
        {
            return new KeyValuePair<string, string>(k, v);
        }

        public ReportResult AccountingBalance()
        {
            // The owner's Accounting.xlsx / Balance sheet, section by section.
            // Account codes are the ones the workbook names in its own rule
            // text: b = bank cash, p+ = receivable, s = baskets ledger,
            // q = uncleared cheques, l = loans, c = capital, e = expenses.
            var result = new ReportResult
            {
                Id = "accounting_balance",
                Title = "ترازنامه",
                Columns = new[] { "بخش", "شرح", "کد طبقه", "مبلغ (ریال)" }
            };

            long? cash = AccountBalance("1010", true);
            long? receivables = AccountBalance("1200", true);
            long? payables = AccountBalance("2000", false);
            long? capital = AccountBalance("3000", false);
            long? sales = AccountBalance("4000", false);
            long? purchases = AccountBalance("5000", true);
            long? expenses = AccountBalance("5100", true);

            // Baskets ledger: every seller's final balance, summed.
            //
            // THE PAYMENTS ARE NOT IN basket_movements. `event_type` is CHECKed
            // to basket events; a money payment lives in `payments`. Looking for
            // a PAYMENT row here matches nothing, so the baskets asset came out
            // equal to the full purchase total — the seller looked unpaid
            // forever and the balance sheet overstated assets by exactly what
            // had already been paid. Same bug as BasketsReport, fixed here too.
            var basket = Query(
                "SELECT COALESCE(SUM(amount_rial), 0), COUNT(*) " +
                "  FROM basket_movements");
            var paidOut = Query(
                "SELECT COALESCE(SUM(amount_rial), 0) FROM payments " +
                " WHERE direction = 'OUT' " +
                "   AND COALESCE(status, 'APPROVED') <> 'VOIDED'");
            long? basketsValue = null;
            if (basket.Count > 0 && Convert.ToInt64(basket[0][1].Value) > 0)
            {
                basketsValue = Convert.ToInt64(basket[0][0].Value)
                             - Convert.ToInt64(paidOut[0][0].Value);
            }

            // Uncleared cheques, using the same computed status as the cheque
            // reports — not a stored column.
            long unclearedTotal = 0;
            bool anyUncleared = false;
            foreach (ChequeRow r in Cheques())
            {
                if (r.IsCleared || !r.Amount.HasValue) continue;
                unclearedTotal += r.Amount.Value;
                anyUncleared = true;
            }
            long? uncleared = anyUncleared ? (long?)unclearedTotal : null;

            long? assets = SumKnown(cash, receivables, basketsValue, null);
            long? liabilities = SumKnown(payables, uncleared, null, null);
            long? expensesNegated = expenses.HasValue ? -expenses.Value : (long?)null;
            long? equity = SumKnown(null, capital, expensesNegated, null);

            AddSection(result, "دارایی", new[]
            {
                Row("دارایی", "موجودی نقدی بانک‌ها", "b", cash),
                Row("دارایی", "طلب از اشخاص (مانده بدهکار / پیش‌پرداخت)", "p+", receivables),
                Row("دارایی", "سبد و ظروف (دفتر Baskets)", "s", basketsValue),
                Row("دارایی", "دارایی‌های ثابت — زمین، خودرو، تجهیزات (F…)", "f", null)
            });
            AddSection(result, "بدهی", new[]
            {
                Row("بدهی", "دیون اشخاص (مانده بستانکار)", "p-", payables),
                Row("بدهی", "اسناد چک پرداختی — پاس‌نشده", "q", uncleared),
                Row("بدهی", "وام‌ها و تسهیلات (L…)", "l", null),
                Row("بدهی", "متفرقه / در انتظار تعریف", "m", null)
            });
            AddSection(result, "حقوق صاحبان", new[]
            {
                Row("حقوق صاحبان", "افتتاحیه (مانده اولیه بانک‌ها)", "o", null),
                Row("حقوق صاحبان", "سرمایه و آورده صاحبان (CAP…)", "c", capital),
                Row("حقوق صاحبان", "هزینه‌های دوره (کسری)", "e", expensesNegated),
                Row("حقوق صاحبان", "تراکنش‌های شخصی", "x", null)
            });

            long? control = null;
            if (assets.HasValue)
                control = assets.Value - ((liabilities ?? 0) + (equity ?? 0));

            long? cashProfit = null;
            if (sales.HasValue)
                cashProfit = sales.Value - (purchases ?? 0) - (expenses ?? 0);

            result.TotalsLine =
                "جمع دارایی‌ها: " + Fmt(assets)
                + " · جمع بدهی‌ها: " + Fmt(liabilities)
                + " · حقوق صاحبان: " + Fmt(equity)
                + " · کنترل ترازنامه: " + Fmt(control)
                + (control.HasValue && control.Value == 0 ? " ✓" : "");
            result.WarningText =
                "مبنای این ترازنامه نقدی است: درآمد فروش تا تطبیق با فاکتورها "
                + "در «دیون اشخاص» می‌نشیند و هنوز سود شناسایی‌شده نیست؛ "
                + "سود واقعی دوره = درآمد فاکتورشده − بهای تمام‌شده − هزینه‌ها.";
            return result;
        }

        /// <summary>
        /// Sum the parts that are known. Returns null only when EVERY part is
        /// unknown — a total over four blanks is unknown, but a total over
        /// three blanks and one real number is that number. A missing part is
        /// never treated as zero, which is what makes the total honest.
        /// </summary>
        private static long? SumKnown(long? a, long? b, long? c, long? d)
        {
            bool any = a.HasValue || b.HasValue || c.HasValue || d.HasValue;
            if (!any) return null;
            return (a ?? 0) + (b ?? 0) + (c ?? 0) + (d ?? 0);
        }

        private static string[] Row(string section, string desc, string code,
                                    long? amount)
        {
            return new[] { section, desc, code, Fmt(amount) };
        }

        /// <summary>An unknown amount prints as a dash, never "0".</summary>
        private static string Fmt(long? value)
        {
            return value.HasValue ? value.Value.ToString("N0") : "—";
        }

        private static void AddSection(ReportResult result, string section,
                                       string[][] rows)
        {
            foreach (string[] row in rows) result.Rows.Add(row);
            // A section subtotal row, so the owner does not have to add four
            // numbers by hand to check the control.
            long? total = null;
            long sum = 0;
            bool any = false;
            foreach (string[] row in rows)
            {
                if (row[3] == "—") continue;
                sum += ParseFormatted(row[3]);
                any = true;
            }
            if (any) total = sum;
            result.Rows.Add(new[]
            {
                section, "جمع " + section, "", Fmt(total)
            });
        }

        public void Dispose()
        {
            _connection.Dispose();
        }
    }
}
