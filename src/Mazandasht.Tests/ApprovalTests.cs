using System;
using Mazandasht.Domain;
using Xunit;

namespace Mazandasht.Tests
{
    public class ApprovalTests
    {
        [Fact]
        public void Draft_CanGoToReview()
        {
            Assert.True(ApprovalWorkflow.CanTransition(DocumentStatus.Draft, DocumentStatus.Review));
        }

        [Fact]
        public void Review_CanBeApproved()
        {
            Assert.True(ApprovalWorkflow.CanTransition(DocumentStatus.Review, DocumentStatus.Approved));
        }

        [Fact]
        public void Approved_IsImmutableExceptVoid()
        {
            Assert.True(ApprovalWorkflow.IsImmutable(DocumentStatus.Approved));
            Assert.True(ApprovalWorkflow.CanTransition(DocumentStatus.Approved, DocumentStatus.Voided));
            Assert.False(ApprovalWorkflow.CanTransition(DocumentStatus.Approved, DocumentStatus.Draft));
        }

        [Fact]
        public void Void_RequiresReason()
        {
            Assert.Throws<ArgumentException>(() =>
                ApprovalWorkflow.EnsureTransition(DocumentStatus.Review, DocumentStatus.Voided, ""));
        }

        [Fact]
        public void Voided_IsTerminal()
        {
            Assert.False(ApprovalWorkflow.CanTransition(DocumentStatus.Voided, DocumentStatus.Draft));
        }
    }
}
