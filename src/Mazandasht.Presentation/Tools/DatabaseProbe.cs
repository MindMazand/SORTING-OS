using System;
using System.Data.SQLite;
using System.IO;

namespace Mazandasht.Presentation.Tools
{
    /// <summary>
    /// Read-only questions the tools screen asks the database.
    ///
    /// This is deliberately NOT IDashboardStore. That interface answers "what
    /// are the nineteen KPIs"; this one answers "is this tool healthy and when
    /// did it last run". Merging them would make the dashboard interface a
    /// grab-bag and force every fake dashboard store to implement integrity
    /// checks it will never use.
    ///
    /// One connection, opened per probe, disposed. The tools screen is opened
    /// occasionally; holding a connection for its lifetime would keep a file
    /// lock that blocks a backup copy on Windows.
    /// </summary>
    public sealed class DatabaseProbe : IDisposable
    {
        private readonly SQLiteConnection _connection;

        public DatabaseProbe(string databasePath)
        {
            if (string.IsNullOrEmpty(databasePath))
                throw new ArgumentException("databasePath", "databasePath");
            _connection = new SQLiteConnection("Data Source=" + databasePath + ";");
            _connection.Open();
        }

        /// <summary>A count or any single integer. Returns 0 on a missing table
        /// so an older schema degrades the card instead of crashing the window.</summary>
        public long Scalar(string sql)
        {
            try
            {
                using (var cmd = _connection.CreateCommand())
                {
                    cmd.CommandText = sql;
                    object raw = cmd.ExecuteScalar();
                    if (raw == null || raw == DBNull.Value) return 0;
                    return Convert.ToInt64(raw);
                }
            }
            catch (SQLiteException)
            {
                return 0;
            }
        }

        /// <summary>A single text value, or "" when null/missing.</summary>
        public string Text(string sql)
        {
            try
            {
                using (var cmd = _connection.CreateCommand())
                {
                    cmd.CommandText = sql;
                    object raw = cmd.ExecuteScalar();
                    if (raw == null || raw == DBNull.Value) return "";
                    return Convert.ToString(raw);
                }
            }
            catch (SQLiteException)
            {
                return "";
            }
        }

        /// <summary>
        /// PRAGMA integrity_check. Returns "ok" or the first problem line.
        /// This is the same check tools/verify_database.py runs; the tools
        /// screen showing it means the owner can spot a corrupt file without
        /// anyone opening a terminal.
        /// </summary>
        public string IntegrityCheck()
        {
            try
            {
                using (var cmd = _connection.CreateCommand())
                {
                    cmd.CommandText = "PRAGMA integrity_check";
                    object raw = cmd.ExecuteScalar();
                    string text = raw == null || raw == DBNull.Value
                        ? "(بدون پاسخ)" : Convert.ToString(raw);
                    return text;
                }
            }
            catch (SQLiteException ex)
            {
                return ex.Message;
            }
        }

        public void Dispose()
        {
            _connection.Dispose();
        }
    }

    internal static class FileInfoExtension
    {
        /// <summary>"2026-11-17 14:32" from a FileInfo, for the status line.</summary>
        public static string WriteTimeText(this FileInfo info)
        {
            return info.LastWriteTime.ToString("yyyy-MM-dd HH:mm");
        }
    }
}
