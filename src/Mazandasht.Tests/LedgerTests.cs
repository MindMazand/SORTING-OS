using System;
using System.Collections.Generic;
using Mazandasht.Domain;
using Xunit;

namespace Mazandasht.Tests
{
    public class LedgerTests
    {
        private static List<JournalLineInput> Balanced() => new List<JournalLineInput>
        {
            new JournalLineInput { AccountId = 1, Debit = Money.FromRial(100000) },
            new JournalLineInput { AccountId = 2, Credit = Money.FromRial(100000) }
        };

        [Fact]
        public void BalancedEntry_PassesValidation()
        {
            LedgerRules.ValidateBalanced(Balanced());
            Assert.True(LedgerRules.IsBalanced(Balanced()));
        }

        [Fact]
        public void UnbalancedEntry_IsRejected()
        {
            var lines = Balanced();
            lines[1].Credit = Money.FromRial(99999);
            Assert.Throws<InvalidOperationException>(() => LedgerRules.ValidateBalanced(lines));
            Assert.False(LedgerRules.IsBalanced(lines));
        }

        [Fact]
        public void SingleLineEntry_IsRejected()
        {
            var lines = new List<JournalLineInput>
            {
                new JournalLineInput { AccountId = 1, Debit = Money.FromRial(100) }
            };
            Assert.Throws<InvalidOperationException>(() => LedgerRules.ValidateBalanced(lines));
        }

        [Fact]
        public void DebitAndCreditOnSameLine_IsRejected()
        {
            var lines = new List<JournalLineInput>
            {
                new JournalLineInput { AccountId = 1, Debit = Money.FromRial(100), Credit = Money.FromRial(100) },
                new JournalLineInput { AccountId = 2, Credit = Money.FromRial(100) }
            };
            Assert.Throws<InvalidOperationException>(() => LedgerRules.ValidateBalanced(lines));
        }
    }
}
