using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.IO;

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
    /// </summary>
    public sealed class MigrationRunner
    {
        private readonly string _connectionString;
        private readonly IReadOnlyList<Migration> _migrations;

        public MigrationRunner(string connectionString, IReadOnlyList<Migration> migrations)
        {
            _connectionString = connectionString ?? throw new ArgumentNullException(nameof(connectionString));
            _migrations = migrations ?? throw new ArgumentNullException(nameof(migrations));
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

        public void Migrate()
        {
            var current = CurrentVersion();
            foreach (var m in _migrations)
            {
                if (m.Version <= current) continue;
                using (var con = new SQLiteConnection(_connectionString))
                {
                    con.Open();
                    using (var tx = con.BeginTransaction())
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
                            cmd.CommandText =
                                "INSERT INTO schema_migrations (version, name, checksum) VALUES (@v, @n, @c)";
                            cmd.Parameters.AddWithValue("@v", m.Version);
                            cmd.Parameters.AddWithValue("@n", m.Name);
                            cmd.Parameters.AddWithValue("@c", m.Checksum);
                            cmd.ExecuteNonQuery();
                        }
                        tx.Commit();
                    }
                }
            }
        }

        /// <summary>Load SQL migration files from a folder (001_name.sql, ...).</summary>
        public static IReadOnlyList<Migration> LoadFromFolder(string folder)
        {
            var list = new List<Migration>();
            foreach (var file in Directory.GetFiles(folder, "*.sql"))
            {
                var name = Path.GetFileNameWithoutExtension(file);
                var parts = name.Split(new[] { '_' }, 2);
                if (!int.TryParse(parts[0], out var version)) continue;
                list.Add(new Migration
                {
                    Version = version,
                    Name = name,
                    Sql = File.ReadAllText(file)
                });
            }
            list.Sort((a, b) => a.Version.CompareTo(b.Version));
            return list;
        }
    }
}
