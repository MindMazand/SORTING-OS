using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace Mazandasht.Application
{
    /// <summary>Backup manifest (Spec ch. 16): SHA-256, schema version,
    /// time, integrity result. The live DB never sits in a sync folder;
    /// backups may target local/external/Google Drive Sync folders.</summary>
    public sealed class BackupManifest
    {
        public string Code { get; set; } = "";
        public string BackupType { get; set; } = "MANUAL";
        public string FilePath { get; set; } = "";
        public string Sha256 { get; set; } = "";
        public int SchemaVersion { get; set; }
        public string IntegrityResult { get; set; } = "";
        public DateTime CreatedAtUtc { get; set; }
        public string ToJson() =>
            "{\"code\":\"" + Code + "\",\"type\":\"" + BackupType + "\",\"file\":\"" +
            FilePath + "\",\"sha256\":\"" + Sha256 + "\",\"schema\":" + SchemaVersion +
            ",\"integrity\":\"" + IntegrityResult + "\",\"at\":\"" +
            CreatedAtUtc.ToString("o") + "\"}";
    }

    public static class BackupService
    {
        public static string ComputeSha256(string filePath)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(filePath))
            {
                var hash = sha.ComputeHash(stream);
                var sb = new StringBuilder(hash.Length * 2);
                foreach (var b in hash) sb.Append(b.ToString("x2"));
                return sb.ToString();
            }
        }

        public static BackupManifest CreateManifest(string code, string backupType,
                                                    string filePath, int schemaVersion,
                                                    string integrityResult)
        {
            return new BackupManifest
            {
                Code = code,
                BackupType = backupType,
                FilePath = filePath,
                Sha256 = ComputeSha256(filePath),
                SchemaVersion = schemaVersion,
                IntegrityResult = integrityResult,
                CreatedAtUtc = DateTime.UtcNow
            };
        }

        /// <summary>Verify a backup file against its manifest hash.</summary>
        public static bool Verify(string filePath, string expectedSha256)
        {
            if (!File.Exists(filePath)) return false;
            return string.Equals(ComputeSha256(filePath), expectedSha256,
                                 StringComparison.OrdinalIgnoreCase);
        }
    }
}
