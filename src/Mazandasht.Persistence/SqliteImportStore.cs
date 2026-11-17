using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.Globalization;
using System.Linq;
using Mazandasht.Application.Import;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// SQLite implementation of the import writer's store.
    ///
    /// Deliberate decisions:
    ///   * One connection, one transaction per file. A half-imported invoice
    ///     would be worse than a failed import.
    ///   * Table and column names are whitelisted before they reach a SQL
    ///     string. They come from the contract, not from a user, but building
    ///     SQL by concatenation without a guard is how injection starts.
    ///   * A key that the target table does not have raises an exception
    ///     instead of being silently dropped; a silently dropped column is the
    ///     most expensive class of bug in an import engine.
    /// </summary>
    public sealed class SqliteImportStore : IImportStore, IDisposable
    {
        private static readonly HashSet<string> AllowedTables = new HashSet<string>(StringComparer.Ordinal)
        {
            "parties", "products", "weigh_tickets", "lots", "stock_movements",
            "purchase_invoices", "purchase_invoice_lines", "sales_invoices",
            "sales_invoice_lines", "sorting_batches", "sorting_inputs",
            "sorting_outputs", "waste_records", "basket_movements",
            "bank_transactions", "cheques", "payment_allocations",
            "partnership_events", "partnerships", "import_batches", "import_rows",
        };

        private readonly SQLiteConnection _connection;
        private readonly Dictionary<string, HashSet<string>> _columns =
            new Dictionary<string, HashSet<string>>(StringComparer.Ordinal);

        public SqliteImportStore(string connectionString)
        {
            _connection = new SQLiteConnection(connectionString);
            _connection.Open();
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "PRAGMA foreign_keys = ON";
                cmd.ExecuteNonQuery();
            }
        }

        private static void EnsureTable(string table)
        {
            if (!AllowedTables.Contains(table))
                throw new InvalidOperationException("جدول مجاز نیست: " + table);
        }

        private HashSet<string> Columns(string table)
        {
            EnsureTable(table);
            HashSet<string> cols;
            if (_columns.TryGetValue(table, out cols)) return cols;

            cols = new HashSet<string>(StringComparer.Ordinal);
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "PRAGMA table_info(" + table + ")";
                using (var r = cmd.ExecuteReader())
                    while (r.Read()) cols.Add(Convert.ToString(r["name"]));
            }
            _columns[table] = cols;
            return cols;
        }

        public long? Lookup(string lookupSpec, string code)
        {
            if (string.IsNullOrEmpty(lookupSpec) || string.IsNullOrEmpty(code)) return null;
            var parts = lookupSpec.Split(':');
            var table = parts[0];
            var column = parts.Length > 1 ? parts[1] : "code";
            EnsureTable(table);
            if (!Columns(table).Contains(column))
                throw new InvalidOperationException(
                    "ستون مرجع در جدول " + table + " وجود ندارد: " + column);

            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT id FROM " + table + " WHERE " + column + " = @c LIMIT 1";
                cmd.Parameters.AddWithValue("@c", code);
                var result = cmd.ExecuteScalar();
                return result == null || result == DBNull.Value ? (long?)null
                                                                : Convert.ToInt64(result);
            }
        }

        public string LookupKind(string invoiceNumber)
        {
            if (string.IsNullOrEmpty(invoiceNumber)) return null;
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "SELECT kind FROM v_invoice_lookup WHERE doc_number = @n LIMIT 1";
                cmd.Parameters.AddWithValue("@n", invoiceNumber);
                var result = cmd.ExecuteScalar();
                return result == null || result == DBNull.Value ? null : Convert.ToString(result);
            }
        }

        public string NextCode(string table, string prefix)
        {
            EnsureTable(table);
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "SELECT code FROM " + table + " WHERE code LIKE @p " +
                    "ORDER BY length(code) DESC, code DESC LIMIT 1";
                cmd.Parameters.AddWithValue("@p", prefix + "%");
                var last = cmd.ExecuteScalar() as string;
                if (string.IsNullOrEmpty(last)) return prefix + "001";
                var tail = last.Substring(prefix.Length);
                long n;
                if (!long.TryParse(tail, NumberStyles.Integer, CultureInfo.InvariantCulture, out n))
                    n = 0;
                return prefix + (n + 1).ToString("000", CultureInfo.InvariantCulture);
            }
        }

        public bool SourceKeyExists(string table, string column, string key)
        {
            EnsureTable(table);
            if (!Columns(table).Contains(column)) return false;
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT COUNT(*) FROM " + table + " WHERE " + column + " = @k";
                cmd.Parameters.AddWithValue("@k", key);
                return Convert.ToInt64(cmd.ExecuteScalar()) > 0;
            }
        }

        public long Insert(string table, IDictionary<string, object> values)
        {
            EnsureTable(table);
            var cols = Columns(table);
            var unknown = values.Keys.Where(k => !cols.Contains(k)).ToList();
            if (unknown.Count > 0)
                throw new InvalidOperationException(
                    "ستون(های) ناشناخته در " + table + ": " + string.Join(", ", unknown));

            var keys = values.Keys.ToList();
            var sql = "INSERT INTO " + table + " (" + string.Join(", ", keys) + ") VALUES (" +
                      string.Join(", ", keys.Select((k, i) => "@p" + i)) + ")";
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = sql;
                for (var i = 0; i < keys.Count; i++)
                {
                    var value = values[keys[i]];
                    cmd.Parameters.AddWithValue("@p" + i, value ?? DBNull.Value);
                }
                cmd.ExecuteNonQuery();
            }
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT last_insert_rowid()";
                return Convert.ToInt64(cmd.ExecuteScalar());
            }
        }

        public long DefaultPartnershipId()
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT id FROM partnerships ORDER BY id LIMIT 1";
                var found = cmd.ExecuteScalar();
                if (found != null && found != DBNull.Value) return Convert.ToInt64(found);
            }
            return Insert("partnerships", new Dictionary<string, object>
            {
                { "code", "PS01" },
                { "description", "شراکت اصلی" },
            });
        }

        public void BeginTransaction()
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "BEGIN IMMEDIATE";
                cmd.ExecuteNonQuery();
            }
        }

        public void Commit()
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "COMMIT";
                cmd.ExecuteNonQuery();
            }
        }

        public void Rollback()
        {
            try
            {
                using (var cmd = _connection.CreateCommand())
                {
                    cmd.CommandText = "ROLLBACK";
                    cmd.ExecuteNonQuery();
                }
            }
            catch (SQLiteException)
            {
                // Already rolled back by SQLite; nothing left to undo.
            }
        }

        public void Dispose()
        {
            _connection.Dispose();
        }
    }
}
