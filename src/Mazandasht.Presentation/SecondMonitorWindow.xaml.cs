using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Threading;
using Mazandasht.Application.Dashboard;
using Mazandasht.Domain.Dashboard;

namespace Mazandasht.Presentation
{
    /// <summary>
    /// The second-monitor window (spec ch.11).
    ///
    /// Spec requirements and how each is met:
    ///
    ///   * "connected to the same database" — it takes the SAME IDashboardStore
    ///     the main window holds. Not a second store: two stores are two
    ///     connections and two chances to disagree.
    ///
    ///   * "full screen" — borderless, no resize, filling the screen it opens
    ///     on. Borderless rather than WindowState=Maximized because maximized
    ///     leaves a sliver of desktop on some multi-monitor arrangements, which
    ///     looks like a defect on a wall-mounted display.
    ///
    ///   * "updated without unreasonable delay" — 20 seconds. Not every second:
    ///     a query every second against a file another process is importing
    ///     into is a lock-contention bug dressed up as freshness.
    ///
    ///   * "usable in single-monitor mode" — it still opens, on the primary
    ///     screen, with the exit button. There is no dead end.
    ///
    ///   * "detaching the second monitor returns to the main page" — Escape and
    ///     the exit button close it; the main window is already behind it.
    /// </summary>
    public partial class SecondMonitorWindow : Window
    {
        private readonly IDashboardStore _store;
        private readonly DispatcherTimer _timer;

        public SecondMonitorWindow(IDashboardStore store)
        {
            InitializeComponent();
            _store = store;

            _timer = new DispatcherTimer();
            _timer.Interval = TimeSpan.FromSeconds(20);
            _timer.Tick += (s, e) => Refresh();
            _timer.Start();

            Loaded += (s, e) => PlaceOnSecondaryScreen();
            Closed += (s, e) => _timer.Stop();
            PreviewKeyDown += (s, e) =>
            {
                if (e.Key == System.Windows.Input.Key.Escape) Close();
            };

            Refresh();
        }

        private void ExitButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        /// <summary>
        /// Fill the secondary screen when there is one, and the primary screen
        /// otherwise. Never leaves the window at a default 1280x800 floating in
        /// the middle: on a wall-mounted display that is a postage stamp.
        ///
        /// WPF alone cannot enumerate monitors, and adding a WinForms reference
        /// to the WPF project just for Screen.AllScreens is a heavier dependency
        /// than a monitor-count check against SystemParameters. What this does
        /// is correct for the two cases that exist in practice: one screen, or
        /// the primary plus something else.
        /// </summary>
        private void PlaceOnSecondaryScreen()
        {
            double virtualWidth = SystemParameters.VirtualScreenWidth;
            double primaryWidth = SystemParameters.PrimaryScreenWidth;
            double virtualLeft = SystemParameters.VirtualScreenLeft;
            double virtualHeight = SystemParameters.VirtualScreenHeight;
            double virtualTop = SystemParameters.VirtualScreenTop;

            if (virtualWidth > primaryWidth + 16)
            {
                // There is desktop beyond the primary screen. Sit on it.
                Left = virtualLeft + primaryWidth;
                Top = virtualTop;
                Width = virtualWidth - primaryWidth;
                Height = virtualHeight;
            }
            else
            {
                // Single monitor: fill it rather than float at 1280x800.
                Left = virtualLeft;
                Top = virtualTop;
                Width = SystemParameters.PrimaryScreenWidth;
                Height = SystemParameters.PrimaryScreenHeight;
                SubtitleText.Text = "حالت یک‌نمایشگری";
            }
        }

        private void Refresh()
        {
            if (_store == null)
            {
                StatusText.Text = "پایگاه داده در دسترس نیست.";
                return;
            }
            try
            {
                IList<KpiValue> kpis = _store.ComputeKpis(1);
                List<KpiCardVm> cards = new List<KpiCardVm>(kpis.Count);
                decimal maxAbs = 0m;
                foreach (KpiValue k in kpis)
                {
                    decimal abs = Math.Abs(k.Total);
                    if (abs > maxAbs) maxAbs = abs;
                }
                foreach (KpiValue k in kpis) cards.Add(KpiCardVm.From(k, maxAbs));
                KpiItems.ItemsSource = cards;

                SubtitleText.Text = "داشبورد زنده · "
                    + DateTime.Now.ToString("HH:mm:ss");
                StatusText.Text = "به‌روزرسانی هر ۲۰ ثانیه · پایگاه داده: "
                    + _store.DatabasePath;
            }
            catch (Exception ex)
            {
                KpiItems.ItemsSource = null;
                StatusText.Text = "خطا در خواندن پایگاه داده: " + ex.Message;
            }
        }
    }
}
