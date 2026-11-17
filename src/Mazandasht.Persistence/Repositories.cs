using System;
using System.Collections.Generic;
using System.Data.SQLite;
using Mazandasht.Domain;

namespace Mazandasht.Persistence
{
    /// <summary>
    /// SQLite repositories. All writes run inside transactions; money is
    /// bound as integer Rial and weight as integer grams (Spec ch. 2.1).
    /// Balances are always derived from ledgers, never stored directly.
    /// </summary>

    public sealed class PartyRepository
    {
        private readonly string _connectionString;
        public PartyRepository(string connectionString) => _connectionString = connectionString;

        public Party Create(Party party)
        {
            if (!PartyNature.IsValid(party.Nature))
                throw new ArgumentException("Invalid party nature: " + party.Nature);
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText =
                        "INSERT INTO parties (code, display_name, nature, national_code, phone, mobile, address, is_active) " +
                        "VALUES (@code, @name, @nature, @nat, @phone, @mobile, @addr, 1); " +
                        "SELECT last_insert_rowid();";
                    cmd.Parameters.AddWithValue("@code", party.Code);
                    cmd.Parameters.AddWithValue("@name", party.DisplayName);
                    cmd.Parameters.AddWithValue("@nature", party.Nature);
                    cmd.Parameters.AddWithValue("@nat", party.NationalCode ?? "");
                    cmd.Parameters.AddWithValue("@phone", party.Phone ?? "");
                    cmd.Parameters.AddWithValue("@mobile", party.Mobile ?? "");
                    cmd.Parameters.AddWithValue("@addr", party.Address ?? "");
                    party.Id = Convert.ToInt64(cmd.ExecuteScalar());
                }
            }
            return party;
        }

        public Party GetByCode(string code)
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText = "SELECT id, code, display_name, nature, is_active FROM parties WHERE code=@c";
                    cmd.Parameters.AddWithValue("@c", code);
                    using (var r = cmd.ExecuteReader())
                    {
                        if (!r.Read()) return null;
                        return new Party
                        {
                            Id = r.GetInt64(0),
                            Code = r.GetString(1),
                            DisplayName = r.GetString(2),
                            Nature = r.GetString(3),
                            IsActive = r.GetInt32(4) == 1
                        };
                    }
                }
            }
        }
    }

    public sealed class JournalRepository
    {
        private readonly string _connectionString;
        public JournalRepository(string connectionString) => _connectionString = connectionString;

        /// <summary>
        /// Atomic, idempotent posting: validates balance first, then writes
        /// entry + lines in one transaction. The UNIQUE source_key in the DB
        /// rejects duplicate postings.
        /// </summary>
        public JournalEntry Post(JournalEntry entry, IReadOnlyList<JournalLineInput> lines)
        {
            LedgerRules.ValidateBalanced(lines);
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var tx = con.BeginTransaction())
                {
                    using (var cmd = con.CreateCommand())
                    {
                        cmd.Transaction = tx;
                        cmd.CommandText =
                            "INSERT INTO journal_entries (code, doc_number, date_iso, date_shamsi, description, status, source_type, source_id, source_key, created_by) " +
                            "VALUES (@code, @doc, @d1, @d2, @desc, 'DRAFT', @st, @sid, @skey, @by); SELECT last_insert_rowid();";
                        cmd.Parameters.AddWithValue("@code", entry.Code);
                        cmd.Parameters.AddWithValue("@doc", entry.DocNumber ?? "");
                        cmd.Parameters.AddWithValue("@d1", entry.DateIso ?? "");
                        cmd.Parameters.AddWithValue("@d2", entry.DateShamsi ?? "");
                        cmd.Parameters.AddWithValue("@desc", entry.Description ?? "");
                        cmd.Parameters.AddWithValue("@st", entry.SourceType ?? "");
                        cmd.Parameters.AddWithValue("@sid", (object)entry.SourceId ?? DBNull.Value);
                        cmd.Parameters.AddWithValue("@skey", entry.SourceKey ?? "");
                        cmd.Parameters.AddWithValue("@by", (object)entry.CreatedBy ?? DBNull.Value);
                        entry.Id = Convert.ToInt64(cmd.ExecuteScalar());
                    }
                    foreach (var line in lines)
                    {
                        using (var cmd = con.CreateCommand())
                        {
                            cmd.Transaction = tx;
                            cmd.CommandText =
                                "INSERT INTO journal_lines (journal_id, account_id, debit_rial, credit_rial, description) " +
                                "VALUES (@j, @a, @d, @c, @desc)";
                            cmd.Parameters.AddWithValue("@j", entry.Id);
                            cmd.Parameters.AddWithValue("@a", line.AccountId);
                            cmd.Parameters.AddWithValue("@d", line.Debit.Rial);
                            cmd.Parameters.AddWithValue("@c", line.Credit.Rial);
                            cmd.Parameters.AddWithValue("@desc", line.Description ?? "");
                            cmd.ExecuteNonQuery();
                        }
                    }
                    tx.Commit();
                }
            }
            return entry;
        }

        /// <summary>Approve a journal entry (DRAFT/REVIEW -> APPROVED).</summary>
        public void Approve(long journalId, long approverUserId)
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText =
                        "UPDATE journal_entries SET status='APPROVED', approved_by=@by WHERE id=@id AND status IN ('DRAFT','REVIEW')";
                    cmd.Parameters.AddWithValue("@by", approverUserId);
                    cmd.Parameters.AddWithValue("@id", journalId);
                    if (cmd.ExecuteNonQuery() != 1)
                        throw new InvalidOperationException("Journal entry cannot be approved from its current state.");
                }
            }
        }
    }

    public sealed class StockRepository
    {
        private readonly string _connectionString;
        public StockRepository(string connectionString) => _connectionString = connectionString;

        public void AddMovement(StockMovement m)
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText =
                        "INSERT INTO stock_movements (lot_id, product_id, grade_id, packaging_id, warehouse_id, movement_type, quantity_grams, quantity_count, ref_type, ref_id) " +
                        "VALUES (@lot, @prod, @grade, @pack, @wh, @type, @grams, @count, @rt, @rid)";
                    cmd.Parameters.AddWithValue("@lot", (object)m.LotId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@prod", (object)m.ProductId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@grade", (object)m.GradeId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@pack", (object)m.PackagingId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@wh", (object)m.WarehouseId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@type", m.MovementType);
                    cmd.Parameters.AddWithValue("@grams", m.Quantity.Grams);
                    cmd.Parameters.AddWithValue("@count", m.QuantityCount);
                    cmd.Parameters.AddWithValue("@rt", m.RefType ?? "");
                    cmd.Parameters.AddWithValue("@rid", (object)m.RefId ?? DBNull.Value);
                    cmd.ExecuteNonQuery();
                }
            }
        }

        /// <summary>Detailed balance (per lot/grade/packaging/warehouse).</summary>
        public long DetailedBalanceGrams(long productId, long? gradeId, long? packagingId, long? warehouseId, long? lotId)
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText =
                        "SELECT COALESCE(balance_grams,0) FROM v_stock_balance " +
                        "WHERE product_id=@p AND grade_id IS @g AND packaging_id IS @pk AND warehouse_id IS @w AND lot_id IS @l";
                    cmd.Parameters.AddWithValue("@p", productId);
                    cmd.Parameters.AddWithValue("@g", (object)gradeId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@pk", (object)packagingId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@w", (object)warehouseId ?? DBNull.Value);
                    cmd.Parameters.AddWithValue("@l", (object)lotId ?? DBNull.Value);
                    var v = cmd.ExecuteScalar();
                    return v == null || v == DBNull.Value ? 0 : Convert.ToInt64(v);
                }
            }
        }

        /// <summary>Simple balance (per product, all lots/grades/warehouses).</summary>
        public long SimpleBalanceGrams(long productId)
        {
            using (var con = new SQLiteConnection(_connectionString))
            {
                con.Open();
                using (var cmd = con.CreateCommand())
                {
                    cmd.CommandText =
                        "SELECT COALESCE(SUM(CASE WHEN movement_type='IN' THEN quantity_grams " +
                        "WHEN movement_type='OUT' THEN -quantity_grams ELSE quantity_grams END),0) " +
                        "FROM stock_movements WHERE product_id=@p";
                    cmd.Parameters.AddWithValue("@p", productId);
                    return Convert.ToInt64(cmd.ExecuteScalar());
                }
            }
        }
    }
}
