using System;
using System.Windows;

namespace Mazandasht.Presentation
{
    /// <summary>
    /// Second-monitor display window (Spec ch. 11): same process, same
    /// database, fullscreen-capable, auto-refresh. If the second monitor is
    /// disconnected, the window returns to the primary screen.
    /// </summary>
    public partial class SecondMonitorWindow : Window
    {
        private readonly System.Windows.Threading.DispatcherTimer _timer;

        public SecondMonitorWindow()
        {
            InitializeComponent();
            PlaceOnSecondMonitor();
            _timer = new System.Windows.Threading.DispatcherTimer
            {
                Interval = TimeSpan.FromSeconds(10)
            };
            _timer.Tick += (s, e) => Refresh();
            _timer.Start();
            Closed += (s, e) => _timer.Stop();
        }

        private void PlaceOnSecondMonitor()
        {
            var area = SystemParameters.VirtualScreenWidth;
            var primary = SystemParameters.PrimaryScreenWidth;
            if (area > primary)
            {
                Left = primary + 8;
                Top = 0;
                Width = area - primary - 16;
            }
            else
            {
                // Single-monitor mode: still usable on the primary screen.
                WindowStartupLocation = WindowStartupLocation.CenterScreen;
            }
        }

        private void Refresh()
        {
            // Rebind KPI cards from the same database (no unreasonable delay).
            var vm = new DashboardViewModel();
            KpiItems.ItemsSource = vm.Cards;
        }
    }
}
