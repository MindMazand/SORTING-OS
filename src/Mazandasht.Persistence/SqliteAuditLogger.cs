using System;
using System.Data.SQLite;
using Mazandasht.Infrastructure;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// Writes audit events to the `audit_events` table (spec ch.10).
    ///
    /// WHY THIS CLASS HAD TO EXIST
    ///
    /// IAuditLogger was declared in Infrastructure and implemented nowhere.
    /// The table existed, the interface existed, and nothing connected them —
    /// which means spec ch.10's "every sensitive action is logged" was a
    /// comment with no runtime effect. An interface with no implementation is
    /// the most comfortable kind of missing feature: it compiles, it reads as
    /// done, and it records nothing.
    ///
    /// DESIGN CHOICES
    ///
    ///  * Own connection, opened per write. Audit writes happen at the edges of
    ///    user actions, not in loops, so the cost is irrelevant and a shared
    ///    connection would risk being closed mid-operation by another window.
    ///
    ///  * Log() never throws. An audit failure must not roll back the business
    ///    action that is being audited — losing a sale because the log insert
    ///    failed is worse than a missing log line. The failure is reported
    ///    through LastError so the UI can surface it.
    ///
    ///  * Details is free text. The schema column is TEXT and audit details
    ///    evolve faster than any column set could; JSON in a text column is the
    ///    honest shape here.
    /// </summary>
    public sealed class SqliteAuditLogger : IAuditLogger, IDisposable
    {
        private readonly string _connectionString;
        private readonly SQLiteConnection _connection;

        /// <summary>Last failure, or null. Read by the caller when it wants to
        /// tell the owner that auditing is not working.</summary>
        public string LastError { get; private set; }

        public SqliteAuditLogger(string databasePath)
        {
            if (string.IsNullOrEmpty(databasePath))
                throw new ArgumentException("databasePath", "databasePath");
            _connectionString = "Data Source=" + databasePath + ";Version=3;";
            _connection = new SQLiteConnection(_connectionString);
            _connection.Open();
        }

        public void Log(AuditEvent evt)
        {
            if (evt == null) return;
            try
            {
                using (var cmd = _connection.CreateCommand())
                {
                    cmd.CommandText =
                        "INSERT INTO audit_events(user_id, action, entity_type, " +
                        "entity_id, details) VALUES(@u, @a, @t, @i, @d)";

                    if (evt.UserId.HasValue)
                        cmd.Parameters.AddWithValue("@u", evt.UserId.Value);
                    else
                        cmd.Parameters.AddWithValue("@u", DBNull.Value);

                    // An audit row with no action is noise. Store a marker
                    // rather than an empty string so it is greppable.
                    cmd.Parameters.AddWithValue("@a",
                        string.IsNullOrEmpty(evt.Action) ? "(بی‌نام)" : evt.Action);

                    cmd.Parameters.AddWithValue("@t",
                        string.IsNullOrEmpty(evt.EntityType) ? "(نامشخص)" : evt.EntityType);

                    if (evt.EntityId.HasValue)
                        cmd.Parameters.AddWithValue("@i", evt.EntityId.Value);
                    else
                        cmd.Parameters.AddWithValue("@i", DBNull.Value);

                    cmd.Parameters.AddWithValue("@d", evt.Details ?? "");
                    cmd.ExecuteNonQuery();
                }
                LastError = null;
            }
            catch (Exception ex)
            {
                // Deliberately swallowed: see the class comment. The caller
                // reads LastError if it cares.
                LastError = ex.Message;
            }
        }

        /// <summary>How many events exist, for the tools screen's health line.</summary>
        public long Count()
        {
            try
            {
                using (var cmd = _connection.CreateCommand())
                {
                    cmd.CommandText = "SELECT COUNT(*) FROM audit_events";
                    return Convert.ToInt64(cmd.ExecuteScalar());
                }
            }
            catch (Exception ex)
            {
                LastError = ex.Message;
                return -1;
            }
        }

        public void Dispose()
        {
            _connection.Dispose();
        }
    }
}
