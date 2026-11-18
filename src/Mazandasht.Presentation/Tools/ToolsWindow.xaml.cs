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

            // Probe on load: the size and timestamp are read from the real
            // file, never inferred from a previous run.
            Loaded += (s, e) =>
            {
                _vm.ProbeDatabase(DatabasePathProvider.Resolve());
                StatusText.Text = _vm.StatusMessage;
            };
        }
    }
}
