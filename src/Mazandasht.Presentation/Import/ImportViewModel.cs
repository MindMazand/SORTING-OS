using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using Mazandasht.Application.Import;

namespace Mazandasht.Presentation.Import
{
    /// <summary>One importable template, as the owner sees it.</summary>
    public sealed class TemplateChoice
    {
        public string Code { get; set; }
        public string FileName { get; set; }
        public string ModuleFa { get; set; }

        /// <summary>"01_Parties.xlsx — اشخاص"</summary>
        public string Display
        {
            get { return FileName + " — " + ModuleFa; }
        }
    }

    /// <summary>A row of the preview grid.</summary>
    public sealed class PreviewRow
    {
        public int SourceRow { get; set; }
        public string StatusText { get; set; }
        public bool Ok { get; set; }
        public string Summary { get; set; }
        public string Blanks { get; set; }
    }

    /// <summary>A row of the batch history.</summary>
    public sealed class BatchRow
    {
        public long Id { get; set; }
        public string Code { get; set; }
        public string FileName { get; set; }
        public string TemplateFa { get; set; }
        public string Status { get; set; }
        public string StatusFa { get; set; }
        public string Counts { get; set; }
        public bool CanRollback { get; set; }
    }

    /// <summary>
    /// The import centre's view model.
    ///
    /// THE ONE RULE THIS CLASS EXISTS TO ENFORCE
    ///
    /// Preview is the default; commit is a second, explicit action whose button
    /// says how many rows it will write and how many will be rejected. The
    /// owner's standard is "upload is not commit". A UI that commits on
    /// file-select makes that standard a comment in a document.
    ///
    /// Everything else here is presentation. Not one line parses a file or
    /// writes a row: ImportEngine and ImportRunner do that, and they are the
    /// parts with 39 executing tests.
    /// </summary>
    public sealed class ImportViewModel : INotifyPropertyChanged
    {
        private readonly Func<string, string, ImportRunner.RunResult> _preview;
        private readonly Func<string, string, ImportRunner.RunResult> _commit;
        private readonly Func<int, IReadOnlyList<ImportBatchInfo>> _recent;
        private readonly Func<long, RollbackOutcome> _rollback;

        private string _filePath = "";
        private TemplateChoice _selectedTemplate;
        private string _statusMessage = "";
        private string _fileSummary = "";
        private bool _hasPreview;
        private bool _canCommit;
        private string _commitButtonText = "ثبت در پایگاه داده";
        private int _validCount;
        private int _invalidCount;

        public event PropertyChangedEventHandler PropertyChanged;

        public ObservableCollection<TemplateChoice> Templates { get; private set; }
        public ObservableCollection<PreviewRow> PreviewRows { get; private set; }
        public ObservableCollection<BatchRow> Batches { get; private set; }

        /// <summary>
        /// The four operations are injected as delegates rather than taken as
        /// an ImportService instance. Reason: the view model then has no
        /// reference to Persistence, so it can be tested against fakes without
        /// a database file, and the window cannot accidentally reach around it.
        /// </summary>
        public ImportViewModel(
            Func<string, string, ImportRunner.RunResult> preview,
            Func<string, string, ImportRunner.RunResult> commit,
            Func<int, IReadOnlyList<ImportBatchInfo>> recent,
            Func<long, RollbackOutcome> rollback)
        {
            if (preview == null) throw new ArgumentNullException("preview");
            if (commit == null) throw new ArgumentNullException("commit");
            if (recent == null) throw new ArgumentNullException("recent");
            if (rollback == null) throw new ArgumentNullException("rollback");

            _preview = preview;
            _commit = commit;
            _recent = recent;
            _rollback = rollback;

            Templates = new ObservableCollection<TemplateChoice>();
            PreviewRows = new ObservableCollection<PreviewRow>();
            Batches = new ObservableCollection<BatchRow>();
        }

        public string FilePath
        {
            get { return _filePath; }
            private set
            {
                if (_filePath == value) return;
                _filePath = value;
                Raise("FilePath");
                Raise("HasFile");
            }
        }

        public bool HasFile
        {
            get { return !string.IsNullOrEmpty(_filePath); }
        }

        public TemplateChoice SelectedTemplate
        {
            get { return _selectedTemplate; }
            set
            {
                if (ReferenceEquals(_selectedTemplate, value)) return;
                _selectedTemplate = value;
                Raise("SelectedTemplate");
                Raise("HasTemplate");
            }
        }

        public bool HasTemplate
        {
            get { return _selectedTemplate != null; }
        }

        public string StatusMessage
        {
            get { return _statusMessage; }
            private set
            {
                if (_statusMessage == value) return;
                _statusMessage = value;
                Raise("StatusMessage");
            }
        }

        public string FileSummary
        {
            get { return _fileSummary; }
            private set
            {
                if (_fileSummary == value) return;
                _fileSummary = value;
                Raise("FileSummary");
            }
        }

        public bool HasPreview
        {
            get { return _hasPreview; }
            private set
            {
                if (_hasPreview == value) return;
                _hasPreview = value;
                Raise("HasPreview");
            }
        }

        public bool CanCommit
        {
            get { return _canCommit; }
            private set
            {
                if (_canCommit == value) return;
                _canCommit = value;
                Raise("CanCommit");
            }
        }

        public string CommitButtonText
        {
            get { return _commitButtonText; }
            private set
            {
                if (_commitButtonText == value) return;
                _commitButtonText = value;
                Raise("CommitButtonText");
            }
        }

        public int ValidCount
        {
            get { return _validCount; }
            private set { _validCount = value; Raise("ValidCount"); }
        }

        public int InvalidCount
        {
            get { return _invalidCount; }
            private set { _invalidCount = value; Raise("InvalidCount"); }
        }

        public void LoadTemplates(IEnumerable<TemplateChoice> templates)
        {
            Templates.Clear();
            foreach (TemplateChoice t in templates) Templates.Add(t);
        }

        public void ChooseFile(string path)
        {
            FilePath = path ?? "";
            // A new file invalidates the previous preview. Leaving the old
            // preview on screen with a new path in the box is how someone
            // commits the wrong file.
            PreviewRows.Clear();
            HasPreview = false;
            CanCommit = false;
            CommitButtonText = "ثبت در پایگاه داده";
            ValidCount = 0;
            InvalidCount = 0;
            FileSummary = path == null ? "" : Path.GetFileName(path);
            StatusMessage = "فایل انتخاب شد. برای دیدن نتیجه، «بررسی فایل» را بزنید — "
                + "هیچ چیز هنوز ثبت نشده است.";
        }

        /// <summary>
        /// Parse and report. Writes nothing, and says so.
        /// </summary>
        public void RunPreview()
        {
            if (!HasFile || SelectedTemplate == null)
            {
                StatusMessage = "ابتدا فایل و قالب را انتخاب کنید.";
                return;
            }

            try
            {
                ImportRunner.RunResult result = _preview(FilePath, SelectedTemplate.Code);
                PreviewRows.Clear();

                if (result.Parse == null)
                {
                    StatusMessage = "فایل خوانده نشد.";
                    HasPreview = false;
                    CanCommit = false;
                    return;
                }

                foreach (string err in result.Parse.FileErrors)
                {
                    PreviewRows.Add(new PreviewRow
                    {
                        SourceRow = 0,
                        StatusText = "خطای فایل",
                        Ok = false,
                        Summary = err,
                        Blanks = "",
                    });
                }

                var valid = 0;
                var invalid = 0;
                foreach (ParsedRow row in result.Parse.Rows)
                {
                    var messages = new List<string>();
                    foreach (RowIssue e in row.Errors) messages.Add(e.Message);
                    if (row.Ok) valid++; else invalid++;
                    PreviewRows.Add(new PreviewRow
                    {
                        SourceRow = row.SourceRow,
                        StatusText = row.Ok ? "درست" : "خطا",
                        Ok = row.Ok,
                        Summary = messages.Count == 0 ? "" : string.Join(" | ", messages),
                        Blanks = string.Join("، ", row.Blanks),
                    });
                }

                ValidCount = valid;
                InvalidCount = invalid;
                HasPreview = result.Parse.Rows.Count > 0;

                // Committing with zero valid rows would create an empty batch
                // row and teach the owner nothing. Disabled, with the reason.
                CanCommit = valid > 0;
                CommitButtonText = valid > 0
                    ? "ثبت " + valid.ToString("N0", CultureInfo.InvariantCulture) + " ردیف درست"
                    : "چیزی برای ثبت نیست";

                string sheet = result.Parse.SheetName;
                FileSummary = Path.GetFileName(FilePath) + " · شیت: " + sheet
                    + " · " + result.Parse.Rows.Count.ToString("N0", CultureInfo.InvariantCulture) + " ردیف"
                    + " · " + valid.ToString("N0", CultureInfo.InvariantCulture) + " درست"
                    + " · " + invalid.ToString("N0", CultureInfo.InvariantCulture) + " خطا";

                if (result.Parse.IgnoredBlankRows > 0)
                    FileSummary += " · " + result.Parse.IgnoredBlankRows + " ردیف خالی نادیده گرفته شد";

                StatusMessage = valid > 0
                    ? "پیش‌نمایش آماده است. هنوز هیچ چیز ثبت نشده. برای ثبت، دکمه «"
                      + CommitButtonText + "» را بزنید."
                    : "هیچ ردیف معتبری پیدا نشد. چیزی ثبت نخواهد شد.";
            }
            catch (Exception ex)
            {
                HasPreview = false;
                CanCommit = false;
                StatusMessage = "خطا در بررسی فایل: " + ex.Message;
            }
        }

        /// <summary>
        /// The explicit second step. Returns true when the batch was written.
        /// </summary>
        public bool RunCommit()
        {
            if (!CanCommit || SelectedTemplate == null) return false;

            try
            {
                ImportRunner.RunResult result = _commit(FilePath, SelectedTemplate.Code);
                if (result.BatchCode != null)
                {
                    StatusMessage = "ثبت شد. کد دسته: " + result.BatchCode
                        + " · " + ValidCount.ToString("N0", CultureInfo.InvariantCulture)
                        + " ردیف نوشته شد. برای برگشت از تاریخچه استفاده کنید.";
                    CanCommit = false;
                    CommitButtonText = "ثبت شد";
                    RefreshBatches();
                    return true;
                }
                StatusMessage = "ثبت انجام نشد: " + string.Join(" | ", result.Errors);
                return false;
            }
            catch (Exception ex)
            {
                StatusMessage = "خطا در ثبت: " + ex.Message;
                return false;
            }
        }

        /// <summary>
        /// Roll back one batch. The caller must already have asked the owner
        /// for confirmation: this method does not, because a view model cannot
        /// show a dialog and must not pretend to.
        /// </summary>
        public void RollbackBatch(BatchRow row)
        {
            if (row == null) return;
            if (!row.CanRollback)
            {
                StatusMessage = "این دسته قابل برگشت نیست: " + row.StatusFa;
                return;
            }

            try
            {
                RollbackOutcome outcome = _rollback(row.Id);
                if (outcome.Succeeded)
                {
                    StatusMessage = "دسته " + row.Code + " برگشت خورد · "
                        + outcome.Deleted.ToString("N0", CultureInfo.InvariantCulture)
                        + " سند حذف شد.";
                }
                else
                {
                    var parts = new List<string>();
                    parts.AddRange(outcome.Refusals);
                    parts.AddRange(outcome.Errors);
                    StatusMessage = "برگشت انجام نشد: " + string.Join(" | ", parts);
                }
                RefreshBatches();
            }
            catch (Exception ex)
            {
                StatusMessage = "خطا در برگشت: " + ex.Message;
            }
        }

        public void RefreshBatches()
        {
            try
            {
                IReadOnlyList<ImportBatchInfo> list = _recent(50);
                Batches.Clear();
                foreach (ImportBatchInfo b in list)
                {
                    Batches.Add(new BatchRow
                    {
                        Id = b.Id,
                        Code = b.Code,
                        FileName = b.FileName,
                        TemplateFa = TemplateName(b.DetectedType),
                        Status = b.Status,
                        StatusFa = StatusName(b.Status),
                        Counts = b.ValidRows.ToString("N0", CultureInfo.InvariantCulture)
                            + " درست · "
                            + b.InvalidRows.ToString("N0", CultureInfo.InvariantCulture)
                            + " خطا",
                        // Only a REVIEW batch can be rolled back. An approved
                        // one is immutable; a rolled-back one has nothing left.
                        CanRollback = b.Status == "REVIEW",
                    });
                }
            }
            catch (Exception ex)
            {
                StatusMessage = "خواندن تاریخچه ناموفق: " + ex.Message;
            }
        }

        /// <summary>
        /// Template code -> Persian module name. The mapping is written out
        /// rather than looked up so an unknown code shows its raw self instead
        /// of a blank cell — a blank template cell in an audit trail hides the
        /// one piece of information needed to investigate it.
        /// </summary>
        private static string TemplateName(string code)
        {
            switch (code)
            {
                case "PARTIES": return "اشخاص";
                case "PRODUCTS": return "محصولات";
                case "WEIGHING_IN": return "باسکول ورودی";
                case "PURCHASE_INVOICES": return "خرید";
                case "SALES_INVOICES": return "فروش";
                case "SORTING": return "سورتینگ";
                case "BASKET_MOVEMENTS": return "سبد";
                case "BANK_TRANSACTIONS": return "بانک";
                case "CHEQUES": return "چک";
                case "SETTLEMENTS": return "تسویه";
                case "PARTNERSHIP": return "شراکت";
                default: return code ?? "";
            }
        }

        private static string StatusName(string status)
        {
            switch (status)
            {
                case "REVIEW": return "منتظر تأیید";
                case "APPROVED": return "تأییدشده";
                case "ROLLED_BACK": return "برگشت‌خورده";
                case "FAILED": return "ناموفق";
                case "DRAFT": return "پیش‌نویس";
                default: return status ?? "";
            }
        }

        private void Raise(string name)
        {
            PropertyChangedEventHandler h = PropertyChanged;
            if (h != null) h(this, new PropertyChangedEventArgs(name));
        }
    }
}
