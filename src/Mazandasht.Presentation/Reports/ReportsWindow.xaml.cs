using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;

namespace Mazandasht.Presentation.Reports
{
    /// <summary>
    /// The reports window. It owns no query logic: the view model decides what
    /// exists and what can be opened, the engine builds it, this class binds.
    ///
    /// The one job that MUST live here is the DataGrid columns, because the
    /// seven reports have different column counts. A fixed set in XAML would
    /// either truncate or need seven templates.
    /// </summary>
    public partial class ReportsWindow : Window
    {
        private readonly ReportsViewModel _vm;

        public ReportsWindow(ReportsViewModel viewModel)
        {
            InitializeComponent();
            _vm = viewModel;
            DataContext = _vm;

            ReportList.ItemsSource = _vm.Reports;

            _vm.PropertyChanged += (s, e) =>
            {
                if (e.PropertyName == "StatusMessage")
                    StatusText.Text = _vm.StatusMessage;
                else if (e.PropertyName == "Current")
                    RebuildGrid();
            };

            // The window is given its view model, never constructs one: the
            // wiring (engine, database path, CSV writer) belongs in one place
            // and this class must not know where the database is.
            Loaded += (s, e) => StatusText.Text = _vm.StatusMessage;
        }

        private void ReportList_SelectionChanged(object sender,
                                                SelectionChangedEventArgs e)
        {
            _vm.Selected = ReportList.SelectedItem as ReportChoice;
            DescriptionText.Text = _vm.SelectedDescription;

            // A report with no layout must not leave an openable-looking button.
            OpenButton.IsEnabled = _vm.Selected != null && _vm.Selected.CanOpen;
            TitleText.Text = _vm.Selected == null
                ? "گزارشی انتخاب نشده"
                : _vm.Selected.Title;
        }

        private void OpenButton_Click(object sender, RoutedEventArgs e)
        {
            _vm.PartyCode = PartyCodeBox.Text;
            _vm.Open();
            StatusText.Text = _vm.StatusMessage;
            StatusText.Text = _vm.StatusMessage;
            RebuildGrid();
        }

        private void ExportButton_Click(object sender, RoutedEventArgs e)
        {
            string path = _vm.ExportCsv();
            StatusText.Text = _vm.StatusMessage;
            if (!string.IsNullOrEmpty(path))
                MessageBox.Show("خروجی در این مسیر ساخته شد:\n" + path,
                                "خروجی CSV", MessageBoxButton.OK,
                                MessageBoxImage.Information);
        }

        /// <summary>
        /// Rebuild the grid's columns from the current report.
        ///
        /// Cells arrive as strings already formatted by the view model, where
        /// an unknown value is "—" and a real zero is "0". Binding a nullable
        /// number directly would render both as an empty cell and re-create the
        /// confusion between blank and zero that this project keeps undoing.
        /// </summary>
        private void RebuildGrid()
        {
            ReportGrid.Columns.Clear();
            ReportGrid.ItemsSource = null;

            ReportView view = _vm.Current;
            if (view == null)
            {
                TotalsText.Text = "";
                WarningText.Text = "";
                WarningText.Visibility = Visibility.Collapsed;
                ExportButton.IsEnabled = false;
                return;
            }

            for (int i = 0; i < view.Columns.Length; i++)
            {
                ReportGrid.Columns.Add(new DataGridTextColumn
                {
                    Header = view.Columns[i],
                    // Path="[0]", "[1]", … on a string[]; no dynamic object or
                    // expando needed, and the index is the column order the
                    // workbook itself uses.
                    Binding = new Binding("[" + i + "]"),
                    Width = i == view.Columns.Length - 1
                        ? new DataGridLength(1, DataGridLengthUnitType.Star)
                        : DataGridLength.Auto,
                    IsReadOnly = true
                });
            }

            ReportGrid.ItemsSource = _vm.CurrentRows;

            TotalsText.Text = view.TotalsLine;
            WarningText.Text = view.WarningText;
            WarningText.Visibility = view.HasWarning
                ? Visibility.Visible
                : Visibility.Collapsed;
            ExportButton.IsEnabled = _vm.CanExport;
        }
    }
}
