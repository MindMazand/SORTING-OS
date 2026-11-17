using System.Windows;

namespace Mazandasht.Presentation
{
    /// <summary>
    /// Main window shell (Spec ch. 11-13): RTL dashboard, central quick-add
    /// (+) operations menu from the registry, second-monitor window.
    /// Module windows (weigh, sorting, invoices, ...) open from the menu.
    /// </summary>
    public partial class MainWindow : Window
    {
        private SecondMonitorWindow _secondMonitor;

        public MainWindow()
        {
            InitializeComponent();
            QuickAddButton.Click += (s, e) =>
            {
                QuickAddMenu.IsOpen = true;
            };
            SecondMonitorButton.Click += (s, e) => OpenSecondMonitor();
            RefreshDashboard();
        }

        private void OpenSecondMonitor()
        {
            if (_secondMonitor != null && _secondMonitor.IsLoaded)
            {
                _secondMonitor.Activate();
                return;
            }
            _secondMonitor = new SecondMonitorWindow();
            _secondMonitor.Show();
        }

        private void RefreshDashboard()
        {
            // KPI values are loaded from the real database by the dashboard
            // service; the shell only binds them. Empty state is explicit.
            var vm = new DashboardViewModel { RangeLabel = "بازه: ۷ روز گذشته" };
            KpiItems.ItemsSource = vm.Cards;
            RangeLabel.Text = vm.RangeLabel;
            StatusText.Text = vm.IsEmpty
                ? "داده‌ای برای نمایش وجود ندارد."
                : "داشبورد به‌روز شد.";
        }
    }
}
