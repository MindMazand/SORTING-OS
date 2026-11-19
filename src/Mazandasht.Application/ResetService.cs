using System;

namespace Mazandasht.Application
{
    /// <summary>
    /// Database Reset (Spec ch. 15): admin-only, mandatory backup first,
    /// explicit confirmation phrase, then the DB file is replaced with a
    /// fresh schema+seed database. Operational data disappears; base
    /// definitions (banks, units, groups, operations, parameters) remain.
    /// Operators never have the db.reset permission.
    /// </summary>
    public static class ResetService
    {
        public const string ConfirmationPhrase = "RESET MAZANDASHT";

        public static void EnsureConfirmed(string phrase)
        {
            if (!string.Equals(phrase, ConfirmationPhrase, StringComparison.Ordinal))
                throw new InvalidOperationException(
                    "Reset requires the exact confirmation phrase: " + ConfirmationPhrase);
        }

        public static void EnsureBackupExists(bool backupCreated)
        {
            if (!backupCreated)
                throw new InvalidOperationException("A backup is mandatory before Reset.");
        }
    }
}
