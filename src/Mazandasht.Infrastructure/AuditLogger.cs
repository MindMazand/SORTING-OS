namespace Mazandasht.Infrastructure
{
    /// <summary>One audit event (Spec ch. 10): every sensitive action is logged.</summary>
    public sealed class AuditEvent
    {
        public long? UserId { get; set; }
        public string Action { get; set; } = "";      // CREATE/UPDATE/APPROVE/VOID/LOGIN/RESET/BACKUP/...
        public string EntityType { get; set; } = "";
        public long? EntityId { get; set; }
        public string Details { get; set; } = "";
    }

    public interface IAuditLogger
    {
        void Log(AuditEvent evt);
    }
}
