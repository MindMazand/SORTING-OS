using System;
using System.Security.Cryptography;

namespace Mazandasht.Infrastructure
{
    /// <summary>
    /// Per-user private key: 32 random bytes (Spec ch. 10). Only the hash is
    /// stored; the raw key is shown once at creation and never again.
    /// Keys can be revoked and re-issued.
    /// </summary>
    public static class KeyGenerator
    {
        public const int KeySizeBytes = 32;

        public static string GenerateRawKey(out string keyHashBase64, out string keyPrefix)
        {
            var bytes = new byte[KeySizeBytes];
            using (var rng = RandomNumberGenerator.Create())
                rng.GetBytes(bytes);
            var raw = Convert.ToBase64String(bytes);
            using (var sha = SHA256.Create())
            {
                keyHashBase64 = Convert.ToBase64String(sha.ComputeHash(bytes));
            }
            keyPrefix = raw.Length >= 8 ? raw.Substring(0, 8) : raw;
            return raw; // show once, store only the hash
        }

        public static bool Verify(string rawKey, string storedHashBase64)
        {
            if (string.IsNullOrEmpty(rawKey) || string.IsNullOrEmpty(storedHashBase64)) return false;
            byte[] bytes;
            try { bytes = Convert.FromBase64String(rawKey); }
            catch (FormatException) { return false; }
            using (var sha = SHA256.Create())
            {
                var hash = sha.ComputeHash(bytes);
                return PasswordHasher.FixedTimeEquals(
                    hash, Convert.FromBase64String(storedHashBase64));
            }
        }
    }
}
