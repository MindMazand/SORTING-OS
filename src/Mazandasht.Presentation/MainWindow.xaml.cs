using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using Mazandasht.Application.Dashboard;

namespace Mazandasht.Presentation
{
    /// <summary>
    /// Main window shell (spec ch.11-13).
    ///
    /// WHAT THIS WINDOW IS RESPONSIBLE FOR
    ///
    ///  * Holding the dashboard view model and reloading it.
    ///  * Switching the selected tool group.
    ///  * Opening the tools window and the second monitor.
    ///
    /// WHAT IT IS NOT
    ///
    /// It does not compute a single KPI. Every number comes from
    /// IDashboardStore. That is the whole reason the store is an interface: a
    /// query inside a code-behind cannot be tested, and its numbers cannot be
    /// compared to the Python reference that proved them.
    /// </summary>
    public partial class MainWindow : Window
    {
        private SecondMonitorWindow _secondMonitor;
        private Tools.ToolsWindow _toolsWindow;
        private Import.ImportWindow _importWindow;
        private DashboardViewModel _vm;
        private IDashboardStore _store;

        public MainWindow()
        {
            InitializeComponent();

            VersionText.Text = "نسخه ۱٫۰ · اسکیمای ۵";

            try
            {
                _store = DatabasePathProvider.CreateDashboardStore();
                _vm = new DashboardViewModel(_store);
                DataContext = _vm;
                _vm.Refresh();
                ApplyCards();
                _vm.Start();
            }
            catch (Exception ex)
            {
                // A failed startup must still show a window with a reason.
                // Dying before the first paint leaves the owner with a silent
                // "app does not open" and nothing to report.
                StatusText.Text = "پایگاه داده باز نشد: " + ex.Message;
                ShowEmpty("پایگاه داده در دسترس نیست. مسیر و مجوز فایل را بررسی کنید.");
            }
        }

        // ------------------------------------------------------------------
        // Dashboard
        // ------------------------------------------------------------------

        /// <summary>
        /// Push the view model's cards into the ItemsControl and paint the bars.
        /// </summary>
        private void ApplyCards()
        {
            if (_vm == null) return;
            KpiItems.ItemsSource = _vm.Cards;
            EmptyStateText.Text = _vm.EmptyMessage;
            EmptyStatePanel.Visibility = _vm.IsEmpty && !string.IsNullOrEmpty(_vm.EmptyMessage)
                ? Visibility.Visible
                : Visibility.Collapsed;
            StatusText.Text = _vm.StatusMessage;

            Dispatcher.BeginInvoke(new Action(PaintBars),
                System.Windows.Threading.DispatcherPriority.Loaded);
        }

        /// <summary>
        /// Size each bar against the card's track.
        ///
        /// Done here rather than bound because a per-card width binding needs a
        /// converter that knows the maximum across all cards — a value the item
        /// template cannot see. One pass over the visual tree cannot get out of
        /// step with the numbers.
        /// </summary>
        private void PaintBars()
        {
            if (_vm == null) return;
            for (int i = 0; i < _vm.Cards.Count; i++)
            {
                ContentPresenter cp = KpiItems.ItemContainerGenerator
                    .ContainerFromIndex(i) as ContentPresenter;
                if (cp == null) continue;
                cp.ApplyTemplate();

                Border fill = FindByName(cp, "BarFill") as Border;
                if (fill == null) continue;

                Border track = fill.Parent as Border;
                if (track == null && fill.Parent is Grid)
                {
                    Grid g = (Grid)fill.Parent;
                    foreach (UIElement child in g.Children)
                    {
                        Border b = child as Border;
                        if (b != null && b != fill) { track = b; break; }
                    }
                }
                if (track == null) continue;

                double available = track.ActualWidth;
                fill.Width = Math.Max(2, available * _vm.Cards[i].BarFraction);
            }
        }

        private static FrameworkElement FindByName(DependencyObject root, string name)
        {
            if (root == null) return null;
            FrameworkElement fe = root as FrameworkElement;
            if (fe != null && fe.Name == name) return fe;

            int n = VisualTreeHelper.GetChildrenCount(root);
            for (int i = 0; i < n; i++)
            {
                FrameworkElement found = FindByName(VisualTreeHelper.GetChild(root, i), name);
                if (found != null) return found;
            }
            return null;
        }

        private void ShowEmpty(string message)
        {
            KpiItems.ItemsSource = null;
            EmptyStateText.Text = message;
            EmptyStatePanel.Visibility = Visibility.Visible;
        }

        private void RefreshButton_Click(object sender, RoutedEventArgs e)
        {
            if (_vm == null) return;
            _vm.Refresh();
            ApplyCards();
        }

        private void RangePicker_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            // Fires during InitializeComponent before _vm exists. Guarding here
            // is not defensive noise: without it the app throws on startup.
            if (_vm == null) return;
            ComboBoxItem item = RangePicker.SelectedItem as ComboBoxItem;
            if (item == null || item.Tag == null) return;
            int days;
            if (!int.TryParse(item.Tag.ToString(), out days)) return;
            _vm.RangeDays = days;
            ApplyCards();
        }

        // ------------------------------------------------------------------
        // Navigation
        // ------------------------------------------------------------------

        /// <summary>
        /// All nine navigation entries share one handler: nine near-identical
        /// handlers is nine places for a copy-paste to go wrong.
        /// </summary>
        private void Nav_Click(object sender, RoutedEventArgs e)
        {
            ToggleButton source = sender as ToggleButton;
            if (source == null) return;

            if (source == NavDashboard) { SelectTool("داشبورد مدیریتی", NavDashboard); }
            else if (source == NavImport)
            {
                SelectTool("مرکز واردسازی", NavImport);
                OpenImport();
            }
            else if (source == NavTools)
            {
                SelectTool("ابزارهای نگهداری", NavTools);
                OpenTools();
            }
            else if (source == NavReports) { SelectTool("گزارش‌ها", NavReports); }
            else if (source == NavWeigh) { SelectTool("باسکول", NavWeigh); }
            else if (source == NavSorting) { SelectTool("سورتینگ", NavSorting); }
            else if (source == NavInvoices) { SelectTool("خرید و فروش", NavInvoices); }
            else if (source == NavBank) { SelectTool("بانک و چک", NavBank); }
            else if (source == NavParties) { SelectTool("اشخاص", NavParties); }
        }

        private void SelectTool(string title, ToggleButton source)
        {
            PageTitle.Text = title;
            NavDashboard.IsChecked = ReferenceEquals(source, NavDashboard);
            NavImport.IsChecked = ReferenceEquals(source, NavImport);
            NavTools.IsChecked = ReferenceEquals(source, NavTools);
            NavReports.IsChecked = ReferenceEquals(source, NavReports);
            NavWeigh.IsChecked = ReferenceEquals(source, NavWeigh);
            NavSorting.IsChecked = ReferenceEquals(source, NavSorting);
            NavInvoices.IsChecked = ReferenceEquals(source, NavInvoices);
            NavBank.IsChecked = ReferenceEquals(source, NavBank);
            NavParties.IsChecked = ReferenceEquals(source, NavParties);
        }

        /// <summary>
        /// The tools window is single-instance: opening it twice would leave two
        /// windows reading the same database with no way for the owner to know
        /// which is current.
        /// </summary>
        private void OpenTools()
        {
            if (_toolsWindow != null && _toolsWindow.IsLoaded)
            {
                _toolsWindow.Activate();
                return;
            }
            _toolsWindow = new Tools.ToolsWindow();
            _toolsWindow.Owner = this;
            _toolsWindow.Closed += (s, e) => _toolsWindow = null;
            _toolsWindow.Show();
        }

        /// <summary>
        /// Same single-instance rule as the tools window: two import windows
        /// would mean two file previews against one database, and the owner
        /// could commit from a stale one.
        /// </summary>
        private void OpenImport()
        {
            if (_importWindow != null && _importWindow.IsLoaded)
            {
                _importWindow.Activate();
                return;
            }
            _importWindow = new Import.ImportWindow();
            _importWindow.Owner = this;
            _importWindow.Closed += (s, e) => _importWindow = null;
            _importWindow.Show();
        }

        // ------------------------------------------------------------------
        // Quick add
        // ------------------------------------------------------------------

        private void QuickAddButton_Click(object sender, RoutedEventArgs e)
        {
            QuickAddMenu.PlacementTarget = QuickAddButton;
            QuickAddMenu.IsOpen = true;
        }

        private void QuickAddMenu_Click(object sender, RoutedEventArgs e)
        {
            MenuItem item = sender as MenuItem;
            if (item == null) return;
            string code = item.Tag as string;
            if (string.IsNullOrEmpty(code)) return;

            // Every operation is a real registry code. The modules that are not
            // built yet say so instead of opening an empty window that looks
            // broken.
            switch (code)
            {
                case "WEIGH":
                case "SORTING":
                case "PURCHASE":
                case "SALES":
                case "STOCK":
                case "BASKET":
                case "BANK":
                case "CHEQUE":
                case "SETTLEMENT":
                case "PARTY":
                case "EMPLOYEE":
                case "EXPENSE":
                case "PARTNERSHIP":
                case "JOURNAL":
                    StatusText.Text = "«" + item.Header + "» — این ماژول در نسخه بعدی فعال می‌شود.";
                    break;
                default:
                    StatusText.Text = "عملیات ناشناخته: " + code;
                    break;
            }
        }

        // ------------------------------------------------------------------
        // Second monitor
        // ------------------------------------------------------------------

        private void SecondMonitorButton_Click(object sender, RoutedEventArgs e)
        {
            OpenSecondMonitor();
        }

        private void OpenSecondMonitor()
        {
            if (_secondMonitor != null && _secondMonitor.IsLoaded)
            {
                _secondMonitor.Activate();
                return;
            }
            _secondMonitor = new SecondMonitorWindow(_store);
            _secondMonitor.Closed += (s, e) => _secondMonitor = null;
            _secondMonitor.Show();
        }

        protected override void OnClosed(EventArgs e)
        {
            if (_vm != null) _vm.Stop();
            base.OnClosed(e);
        }
    }
}
