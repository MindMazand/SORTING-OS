using System;
using System.Collections.Generic;
using Mazandasht.Application.Import;
using Mazandasht.Infrastructure;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// Wires ImportRunner to the SQLite stores and exposes the three operations
    /// the import centre actually performs.
    ///
    /// WHY THIS CLASS EXISTS
    ///
    /// ImportRunner.Rollback takes two delegates (child ids, delete by ids)
    /// because it deliberately knows nothing about SQL. That is right for
    /// testing, but it means every caller would have to write the same wiring —
    /// and a caller that wires it slightly wrong deletes children in the wrong
    /// order, which fails on a foreign key *after* having deleted something.
    ///
    /// So the wiring lives here, once, next to the store that owns the
    /// connection.
    ///
    /// Every method opens and disposes its own connections. A long-lived
    /// connection here would hold a write lock across the whole preview of a
    /// 2,000-row file, and the dashboard refreshing at that moment would be
    /// told "database is locked".
    /// </summary>
    public sealed class ImportService : IDisposable
    {
        private readonly string _connectionString;
        private readonly SqliteImportStore _store;
        private readonly SqliteImportBatchStore _batches;
        private readonly ImportRunner _runner;
        private readonly SqliteAuditLogger _audit;

        public ImportService(string databasePath)
        {
            if (string.IsNullOrEmpty(databasePath))
                throw new ArgumentException("databasePath", "databasePath");

            // One connection string shape for both stores. System.Data.SQLite
            // accepts a bare path; being explicit avoids depending on the
            // provider's default, which changed between versions.
            _connectionString = "Data Source=" + databasePath + ";Version=3;";
            _store = new SqliteImportStore(_connectionString);
            _batches = new SqliteImportBatchStore(_connectionString);
            _runner = new ImportRunner(_store, _batches);
            _audit = new SqliteAuditLogger(databasePath);
        }

        /// <summary>
        /// Why the import path audits at all (spec ch.10): an imported batch is
        /// the one place in this app where hundreds of financial documents
        /// appear from a file. "Who imported what, when" must be answerable
        /// without trusting the import_batches table, because a rollback deletes
        /// the documents while the audit row deliberately survives.
        /// </summary>
        private void Audit(string action, string entityType, long? entityId,
                           string details)
        {
            _audit.Log(new AuditEvent
            {
                Action = action,
                EntityType = entityType,
                EntityId = entityId,
                Details = details,
            });
        }

        /// <summary>
        /// Parse and resolve WITHOUT writing anything. This is what the
        /// "بررسی فایل" button calls: the owner must be able to see what would
        /// happen before anything does.
        /// </summary>
        public ImportRunner.RunResult Preview(string path, string templateCode)
        {
            return _runner.Run(path, templateCode, false);
        }

        /// <summary>
        /// Parse and WRITE. Creates the batch row, every document, and the
        /// import_rows audit trail that rollback depends on.
        /// </summary>
        public ImportRunner.RunResult Commit(string path, string templateCode)
        {
            ImportRunner.RunResult result = _runner.Run(path, templateCode, true);
            Audit(result.BatchCode == null ? "IMPORT_FAILED" : "IMPORT_COMMIT",
                  templateCode,
                  result.BatchId,
                  (result.BatchCode ?? "(بدون کد دسته)") + " · " +
                  System.IO.Path.GetFileName(path) + " · " +
                  (result.Write == null ? 0 : result.Write.Created) + " سند" +
                  (result.Errors.Count == 0 ? "" : " · خطا: " + string.Join(" | ", result.Errors)));
            return result;
        }

        public IReadOnlyList<ImportBatchInfo> RecentBatches(int limit)
        {
            return _batches.ListBatches(limit);
        }

        /// <summary>
        /// Roll back one batch.
        ///
        /// Three refusals are possible and all three are reported rather than
        /// thrown, because "why can I not roll this back" is a question the
        /// owner asks, not an exception:
        ///   * already rolled back
        ///   * one of its documents is approved (immutable by contract)
        ///   * no deletion plan for this template
        /// </summary>
        public RollbackOutcome Rollback(long batchId)
        {
            ImportBatchInfo batch = _batches.GetBatch(batchId);
            if (batch == null)
            {
                RollbackOutcome missing = new RollbackOutcome();
                missing.Refusals.Add("دسته با شناسه " + batchId + " پیدا نشد");
                return missing;
            }

            IReadOnlyList<ImportedRowRef> rows = _batches.GetImportedRows(batchId);
            bool anyApproved = _batches.AnyApproved(batch);

            RollbackOutcome outcome = _runner.Rollback(
                batch, rows, anyApproved,
                (table, column, parentIds) => _batches.ChildIds(table, column, parentIds),
                (table, ids) => _batches.DeleteByIds(table, ids));

            if (outcome.Succeeded)
                _batches.MarkBatchRolledBack(batchId);

            Audit(outcome.Succeeded ? "IMPORT_ROLLBACK" : "IMPORT_ROLLBACK_REFUSED",
                  batch.DetectedType,
                  batchId,
                  batch.Code + " · " + outcome.Deleted + " سند حذف شد" +
                  (outcome.Refusals.Count == 0 ? "" :
                   " · رد شد: " + string.Join(" | ", outcome.Refusals)));

            return outcome;
        }

        public void Dispose()
        {
            _store.Dispose();
            _batches.Dispose();
            _audit.Dispose();
        }
    }
}
