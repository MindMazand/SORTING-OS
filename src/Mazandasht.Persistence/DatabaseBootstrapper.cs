using System;
using System.Data.SQLite;
using System.IO;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// Creates and upgrades the local database (Spec ch. 3, 15, 16).
    ///
    /// Two paths, never mixed:
    ///   * NEW database  -> schema_v001.sql + seed_v001.sql, then every
    ///                      migration in order (so a fresh install and an
    ///                      upgraded install converge on the same shape).
    ///   * EXISTING      -> migrations only, never the base schema (re-running
    ///                      CREATE TABLE would either fail or, worse, be
    ///                      silently skipped and hide a broken file).
    ///
    /// The live database must never sit in a cloud-sync folder; the caller
    /// supplies the path and this class refuses to proceed silently on a
    /// missing schema file.
    /// </summary>
    public sealed class DatabaseBootstrapper
    {
        private readonly string _connectionString;
        private readonly string _schemaFolder;
        private readonly string _seedFolder;
        private readonly string _migrationFolder;
        private readonly Action<string> _log;

        public DatabaseBootstrapper(string connectionString, string schemaFolder,
                                    string seedFolder, string migrationFolder,
                                    Action<string> log = null)
        {
            _connectionString = connectionString ?? throw new ArgumentNullException(nameof(connectionString));
            _schemaFolder = schemaFolder ?? throw new ArgumentNullException(nameof(schemaFolder));
            _seedFolder = seedFolder ?? throw new ArgumentNullException(nameof(seedFolder));
            _migrationFolder = migrationFolder ?? throw new ArgumentNullException(nameof(migrationFolder));
            _log = log ?? (_ => { });
        }

        /// <summary>Returns true when a brand-new database was created.</summary>
        public bool EnsureCreated()
        {
            var fresh = !HasBaseSchema();
            if (fresh)
            {
                _log("Creating new database from base schema + seed.");
                ApplyScript(FindSingle(_schemaFolder, "schema_v*.sql"));
                ApplyScript(FindSingle(_seedFolder, "seed_v*.sql"));
            }
            else
            {
                _log("Existing database found; applying pending migrations only.");
            }

            // PRAGMAs the whole app depends on (docs/02_Technology_and_Runtime_FA.md).
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                Exec(con, "PRAGMA foreign_keys = ON");
                Exec(con, "PRAGMA journal_mode = WAL");
                Exec(con, "PRAGMA synchronous = FULL");
                Exec(con, "PRAGMA busy_timeout = 5000");
            }

            var runner = new MigrationRunner(
                _connectionString, MigrationRunner.LoadFromFolder(_migrationFolder, _log), _log);

            var drift = runner.DetectDrift();
            if (drift.Count > 0)
                throw new InvalidOperationException(
                    "Migration checksum drift on version(s) " + string.Join(", ", drift) +
                    ". A released migration file was edited. Add a new migration instead; " +
                    "the database cannot be trusted until this is resolved.");

            runner.Migrate();
            _log("Database at schema version " + runner.CurrentVersion() + ".");
            return fresh;
        }

        private bool HasBaseSchema()
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText =
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'";
                    return Convert.ToInt64(cmd.ExecuteScalar()) > 0;
                }
            }
        }

        private void ApplyScript(string path)
        {
            var sql = File.ReadAllText(path);
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                Exec(con, "PRAGMA foreign_keys = ON");
                using (var tx = con.BeginTransaction())
                {
                    using (var cmd = con.CreateCommand())
                    {
                        cmd.Transaction = tx;
                        cmd.CommandText = sql;
                        cmd.ExecuteNonQuery();
                    }
                    tx.Commit();
                }
            }
            _log("Applied " + Path.GetFileName(path));
        }

        private static string FindSingle(string folder, string pattern)
        {
            var files = Directory.GetFiles(folder, pattern);
            if (files.Length == 0)
                throw new FileNotFoundException(
                    "Required database script not found: " + pattern + " in " + folder);
            if (files.Length > 1)
                throw new InvalidOperationException(
                    "More than one " + pattern + " in " + folder +
                    "; keep exactly one base script so the install is reproducible.");
            return files[0];
        }

        private static void Exec(SQLiteConnection con, string sql)
        {
            using (var cmd = con.CreateCommand())
            {
                cmd.CommandText = sql;
                cmd.ExecuteNonQuery();
            }
        }
    }
}
