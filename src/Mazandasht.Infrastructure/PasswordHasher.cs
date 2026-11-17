using System;
using System.Security.Cryptography;

namespace Mazandasht.Infrastructure
{
    /// <summary>
    /// Password hashing with PBKDF2-HMAC-SHA256 and an independent salt per
    /// user (Spec ch. 10). Plaintext passwords are never stored.
    /// </summary>
    public static class PasswordHasher
    {
        public const int SaltSizeBytes = 32;
        public const int HashSizeBytes = 32;
        public const int Iterations = 100000;

        public static string Hash(string password, out string saltBase64)
        {
            if (string.IsNullOrEmpty(password)) throw new ArgumentException("Password is required.", nameof(password));
            var salt = new byte[SaltSizeBytes];
            using (var rng = RandomNumberGenerator.Create())
                rng.GetBytes(salt);
            saltBase64 = Convert.ToBase64String(salt);
            using (var pbkdf2 = new Rfc2898DeriveBytes(password, salt, Iterations, HashAlgorithmName.SHA256))
            {
                return Convert.ToBase64String(pbkdf2.GetBytes(HashSizeBytes));
            }
        }

        public static bool Verify(string password, string saltBase64, string expectedHashBase64)
        {
            if (string.IsNullOrEmpty(password) || string.IsNullOrEmpty(saltBase64) || string.IsNullOrEmpty(expectedHashBase64))
                return false;
            var salt = Convert.FromBase64String(saltBase64);
            using (var pbkdf2 = new Rfc2898DeriveBytes(password, salt, Iterations, HashAlgorithmName.SHA256))
            {
                var actual = pbkdf2.GetBytes(HashSizeBytes);
                return FixedTimeEquals(actual, Convert.FromBase64String(expectedHashBase64));
            }
        }

        // CryptographicOperations is not available on .NET Framework 4.8.
        internal static bool FixedTimeEquals(byte[] a, byte[] b)
        {
            if (a == null || b == null || a.Length != b.Length) return false;
            var diff = 0;
            for (var i = 0; i < a.Length; i++) diff |= a[i] ^ b[i];
            return diff == 0;
        }
    }
}
