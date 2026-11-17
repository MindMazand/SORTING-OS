using System;
using System.Collections.Generic;

namespace Mazandasht.Application
{
    /// <summary>Smart Excel/CSV import template (Spec ch. 14).</summary>
    public sealed class ImportTemplate
    {
        public string Code { get; set; } = "";
        public string Name { get; set; } = "";
        public string[] SheetNames { get; set; } = new string[0];
        public string[] HeaderMarkers { get; set; } = new string[0]; // header detection hints
        public string TargetType { get; set; } = "";                 // e.g. PARTIES / WEIGH_TICKETS
        public Dictionary<string, string> ColumnMap { get; set; } = new Dictionary<string, string>();
    }

    /// <summary>
    /// Extensible registry: new import templates can be added without wide
    /// code changes (Spec ch. 14). Final import requires manager approval
    /// and is rollback-capable via import_batches.
    /// </summary>
    public sealed class ImportRegistry
    {
        private readonly Dictionary<string, ImportTemplate> _templates =
            new Dictionary<string, ImportTemplate>();

        public void Register(ImportTemplate template)
        {
            if (template == null) throw new ArgumentNullException(nameof(template));
            _templates[template.Code] = template;
        }

        public bool TryGet(string code, out ImportTemplate template) =>
            _templates.TryGetValue(code, out template);

        public IReadOnlyCollection<ImportTemplate> All => _templates.Values;

        /// <summary>Built-in templates mirroring the Excel workbooks (Spec ch. 4-5).</summary>
        public static ImportRegistry WithBuiltIns()
        {
            var r = new ImportRegistry();
            r.Register(new ImportTemplate
            {
                Code = "INFO_PARTIES", Name = "INFO.xlsx - Accounts",
                SheetNames = new[] { "Accounts" },
                HeaderMarkers = new[] { "کد", "نام صاحب حساب" },
                TargetType = "PARTIES"
            });
            r.Register(new ImportTemplate
            {
                Code = "BASKOL_WEIGH", Name = "Baskol.xlsx - Baskol",
                SheetNames = new[] { "Baskol" },
                HeaderMarkers = new[] { "وزن باسکول", "وزن خالص" },
                TargetType = "WEIGH_TICKETS"
            });
            r.Register(new ImportTemplate
            {
                Code = "TXN_BANK", Name = "Transactions.xlsx - Entry",
                SheetNames = new[] { "Entry" },
                HeaderMarkers = new[] { "مبلغ واریز", "مبلغ برداشت" },
                TargetType = "BANK_TRANSACTIONS"
            });
            return r;
        }
    }
}
