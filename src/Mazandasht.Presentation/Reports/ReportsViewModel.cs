using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;

namespace Mazandasht.Presentation.Reports
{
    /// <summary>
    /// One report in the picker: what it is, and whether it can be opened.
    ///
    /// Availability is per report, not one flag for the screen. Six of the
    /// seven reports have a layout; the seventh does not, because the owner's
    /// own Financial.xlsx leaves that sheet empty and says the structure is
    /// awaiting their definition. Hiding it would be a lie of omission; making
    /// it look like the others would produce an empty table that reads as
    /// "no data this period".
    /// </summary>
    public sealed class ReportChoice : INotifyPropertyChanged
    {
        private bool _isAvailable;
        private string _unavailableReason;

        public string Id { get; set; }
        public string Title { get; set; }
        public string Description { get; set; }

        public bool IsAvailable
        {
            get { return _isAvailable; }
            set { _isAvailable = value; Raise("IsAvailable"); Raise("CanOpen"); }
        }

        public string UnavailableReason
        {
            get { return _unavailableReason; }
            set
            {
                _unavailableReason = value;
                Raise("UnavailableReason");
                Raise("HasReason");
            }
        }

        /// <summary>Bound to IsEnabled. A card you cannot open must not look
        /// openable, and must say why rather than doing nothing.</summary>
        public bool CanOpen { get { return _isAvailable; } }
        public bool HasReason
        {
            get { return !string.IsNullOrEmpty(_unavailableReason); }
        }

        public event PropertyChangedEventHandler PropertyChanged;
        private void Raise(string name)
        {
            PropertyChangedEventHandler h = PropertyChanged;
            if (h != null) h(this, new PropertyChangedEventArgs(name));
        }
    }

    /// <summary>
    /// One displayed row of a report.
    ///
    /// The cells are STRINGS prepared for display, because the two things that
    /// matter — a blank cell and a zero — must not collapse into the same
    /// pixel. A null amount renders as "—" and an actual zero renders as "0".
    /// Handing the DataGrid a nullable long and letting it format would print
    /// an empty cell for both, which is the precise confusion this project
    /// keeps having to undo.
    /// </summary>
    public sealed class ReportRow
    {
        /// <summary>Cell text by column key, then the ordered values.</summary>
        public Dictionary<string, string> Cells { get; private set; }
        public string[] Values { get; private set; }

        public ReportRow(string[] values)
        {
            Values = values;
            Cells = new Dictionary<string, string>();
        }
    }

    /// <summary>
    /// A report ready to display: columns plus rows plus a totals line.
    ///
    /// Kept as a plain data holder so it can be built by any caller — today
    /// the report engine behind a delegate, tomorrow a cached export.
    /// </summary>
    public sealed class ReportView
    {
        public string Id { get; set; }
        public string Title { get; set; }
        public string Subtitle { get; set; }
        public string[] Columns { get; set; }
        public List<string[]> Rows { get; set; }
        public string TotalsLine { get; set; }
        public string WarningText { get; set; }
        public bool HasWarning
        {
            get { return !string.IsNullOrEmpty(WarningText); }
        }

        public ReportView()
        {
            Columns = new string[0];
            Rows = new List<string[]>();
        }
    }

    /// <summary>
    /// The reports screen.
    ///
    /// Four delegate-injected operations, same shape as ImportViewModel: this
    /// class must not reference Persistence or Application, so it stays
    /// testable and the window stays a view. Wiring lives in one place.
    /// </summary>
    public sealed class ReportsViewModel : INotifyPropertyChanged
    {
        private readonly Func<List<ReportChoice>> _listReports;
        private readonly Func<string, ReportView> _buildReport;
        private readonly Func<string> _resolveDatabasePath;
        private readonly Func<string, string> _buildCsv;
        private readonly Action<string> _setPartyCode;

        private string _statusMessage;
        private ReportChoice _selected;
        private ReportView _current;
        private string _rangeFrom;
        private string _rangeTo;

        /// <summary>Per-report parameters. Only the baskets report uses one
        /// today, but the shape is general so a second one does not need a
        /// second ViewModel.</summary>
        public string PartyCode { get; set; }

        public ReportsViewModel(
            Func<List<ReportChoice>> listReports,
            Func<string, ReportView> buildReport,
            Func<string> resolveDatabasePath,
            Func<string, string> buildCsv,
            Action<string> setPartyCode)
        {
            _listReports = listReports;
            _buildReport = buildReport;
            _resolveDatabasePath = resolveDatabasePath;
            _buildCsv = buildCsv;
            _setPartyCode = setPartyCode;
            Reports = new ObservableCollection<ReportChoice>();
            CurrentRows = new ObservableCollection<string[]>();
            Columns = new ObservableCollection<string>();
            StatusMessage = "";
            PartyCode = "";
            Load();
        }

        public ObservableCollection<ReportChoice> Reports { get; private set; }
        public ObservableCollection<string> Columns { get; private set; }
        public ObservableCollection<string[]> CurrentRows { get; private set; }

        public ReportChoice Selected
        {
            get { return _selected; }
            set
            {
                _selected = value;
                Raise("Selected");
                Raise("SelectedDescription");
                Raise("CanExport");
            }
        }

        public string SelectedDescription
        {
            get
            {
                if (_selected == null) return "یک گزارش را از فهرست انتخاب کنید.";
                if (!_selected.IsAvailable) return _selected.UnavailableReason;
                return _selected.Description;
            }
        }

        public ReportView Current
        {
            get { return _current; }
            private set
            {
                _current = value;
                Raise("Current");
                Raise("HasReport");
                Raise("TotalsLine");
                Raise("HasTotals");
                Raise("WarningText");
                Raise("HasWarning");
                Raise("CanExport");
            }
        }

        public bool HasReport
        {
            get { return _current != null && _current.Rows != null; }
        }

        public string TotalsLine
        {
            get { return _current == null ? "" : _current.TotalsLine; }
        }

        public bool HasTotals
        {
            get { return !string.IsNullOrEmpty(TotalsLine); }
        }

        public string WarningText
        {
            get { return _current == null ? "" : _current.WarningText; }
        }

        public bool HasWarning
        {
            get { return _current != null && _current.HasWarning; }
        }

        /// <summary>Export needs a built report. It does NOT need the report to
        /// have rows: an empty report is a real answer, and refusing to export
        /// it hides the fact that it is empty.</summary>
        public bool CanExport
        {
            get { return _current != null; }
        }

        public string RangeFrom
        {
            get { return _rangeFrom; }
            set { _rangeFrom = value; Raise("RangeFrom"); }
        }

        public string RangeTo
        {
            get { return _rangeTo; }
            set { _rangeTo = value; Raise("RangeTo"); }
        }

        public string StatusMessage
        {
            get { return _statusMessage; }
            private set { _statusMessage = value; Raise("StatusMessage"); }
        }

        // ------------------------------------------------------------------
        public void Load()
        {
            try
            {
                Reports.Clear();
                foreach (ReportChoice c in _listReports())
                    Reports.Add(c);

                int open = 0;
                foreach (ReportChoice c in Reports)
                    if (c.IsAvailable) open++;

                StatusMessage = Reports.Count == 0
                    ? "هیچ گزارشی تعریف نشده است."
                    : open + " گزارش آماده از " + Reports.Count
                      + " گزارش (یکی منتظر تعریف مالک است).";

                if (ReviewsNeedOneUnavailable(Reports))
                    StatusMessage = "شش گزارش آماده است. گزارش مالی هنوز ساختار "
                        + "ندارد؛ فایل مالک، شیت Report را خالی گذاشته است.";
            }
            catch (Exception ex)
            {
                StatusMessage = "فهرست گزارش‌ها خوانده نشد: " + ex.Message;
            }
        }

        private static bool ReviewsNeedOneUnavailable(
            IEnumerable<ReportChoice> items)
        {
            foreach (ReportChoice c in items)
                if (!c.IsAvailable) return true;
            return false;
        }

        /// <summary>
        /// Build the selected report.
        ///
        /// Refuses to build an unavailable one rather than calling through and
        /// letting the engine throw: the engine's exception is a developer
        /// message, the button's refusal is the owner's answer.
        /// </summary>
        public void Open()
        {
            if (_selected == null)
            {
                StatusMessage = "اول یک گزارش را انتخاب کنید.";
                return;
            }
            if (!_selected.IsAvailable)
            {
                StatusMessage = _selected.UnavailableReason;
                return;
            }
            try
            {
                // Hand the party code over BEFORE building: only the baskets
                // report uses it, and passing it as an argument would change
                // every report's call shape for the one that needs it.
                if (_setPartyCode != null) _setPartyCode(PartyCode);
                ReportView view = _buildReport(_selected.Id);
                Columns.Clear();
                foreach (string col in view.Columns) Columns.Add(col);

                CurrentRows.Clear();
                foreach (string[] row in view.Rows) CurrentRows.Add(row);

                Current = view;
                StatusMessage = view.Title + " · " + view.Rows.Count + " ردیف";
            }
            catch (Exception ex)
            {
                Current = null;
                Columns.Clear();
                CurrentRows.Clear();
                // The owner's language, and the real reason.
                StatusMessage = ex.Message;
            }
        }

        public string ExportCsv()
        {
            if (_current == null) return null;
            try
            {
                string path = _buildCsv(_current.Id);
                StatusMessage = "خروجی ساخته شد: " + path;
                return path;
            }
            catch (Exception ex)
            {
                StatusMessage = "ساخت خروجی ناموفق: " + ex.Message;
                return null;
            }
        }

        public string DatabasePath()
        {
            return _resolveDatabasePath();
        }

        public event PropertyChangedEventHandler PropertyChanged;
        private void Raise(string name)
        {
            PropertyChangedEventHandler h = PropertyChanged;
            if (h != null) h(this, new PropertyChangedEventArgs(name));
        }
    }
}
