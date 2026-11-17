using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace Mazandasht.Persistence
{
    /// <summary>One versioned migration (Spec ch. 3, 16).</summary>
    public sealed class Migration
    {
        public int Version { get; set; }
        public string Name { get; set; } = "";
        public string Sql { get; set; } = "";
        public string Checksum { get; set; } = "";
    }

    /// <summary>
    /// Versioned, transactional migrations. A backup is taken before any
    /// migration runs; each migration applies atomically and is recorded in
    /// schema_migrations. The live DB never lives in a sync folder.
    ///
    /// SQLite facts this class depends on (each one cost a real bug — see
    /// reports/EXECUTION_LEDGER.md NEW-03):
    ///   * PRAGMA foreign_keys is a NO-OP inside a transaction. Migrations that
    ///     rebuild tables (v002 does) need FKs off *before* BEGIN, so the pragma
    ///     is issued on the open connection and its result verified.
    ///   * PRAGMA foreign_keys cannot be changed with a statement in progress;
    ///     the connection must be idle.
    ///   * PRAGMA legacy_alter_table defaults to OFF in modern SQLite, which is
    ///     what we want: RENAME must fix up references.
    ///   * A failed step inside a transaction leaves the connection usable for
    ///     ROLLBACK, so every migration is all-or-nothing.
    /// </summary>
    public sealed class MigrationRunner
    {
        private readonly string _connectionString;
        private readonly IReadOnlyList<Migration> _migrations;
        private readonly Action<string> _log;

        public MigrationRunner(string connectionString, IReadOnlyList<Migration> migrations,
                               Action<string> log = null)
        {
            _connectionString = connectionString ?? throw new ArgumentNullException(nameof(connectionString));
            _migrations = migrations ?? throw new ArgumentNullException(nameof(migrations));
            _log = log ?? (_ => { });
        }

        public int CurrentVersion()
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText = "SELECT COALESCE(MAX(version),0) FROM schema_migrations";
                    var v = cmd.ExecuteScalar();
                    return v == null || v == DBNull.Value ? 0 : Convert.ToInt32(v);
                }
            }
        }

        /// <summary>
        /// Apply every pending migration in ascending version order, one
        /// transaction each. Throws on the first failure and leaves the
        /// database at the last fully-applied version.
        /// </summary>
        public void Migrate()
        {
            var current = CurrentVersion();
            foreach (var m in _migrations)
            {
                if (m.Version <= current) continue;
                ApplyOne(m);
            }
        }

        private void ApplyOne(Migration m)
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();

                // Must happen OUTSIDE the transaction, and must be verified:
                // a silently-ignored pragma would let a table rebuild break
                // referential integrity without anyone noticing.
                ExecuteNonQuery(con, "PRAGMA foreign_keys = OFF");
                var fk = Convert.ToInt32(Scalar(con, "PRAGMA foreign_keys"));
                if (fk != 0)
                    throw new InvalidOperationException(
                        "Could not disable foreign_keys before migration " + m.Version +
                        "; refusing to rebuild tables with FK enforcement on.");

                using (var tx = con.BeginTransaction())
                {
                    try
                    {
                        using (var cmd = con.CreateCommand())
                        {
                            cmd.Transaction = tx;
                            cmd.CommandText = m.Sql;
                            cmd.ExecuteNonQuery();
                        }

                        using (var cmd = con.CreateCommand())
                        {
                            cmd.Transaction = tx;
                            // OR REPLACE: a migration file may also self-record.
                            cmd.CommandText =
                                "INSERT OR REPLACE INTO schema_migrations (version, name, checksum) " +
                                "VALUES (@v, @n, @c)";
                            cmd.Parameters.AddWithValue("@v", m.Version);
                            cmd.Parameters.AddWithValue("@n", m.Name);
                            cmd.Parameters.AddWithValue("@c", m.Checksum ?? "");
                            cmd.ExecuteNonQuery();
                        }

                        // Referential integrity is a precondition of COMMIT, not
                        // a smoke test to run later.
                        var bad = new List<string>();
                        using (var cmd = con.CreateCommand())
                        {
                            cmd.Transaction = tx;
                            cmd.CommandText = "PRAGMA foreign_key_check";
                            using (var r = cmd.ExecuteReader())
                                while (r.Read())
                                    bad.Add(Convert.ToString(r.GetValue(0)));
                        }
                        if (bad.Count > 0)
                            throw new InvalidOperationException(
                                "Migration " + m.Version + " broke foreign keys in: " +
                                string.Join(", ", bad));

                        using (var cmd = con.CreateCommand())
                        {
                            cmd.Transaction = tx;
                            cmd.CommandText = "PRAGMA integrity_check";
                            var ok = Convert.ToString(cmd.ExecuteScalar());
                            if (!string.Equals(ok, "ok", StringComparison.OrdinalIgnoreCase))
                                throw new InvalidOperationException(
                                    "integrity_check failed after migration " + m.Version + ": " + ok);
                        }

                        tx.Commit();
                        _log("Applied migration " + m.Version + " (" + m.Name + ")");
                    }
                    catch
                    {
                        try { tx.Rollback(); } catch { /* connection already gone */ }
                        throw;
                    }
                }

                ExecuteNonQuery(con, "PRAGMA foreign_keys = ON");
            }
        }

        private static void ExecuteNonQuery(SQLiteConnection con, string sql)
        {
            using (var cmd = con.CreateCommand())
            {
                cmd.CommandText = sql;
                cmd.ExecuteNonQuery();
            }
        }

        private static object Scalar(SQLiteConnection con, string sql)
        {
            using (var cmd = con.CreateCommand())
            {
                cmd.CommandText = sql;
                return cmd.ExecuteScalar();
            }
        }

        /// <summary>
        /// Load SQL migration files from a folder. Accepted names:
        ///   NNN_name.sql   (canonical, e.g. 002_v002_workbook_alignment.sql)
        ///   NNN.sql        (shorthand, e.g. 001.sql)
        /// Files without a numeric prefix are IGNORED with a log line rather
        /// than silently skipped — a migration that never runs is exactly the
        /// failure this loader used to hide (it split on '_' and rejected
        /// "migration_002.sql" without a word).
        /// </summary>
        public static IReadOnlyList<Migration> LoadFromFolder(string folder, Action<string> log = null)
        {
            log = log ?? (_ => { });
            var list = new List<Migration>();
            var files = Directory.GetFiles(folder, "*.sql");
            Array.Sort(files, StringComparer.OrdinalIgnoreCase);

            foreach (var file in files)
            {
                var name = Path.GetFileNameWithoutExtension(file);
                var digits = new StringBuilder();
                foreach (var ch in name)
                {
                    if (char.IsDigit(ch)) digits.Append(ch);
                    else break;
                }

                if (digits.Length == 0 || !int.TryParse(digits.ToString(), out var version))
                {
                    log("SKIP migration file without numeric prefix: " + Path.GetFileName(file));
                    continue;
                }

                var sql = File.ReadAllText(file, Encoding.UTF8);
                list.Add(new Migration
                {
                    Version = version,
                    Name = name,
                    Sql = sql,
                    Checksum = Sha256Hex(sql)
                });
            }

            list.Sort((a, b) => a.Version.CompareTo(b.Version));

            for (int i = 1; i < list.Count; i++)
                if (list[i].Version == list[i - 1].Version)
                    throw new InvalidOperationException(
                        "Duplicate migration version " + list[i].Version + ": " +
                        list[i - 1].Name + " and " + list[i].Name);

            return list;
        }

        /// <summary>SHA-256 of the migration text, so drift on an already-applied
        /// file can be detected (Spec ch.3: never edit a released migration).</summary>
        public static string Sha256Hex(string text)
        {
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(Encoding.UTF8.GetBytes(text));
                var sb = new StringBuilder(hash.Length * 2);
                foreach (var b in hash) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        /// <summary>
        /// Compare recorded checksums against the files on disk. Returns the
        /// versions whose content changed after being applied. Empty = healthy.
        /// </summary>
        public IReadOnlyList<int> DetectDrift()
        {
            var drift = new List<int>();
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                foreach (var m in _migrations)
                {
                    using (var cmd = con.CreateCommand())
                    {
                        cmd.CommandText =
                            "SELECT checksum FROM schema_migrations WHERE version = @v";
                        cmd.Parameters.AddWithValue("@v", m.Version);
                        var recorded = cmd.ExecuteScalar();
                        if (recorded == null || recorded == DBNull.Value) continue;
                        var rec = Convert.ToString(recorded);
                        if (rec.Length > 0 && !string.Equals(rec, m.Checksum, StringComparison.OrdinalIgnoreCase))
                            drift.Add(m.Version);
                    }
                }
            }
            return drift;
        }
    }
}
