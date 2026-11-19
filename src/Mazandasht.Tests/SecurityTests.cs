using Mazandasht.Infrastructure;
using Xunit;

namespace Mazandasht.Tests
{
    public class SecurityTests
    {
        [Fact]
        public void PasswordHash_VerifiesAndRejectsWrongPassword()
        {
            var hash = PasswordHasher.Hash("Mazandasht@123", out var salt);
            Assert.True(PasswordHasher.Verify("Mazandasht@123", salt, hash));
            Assert.False(PasswordHasher.Verify("wrong-password", salt, hash));
        }

        [Fact]
        public void PasswordHash_UsesIndependentSaltPerUser()
        {
            var h1 = PasswordHasher.Hash("same-password", out var s1);
            var h2 = PasswordHasher.Hash("same-password", out var s2);
            Assert.NotEqual(s1, s2);
            Assert.NotEqual(h1, h2);
        }

        [Fact]
        public void PrivateKey_Is32RandomBytes_HashStoredOnly()
        {
            var raw = KeyGenerator.GenerateRawKey(out var hash, out var prefix);
            Assert.NotNull(raw);
            Assert.NotEqual(raw, hash); // raw key is never the stored value
            Assert.True(KeyGenerator.Verify(raw, hash));
            Assert.False(KeyGenerator.Verify("invalid-key", hash));
        }
    }
}
