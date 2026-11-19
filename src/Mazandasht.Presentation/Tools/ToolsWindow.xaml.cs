using System.Windows;

namespace Mazandasht.Presentation.Tools
{
    /// <summary>
    /// The tools window. It owns no logic: the view model builds the cards and
    /// probes the database, the window binds them.
    /// </summary>
    public partial class ToolsWindow : Window
    {
        private readonly ToolsViewModel _vm;

        public ToolsWindow()
        {
            InitializeComponent();
            _vm = new ToolsViewModel();
            DataContext = _vm;
            ToolItems.ItemsSource = _vm.Cards;
            ReportItems.ItemsSource = _vm.PendingReports;
            StatusText.Text = _vm.StatusMessage;

            _vm.PropertyChanged += (s, e) =>
            {
                if (e.PropertyName == "StatusMessage")
                    StatusText.Text = _vm.StatusMessage;
            };

            // Probe on load: counts and timestamps come from the real file,
            // never inferred from a previous run.
            //
            // The Probe button exists because this screen is left open: the
            // owner imports something in another window and comes back to a
            // card that still says "nothing imported yet". A manual refresh is
            // the honest fix; a background poll against the same file the
            // importer is writing to is how "database is locked" happens.
            Loaded += (s, e) => Probe();
            ProbeButton.Click += (s, e) => Probe();
        }

        private void Probe()
        {
            _vm.ProbeDatabase(DatabasePathProvider.Resolve());
            StatusText.Text = _vm.StatusMessage;
            // Rebind: the collection is the same instance but the card
            // properties changed, and a TextBlock bound to a plain property
            // would not repaint without the notification ToolCard now raises.
            ToolItems.Items.Refresh();
        }
    }
}
