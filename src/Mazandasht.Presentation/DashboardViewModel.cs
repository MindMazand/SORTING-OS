using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Globalization;
using System.Windows.Threading;
using Mazandasht.Application.Dashboard;
using Mazandasht.Domain.Dashboard;

namespace Mazandasht.Presentation
{
    /// <summary>
    /// One tile on the dashboard.
    ///
    /// Carries THREE formatted numbers, because spec ch.11 requires the
    /// approved / under-review split and a single total hides it. The subtitle
    /// only appears when there really are unconfirmed documents — a permanent
    /// "۰ بررسی‌نشده" under every card is noise.
    /// </summary>
    public sealed class KpiCardVm
    {
        public string Key { get; set; }
        public string Title { get; set; }
        public string Value { get; set; }
        public string Unit { get; set; }
        public string Subtitle { get; set; }
        public string ApprovedLabel { get; set; }
        public string ReviewLabel { get; set; }
        public bool HasPending { get; set; }
        public string AccentColor { get; set; }

        /// <summary>Normalised 0..1 bar height for the comparison strip.</summary>
        public double BarFraction { get; set; }

        public static KpiCardVm From(KpiValue kpi, decimal maxAbs)
        {
            if (kpi == null) throw new ArgumentNullException("kpi");

            string subtitle = kpi.HasPending
                ? "تأییدشده " + kpi.Format(kpi.Approved) +
                  " · بررسی‌نشده " + kpi.Format(kpi.Review)
                : "";

            double fraction = 0;
            if (maxAbs > 0m)
            {
                decimal abs = Math.Abs(kpi.Total);
                fraction = (double)(abs / maxAbs);
                if (fraction > 1) fraction = 1;
            }

            return new KpiCardVm
            {
                Key = kpi.Key,
                Title = kpi.LabelFa,
                Value = kpi.Format(kpi.Total),
                Unit = kpi.UnitLabelFa,
                Subtitle = subtitle,
                ApprovedLabel = kpi.Format(kpi.Approved),
                ReviewLabel = kpi.Format(kpi.Review),
                HasPending = kpi.HasPending,
                // Accent is a token name resolved by the view, not a hex here:
                // colour decisions live in Design/Theme.v2.xaml only.
                AccentColor = kpi.HasPending ? "PendingBrush" : "BrandBrush",
                BarFraction = fraction,
            };
        }
    }

    /// <summary>
    /// Dashboard view model.
    ///
    /// Deliberate decisions:
    ///
    ///  * No mock values, ever. If the database has nothing, the cards are
    ///    empty and <see cref="EmptyMessage"/> explains why. A zero that looks
    ///    like a real figure is the worst possible outcome on a money screen.
    ///
    ///  * Loading is explicit and re-runnable. The refresh timer calls the
    ///    same path as the first load, so a bug cannot exist in only one.
    ///
    ///  * A failed load is shown in <see cref="StatusMessage"/> with the reason
    ///    from the exception. Swallowing it and showing zeros would tell the
    ///    owner "no sales today" when the truth is "the query broke".
    /// </summary>
    public sealed class DashboardViewModel : INotifyPropertyChanged
    {
        private readonly IDashboardStore _store;
        private readonly DispatcherTimer _timer;

        private string _rangeLabel = "";
        private string _statusMessage = "";
        private string _emptyMessage = "";
        private bool _isBusy;
        private int _rangeDays = 1;

        public event PropertyChangedEventHandler PropertyChanged;

        public ObservableCollection<KpiCardVm> Cards { get; private set; }

        public DashboardViewModel(IDashboardStore store)
        {
            if (store == null) throw new ArgumentNullException("store");
            _store = store;
            Cards = new ObservableCollection<KpiCardVm>();
            _timer = new DispatcherTimer();
            _timer.Interval = TimeSpan.FromSeconds(60);
            _timer.Tick += (s, e) => Refresh();
        }

        // Explicit setters rather than one generic Set<T> with object casts.
        // The generic version compiles, but `(string)(object)value` boxes and
        // is exactly the kind of thing that throws InvalidCastException in
        // production and nowhere else.
        public string RangeLabel
        {
            get { return _rangeLabel; }
            private set
            {
                if (_rangeLabel == value) return;
                _rangeLabel = value;
                Raise("RangeLabel");
            }
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

        public string EmptyMessage
        {
            get { return _emptyMessage; }
            private set
            {
                if (_emptyMessage == value) return;
                _emptyMessage = value;
                Raise("EmptyMessage");
            }
        }

        public bool IsBusy
        {
            get { return _isBusy; }
            private set
            {
                if (_isBusy == value) return;
                _isBusy = value;
                Raise("IsBusy");
            }
        }

        public bool IsEmpty
        {
            get { return Cards.Count == 0; }
        }

        /// <summary>Which window the owner picked. Spec ch.11: configurable.</summary>
        public int RangeDays
        {
            get { return _rangeDays; }
            set
            {
                if (value < 1) value = 1;
                if (value == _rangeDays) return;
                _rangeDays = value;
                Refresh();
            }
        }

        public void Start() { _timer.Start(); }

        public void Stop() { _timer.Stop(); }

        /// <summary>
        /// Reload every KPI. Safe to call repeatedly; never throws.
        /// </summary>
        public void Refresh()
        {
            IsBusy = true;
            try
            {
                IList<KpiValue> kpis = _store.ComputeKpis(_rangeDays);

                // One scale for all bars, or each card would be 100% tall and
                // the chart would say nothing.
                decimal maxAbs = 0m;
                foreach (KpiValue k in kpis)
                {
                    decimal abs = Math.Abs(k.Total);
                    if (abs > maxAbs) maxAbs = abs;
                }

                Cards.Clear();
                bool anyData = false;
                foreach (KpiValue k in kpis)
                {
                    if (!k.IsEmpty) anyData = true;
                    Cards.Add(KpiCardVm.From(k, maxAbs));
                }

                RangeLabel = RangeText(_rangeDays);

                if (!anyData)
                {
                    EmptyMessage = "هنوز هیچ سندی ثبت نشده است. "
                        + "برای شروع، از مرکز ابزارها داده وارد کنید.";
                    StatusMessage = "داده‌ای برای نمایش وجود ندارد.";
                }
                else
                {
                    EmptyMessage = "";
                    StatusMessage = "داشبورد به‌روز شد · "
                        + DateTime.Now.ToString("HH:mm:ss", CultureInfo.InvariantCulture);
                }
            }
            catch (Exception ex)
            {
                // Silent zeros would read as "no sales today". Say what broke.
                Cards.Clear();
                EmptyMessage = "";
                StatusMessage = "خطا در خواندن داشبورد: " + ex.Message;
            }
            finally
            {
                IsBusy = false;
                Raise("IsEmpty");
            }
        }

        private static string RangeText(int days)
        {
            if (days == 1) return "بازه: امروز";
            if (days == 2) return "بازه: دو روز گذشته";
            if (days == 7) return "بازه: هفت روز گذشته";
            if (days == 30) return "بازه: سی روز گذشته";
            return "بازه: " + days.ToString(CultureInfo.InvariantCulture) + " روز گذشته";
        }

        private void Raise(string name)
        {
            PropertyChangedEventHandler h = PropertyChanged;
            if (h != null) h(this, new PropertyChangedEventArgs(name));
        }
    }
}
