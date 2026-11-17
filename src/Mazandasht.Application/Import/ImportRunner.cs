using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

namespace Mazandasht.Application.Import
{
    public sealed class ImportBatchInfo
    {
        public long Id { get; set; }
        public string Code { get; set; } = "";
        public string FileName { get; set; } = "";
        public string DetectedType { get; set; } = "";
        public string Status { get; set; } = "DRAFT";
        public int TotalRows { get; set; }
        public int ValidRows { get; set; }
        public int DuplicateRows { get; set; }
        public int InvalidRows { get; set; }
    }

    public sealed class ImportedRowRef
    {
        public long ImportRowId { get; set; }
        public int SourceRow { get; set; }
        public string Status { get; set; } = "";
        public long? NewId { get; set; }
    }

    /// <summary>
    /// Persistence for the import batch itself: the audit trail and the
    /// rollback ledger.
    ///
    /// Why a separate interface from IImportStore: the batch record must
    /// survive exactly when the documents do NOT (a failed import still
    /// records which rows were rejected and why). Keeping it on the same
    /// interface invites a half-written batch.
    /// </summary>
    public interface IImportBatchStore
    {
        long CreateBatch(ImportBatchInfo info, string fileSha256, int headerRow,
                         int headerRowSecond, string profileCode);

        long AddRow(long batchId, int sourceRow, string rawJson, string mappedJson,
                    string blankFieldsJson, string status, string errorMessage);

        void MarkRowImported(long importRowId, long newId);
        void MarkRowInvalid(long importRowId, string errorMessage);

        /// <summary>Batch code is fixed at creation and is the human handle for
        /// the audit trail (IMP-20261117-...). Never reused.</summary>
        string NextBatchCode();
    }

    public sealed class RollbackOutcome
    {
        public bool Succeeded { get; set; }
        public int Deleted { get; set; }
        public List<string> Refusals { get; } = new List<string>();
        public List<string> Errors { get; } = new List<string>();
    }

    /// <summary>
    /// Orchestrates stages 2-7 as one operation and records the batch so the
    /// import can be rolled back later.
    ///
    /// What this class adds over ImportWriter:
    ///   * the audit row (file hash, both header rows, per-row status) that
    ///     survives a failed import
    ///   * the id chain: import_rows.new_id -> the document created
    ///   * rollback that deletes CHILDREN FIRST. Deleting a weigh ticket before
    ///     its lot fails on the foreign key, and that failure was real: it is
    ///     how this method came to exist (test "rollback of a weigh import").
    ///
    /// Rollback is refused, never forced, when any created document has been
    /// APPROVED. An approved document is immutable by contract (Spec ch.6);
    /// deleting it would destroy an audit trail instead of correcting it.
    /// </summary>
    public sealed class ImportRunner
    {
        private readonly IImportStore _store;
        private readonly IImportBatchStore _batches;
        private readonly ImportEngine _engine = new ImportEngine();

        public ImportRunner(IImportStore store, IImportBatchStore batches)
        {
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _batches = batches ?? throw new ArgumentNullException(nameof(batches));
        }

        public sealed class RunResult
        {
            public ParseOutcome Parse { get; set; }
            public WriteOutcome Write { get; set; }
            public long? BatchId { get; set; }
            public string BatchCode { get; set; }
            public List<string> Errors { get; } = new List<string>();
            public bool Ok => Write != null && Write.Failed == 0 && Write.Errors.Count == 0;
        }

        /// <param name="commit">false = preview: parses and resolves, writes
        /// neither documents nor a batch row.</param>
        public RunResult Run(string path, string expectedTemplateCode, bool commit)
        {
            if (path == null) throw new ArgumentNullException(nameof(path));

            var result = new RunResult();
            result.Parse = _engine.Parse(path, expectedTemplateCode);
            if (!result.Parse.Ok)
            {
                result.Errors.AddRange(result.Parse.FileErrors);
                return result;
            }

            var template = result.Parse.Template;
            var sha = FileSha256(path);

            long? batchId = null;
            if (commit)
            {
                result.BatchCode = _batches.NextBatchCode();
                batchId = _batches.CreateBatch(new ImportBatchInfo
                {
                    Code = result.BatchCode,
                    FileName = Path.GetFileName(path),
                    DetectedType = template.Code,
                    Status = "REVIEW",
                    TotalRows = result.Parse.Rows.Count,
                    ValidRows = result.Parse.ValidRows.Count(),
                    InvalidRows = result.Parse.InvalidRows.Count(),
                }, sha, template.HeaderRowEn, template.HeaderRowFa, null);
                result.BatchId = batchId;
            }

            // Record every row BEFORE writing documents, so a crash mid-import
            // still leaves an explanation of what was attempted.
            var rowIds = new Dictionary<int, long>();
            if (commit && batchId.HasValue)
            {
                foreach (var row in result.Parse.Rows)
                {
                    var raw = string.Join("|", row.Values.Select(kv =>
                        kv.Key + "=" + (kv.Value == null ? "" : kv.Value.ToString())));
                    var id = _batches.AddRow(
                        batchId.Value, row.SourceRow, raw, "",
                        string.Join(",", row.Blanks),
                        row.Ok ? "VALID" : "INVALID",
                        string.Join(" | ", row.Errors.Select(e => e.Message)));
                    rowIds[row.SourceRow] = id;
                }
            }

            var writer = new ImportWriter(_store);
            result.Write = writer.Write(result.Parse, commit);
            result.Errors.AddRange(result.Write.Errors);

            if (commit && batchId.HasValue)
            {
                // Link each created document back to its source row. Without
                // this the batch cannot be rolled back precisely, only guessed
                // at, and guessing is how the wrong invoice gets deleted.
                var created = result.Write.CreatedIds;
                var validRows = result.Parse.ValidRows
                    .Where(r => rowIds.ContainsKey(r.SourceRow))
                    .OrderBy(r => r.SourceRow)
                    .ToList();
                for (var i = 0; i < Math.Min(created.Count, validRows.Count); i++)
                    _batches.MarkRowImported(rowIds[validRows[i].SourceRow], created[i]);

                foreach (var row in result.Parse.InvalidRows)
                    if (rowIds.ContainsKey(row.SourceRow))
                        _batches.MarkRowInvalid(rowIds[row.SourceRow],
                            string.Join(" | ", row.Errors.Select(e => e.Message)));
            }

            return result;
        }

        /// <summary>
        /// Rollback plan per template: (table, column, parentTable).
        ///
        /// It is executed in TWO passes and the order of this list is the
        /// COLLECTION order, not the delete order:
        ///   pass 1 collect ids forwards  -> a child's ids are only findable
        ///                                   once its parent's are known
        ///   pass 2 delete by depth, deepest first, root last
        ///
        /// Neither "list order" nor "reverse list order" is correct. The real
        /// chain is two levels deep (weigh_tickets -> lots -> stock_movements)
        /// and every simpler rule failed on the foreign key before this one.
        /// </summary>
        private static IReadOnlyList<Tuple<string, string, string>> RollbackPlan(string templateCode)
        {
            switch (templateCode)
            {
                case "WEIGHING_IN":
                    return new[]
                    {
                        Tuple.Create("lots", "weigh_ticket_id", (string)null),
                        Tuple.Create("stock_movements", "lot_id", "lots"),
                        Tuple.Create("weigh_tickets", "id", (string)null),
                    };
                case "SORTING":
                    return new[]
                    {
                        Tuple.Create("waste_records", "batch_id", (string)null),
                        Tuple.Create("sorting_outputs", "batch_id", (string)null),
                        Tuple.Create("sorting_inputs", "batch_id", (string)null),
                        Tuple.Create("sorting_batches", "id", (string)null),
                    };
                case "PURCHASE_INVOICES":
                    return new[]
                    {
                        Tuple.Create("purchase_invoice_lines", "invoice_id", (string)null),
                        Tuple.Create("purchase_invoices", "id", (string)null),
                    };
                case "SALES_INVOICES":
                    return new[]
                    {
                        Tuple.Create("sales_invoice_lines", "invoice_id", (string)null),
                        Tuple.Create("sales_invoices", "id", (string)null),
                    };
                case "PARTIES": return Single("parties");
                case "PRODUCTS": return Single("products");
                case "BASKET_MOVEMENTS": return Single("basket_movements");
                case "BANK_TRANSACTIONS": return Single("bank_transactions");
                case "CHEQUES": return Single("cheques");
                case "SETTLEMENTS": return Single("payment_allocations");
                case "PARTNERSHIP": return Single("partnership_events");
                default: return new Tuple<string, string, string>[0];
            }
        }

        private static IReadOnlyList<Tuple<string, string, string>> Single(string table)
        {
            return new[] { Tuple.Create(table, "id", (string)null) };
        }

        private readonly struct Level
        {
            public Level(string table, IReadOnlyList<long> ids, int depth, bool isRoot)
            {
                Table = table;
                Ids = ids;
                Depth = depth;
                IsRoot = isRoot;
            }
            public string Table { get; }
            public IReadOnlyList<long> Ids { get; }
            public int Depth { get; }
            public bool IsRoot { get; }
        }

        public RollbackOutcome Rollback(ImportBatchInfo batch,
                                        IReadOnlyList<ImportedRowRef> rows,
                                        bool anyApproved,
                                        Func<string, string, IReadOnlyList<long>, IReadOnlyList<long>> childIds,
                                        Action<string, IReadOnlyList<long>> deleteByIds)
        {
            if (batch == null) throw new ArgumentNullException(nameof(batch));
            if (rows == null) throw new ArgumentNullException(nameof(rows));
            if (childIds == null) throw new ArgumentNullException(nameof(childIds));
            if (deleteByIds == null) throw new ArgumentNullException(nameof(deleteByIds));

            var outcome = new RollbackOutcome();

            if (string.Equals(batch.Status, "ROLLED_BACK", StringComparison.Ordinal))
            {
                outcome.Refusals.Add("این دسته قبلاً برگشت خورده است");
                return outcome;
            }

            if (anyApproved)
            {
                // Refuse rather than cascade: an approved document is immutable
                // and a correction must be a reversal document, not a delete.
                outcome.Refusals.Add(
                    "برگشت ممکن نیست: اسناد تأییدشده‌ای در این دسته وجود دارند. " +
                    "اصلاح باید با سند معکوس انجام شود، نه حذف.");
                return outcome;
            }

            var plan = RollbackPlan(batch.DetectedType);
            if (plan.Count == 0)
            {
                outcome.Refusals.Add("ترتیب حذف برای قالب " + batch.DetectedType + " تعریف نشده است");
                return outcome;
            }

            foreach (var row in rows.Where(r => r.NewId.HasValue))
            {
                var rootId = row.NewId.Value;

                // pass 1: collect, forwards
                var levels = new List<Level>();
                var collected = new Dictionary<string, IReadOnlyList<long>>(StringComparer.Ordinal);
                var depthOf = new Dictionary<string, int>(StringComparer.Ordinal);

                foreach (var step in plan)
                {
                    var table = step.Item1;
                    var column = step.Item2;
                    var parent = step.Item3;

                    IReadOnlyList<long> candidate = parent == null
                        ? new[] { rootId }
                        : (collected.ContainsKey(parent) ? collected[parent] : new long[0]);
                    if (candidate.Count == 0) continue;

                    IReadOnlyList<long> found = column == "id"
                        ? candidate
                        : childIds(table, column, candidate);
                    if (found.Count == 0) continue;

                    var depth = parent == null ? 0
                        : (depthOf.ContainsKey(parent) ? depthOf[parent] : 0) + 1;
                    depthOf[table] = depth;
                    collected[table] = found;
                    levels.Add(new Level(table, found, depth, column == "id"));
                }

                // pass 2: delete, deepest first; a parent never dies before
                // its lines, and the root document is always last.
                foreach (var level in levels
                             .OrderByDescending(l => l.Depth)
                             .ThenByDescending(l => l.IsRoot))
                {
                    deleteByIds(level.Table, level.Ids);
                }
                outcome.Deleted++;
            }

            outcome.Succeeded = true;
            return outcome;
        }

        public static string FileSha256(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
            {
                var hash = sha.ComputeHash(stream);
                var sb = new StringBuilder(hash.Length * 2);
                foreach (var b in hash) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }
    }
}
