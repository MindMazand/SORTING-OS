using System;
using System.Collections.Generic;
using System.Data.SQLite;
using System.Globalization;
using System.Linq;
using Mazandasht.Application.Import;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// Persists the import batch (audit trail) and links each created document
    /// back to its source row so a rollback can delete exactly those rows.
    ///
    /// Two deliberate choices:
    ///   * A batch row is written even when every row of the file is invalid.
    ///     The owner needs to see WHY a file was refused, and a batch that
    ///     disappears on failure teaches them nothing.
    ///   * `mapped_json` stores {"new_id": n}, not the whole mapping. It is a
    ///     pointer for rollback, and a pointer that also carried the data would
    ///     go stale the moment the document is edited.
    /// </summary>
    public sealed class SqliteImportBatchStore : IImportBatchStore
    {
        private readonly SQLiteConnection _connection;

        public SqliteImportBatchStore(string connectionString)
        {
            _connection = new SQLiteConnection(connectionString);
            _connection.Open();
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "PRAGMA foreign_keys = ON";
                cmd.ExecuteNonQuery();
            }
        }

        public string NextBatchCode()
        {
            // IMP-20261117-143005-0001: sortable, greppable, and unique even
            // when two files are imported in the same second.
            var stamp = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture);
            var prefix = "IMP-" + stamp + "-";
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT COUNT(*) FROM import_batches WHERE code LIKE @p";
                cmd.Parameters.AddWithValue("@p", prefix + "%");
                var n = Convert.ToInt64(cmd.ExecuteScalar());
                return prefix + (n + 1).ToString("0000", CultureInfo.InvariantCulture);
            }
        }

        public long CreateBatch(ImportBatchInfo info, string fileSha256, int headerRow,
                                int headerRowSecond, string profileCode)
        {
            if (info == null) throw new ArgumentNullException(nameof(info));
            if (string.IsNullOrEmpty(info.Code))
                throw new ArgumentException("batch code is required", nameof(info));

            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "INSERT INTO import_batches " +
                    "(code, file_name, file_type, detected_type, header_row, header_row_second, " +
                    " file_sha256, profile_code, status, total_rows, valid_rows, " +
                    " duplicate_rows, invalid_rows) " +
                    "VALUES (@code,@file,'XLSX',@type,@h1,@h2,@sha,@profile,@status,@total,@valid,@dup,@invalid); " +
                    "SELECT last_insert_rowid();";
                cmd.Parameters.AddWithValue("@code", info.Code);
                cmd.Parameters.AddWithValue("@file", info.FileName ?? "");
                cmd.Parameters.AddWithValue("@type", info.DetectedType ?? "");
                cmd.Parameters.AddWithValue("@h1", headerRow);
                cmd.Parameters.AddWithValue("@h2", headerRowSecond);
                cmd.Parameters.AddWithValue("@sha", fileSha256 ?? "");
                cmd.Parameters.AddWithValue("@profile", (object)profileCode ?? DBNull.Value);
                cmd.Parameters.AddWithValue("@status", info.Status ?? "REVIEW");
                cmd.Parameters.AddWithValue("@total", info.TotalRows);
                cmd.Parameters.AddWithValue("@valid", info.ValidRows);
                cmd.Parameters.AddWithValue("@dup", info.DuplicateRows);
                cmd.Parameters.AddWithValue("@invalid", info.InvalidRows);
                return Convert.ToInt64(cmd.ExecuteScalar());
            }
        }

        public long AddRow(long batchId, int sourceRow, string rawJson, string mappedJson,
                           string blankFieldsJson, string status, string errorMessage)
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "INSERT INTO import_rows " +
                    "(batch_id, row_number, source_row_number, raw_json, mapped_json, " +
                    " blank_fields_json, status, error_message) " +
                    "VALUES (@b,@r,@sr,@raw,@mapped,@blank,@status,@err); " +
                    "SELECT last_insert_rowid();";
                cmd.Parameters.AddWithValue("@b", batchId);
                cmd.Parameters.AddWithValue("@r", sourceRow);
                cmd.Parameters.AddWithValue("@sr", sourceRow);
                cmd.Parameters.AddWithValue("@raw", rawJson ?? "");
                cmd.Parameters.AddWithValue("@mapped", mappedJson ?? "");
                cmd.Parameters.AddWithValue("@blank", (object)blankFieldsJson ?? DBNull.Value);
                cmd.Parameters.AddWithValue("@status", status ?? "PENDING");
                cmd.Parameters.AddWithValue("@err", Truncate(errorMessage, 900));
                return Convert.ToInt64(cmd.ExecuteScalar());
            }
        }

        public void MarkRowImported(long importRowId, long newId)
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "UPDATE import_rows SET status='IMPORTED', mapped_json=@m WHERE id=@id";
                cmd.Parameters.AddWithValue("@m",
                    "{\"new_id\":" + newId.ToString(CultureInfo.InvariantCulture) + "}");
                cmd.Parameters.AddWithValue("@id", importRowId);
                cmd.ExecuteNonQuery();
            }
        }

        public void MarkRowInvalid(long importRowId, string errorMessage)
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "UPDATE import_rows SET status='INVALID', error_message=@e WHERE id=@id";
                cmd.Parameters.AddWithValue("@e", Truncate(errorMessage, 900));
                cmd.Parameters.AddWithValue("@id", importRowId);
                cmd.ExecuteNonQuery();
            }
        }

        /// <summary>Load a batch for rollback.</summary>
        public ImportBatchInfo GetBatch(long batchId)
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "SELECT id, code, file_name, detected_type, status, total_rows, " +
                    "       valid_rows, duplicate_rows, invalid_rows " +
                    "FROM import_batches WHERE id=@id";
                cmd.Parameters.AddWithValue("@id", batchId);
                using (var r = cmd.ExecuteReader())
                {
                    if (!r.Read()) return null;
                    return new ImportBatchInfo
                    {
                        Id = r.GetInt64(0),
                        Code = r.GetString(1),
                        FileName = r.GetString(2),
                        DetectedType = r.GetString(3),
                        Status = r.GetString(4),
                        TotalRows = r.GetInt32(5),
                        ValidRows = r.GetInt32(6),
                        DuplicateRows = r.GetInt32(7),
                        InvalidRows = r.GetInt32(8),
                    };
                }
            }
        }

        public IReadOnlyList<ImportedRowRef> GetImportedRows(long batchId)
        {
            var list = new List<ImportedRowRef>();
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "SELECT id, source_row_number, status, mapped_json FROM import_rows " +
                    "WHERE batch_id=@b AND status='IMPORTED' ORDER BY source_row_number";
                cmd.Parameters.AddWithValue("@b", batchId);
                using (var r = cmd.ExecuteReader())
                {
                    while (r.Read())
                    {
                        long? newId = null;
                        var mapped = r.IsDBNull(3) ? "" : r.GetString(3);
                        var marker = mapped.IndexOf("\"new_id\":", StringComparison.Ordinal);
                        if (marker >= 0)
                        {
                            var digits = new string(mapped.Substring(marker + 9)
                                .SkipWhile(c => !char.IsDigit(c) && c != '-')
                                .TakeWhile(c => char.IsDigit(c) || c == '-').ToArray());
                            long parsed;
                            if (long.TryParse(digits, out parsed)) newId = parsed;
                        }
                        list.Add(new ImportedRowRef
                        {
                            ImportRowId = r.GetInt64(0),
                            SourceRow = r.IsDBNull(1) ? 0 : r.GetInt32(1),
                            Status = r.GetString(2),
                            NewId = newId,
                        });
                    }
                }
            }
            return list;
        }

        /// <summary>True when any document this batch created is no longer a
        /// draft. Rollback must refuse in that case.</summary>
        public bool AnyApproved(ImportBatchInfo batch)
        {
            if (batch == null) return false;
            var table = DocumentTable(batch.DetectedType);
            if (table == null) return false;
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "SELECT COUNT(*) FROM " + table + " WHERE status='APPROVED'";
                return Convert.ToInt64(cmd.ExecuteScalar()) > 0;
            }
        }

        private static string DocumentTable(string templateCode)
        {
            switch (templateCode)
            {
                case "WEIGHING_IN": return "weigh_tickets";
                case "PURCHASE_INVOICES": return "purchase_invoices";
                case "SALES_INVOICES": return "sales_invoices";
                case "SORTING": return "sorting_batches";
                case "BANK_TRANSACTIONS": return "bank_transactions";
                default: return null;
            }
        }

        /// <summary>Children of a set of parent ids, for the rollback plan.</summary>
        public IReadOnlyList<long> ChildIds(string table, string column,
                                           IReadOnlyList<long> parentIds)
        {
            if (parentIds == null || parentIds.Count == 0) return new long[0];
            var marks = string.Join(",", parentIds.Select((_, i) => "@p" + i));
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "SELECT id FROM " + table + " WHERE " + column +
                                  " IN (" + marks + ")";
                for (var i = 0; i < parentIds.Count; i++)
                    cmd.Parameters.AddWithValue("@p" + i, parentIds[i]);
                var ids = new List<long>();
                using (var r = cmd.ExecuteReader())
                    while (r.Read()) ids.Add(r.GetInt64(0));
                return ids;
            }
        }

        public void DeleteByIds(string table, IReadOnlyList<long> ids)
        {
            if (ids == null || ids.Count == 0) return;
            var marks = string.Join(",", ids.Select((_, i) => "@p" + i));
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText = "DELETE FROM " + table + " WHERE id IN (" + marks + ")";
                for (var i = 0; i < ids.Count; i++)
                    cmd.Parameters.AddWithValue("@p" + i, ids[i]);
                cmd.ExecuteNonQuery();
            }
        }

        public void MarkBatchRolledBack(long batchId)
        {
            using (var cmd = _connection.CreateCommand())
            {
                cmd.CommandText =
                    "UPDATE import_batches SET status='ROLLED_BACK' WHERE id=@id";
                cmd.Parameters.AddWithValue("@id", batchId);
                cmd.ExecuteNonQuery();
            }
        }

        private static string Truncate(string text, int max)
        {
            if (string.IsNullOrEmpty(text)) return "";
            return text.Length <= max ? text : text.Substring(0, max);
        }
    }
}
