using System;
using System.Collections.Generic;
using System.Windows;
using Mazandasht.Application.Import;
using Mazandasht.Persistence;

namespace Mazandasht.Presentation.Import
{
    /// <summary>
    /// The import centre (spec ch.14).
    ///
    /// This window owns the file dialog and the confirmation dialogs, and
    /// nothing else. Parsing, validation, writing and rollback all live in
    /// Application/Persistence where they have executing tests. A code-behind
    /// that parsed a file would be the one place in this app with no test.
    /// </summary>
    public partial class ImportWindow : Window
    {
        private readonly ImportViewModel _vm;
        private ImportService _service;

        public ImportWindow()
        {
            InitializeComponent();

            try
            {
                string path = DatabasePathProvider.Resolve();
                if (!System.IO.File.Exists(path))
                {
                    // No database: show the window with a reason rather than
                    // throwing on open. The owner can still read what it does.
                    StatusText.Text = "پایگاه داده پیدا نشد: " + path
                        + " — ابتدا نصب اولیه را اجرا کنید.";
                    PreviewButton.IsEnabled = false;
                    ChooseFileButton.IsEnabled = false;
                    return;
                }
                _service = new ImportService(path);
            }
            catch (Exception ex)
            {
                StatusText.Text = "باز کردن پایگاه داده ناموفق: " + ex.Message;
                PreviewButton.IsEnabled = false;
                ChooseFileButton.IsEnabled = false;
                return;
            }

            _vm = new ImportViewModel(
                (file, code) => _service.Preview(file, code),
                (file, code) => _service.Commit(file, code),
                limit => _service.RecentBatches(limit),
                id => _service.Rollback(id));

            _vm.PropertyChanged += Vm_PropertyChanged;

            LoadTemplates();
            PreviewGrid.ItemsSource = _vm.PreviewRows;
            BatchList.ItemsSource = _vm.Batches;

            Loaded += (s, e) => _vm.RefreshBatches();
            Closed += (s, e) => { if (_service != null) _service.Dispose(); };

            StatusText.Text = "فایل و قالب را انتخاب کنید. تا دکمه ثبت را نزنید چیزی نوشته نمی‌شود.";
        }

        /// <summary>
        /// The eleven owner templates, in dependency order.
        ///
        /// The order is not cosmetic: importing a sales invoice before its party
        /// and product exist is refused by a foreign key. Presenting the list in
        /// that order is the cheapest possible prevention.
        /// </summary>
        private void LoadTemplates()
        {
            var choices = new List<TemplateChoice>
            {
                new TemplateChoice { Code = "PARTIES", FileName = "01_Parties.xlsx", ModuleFa = "اشخاص" },
                new TemplateChoice { Code = "PRODUCTS", FileName = "02_Products.xlsx", ModuleFa = "محصولات" },
                new TemplateChoice { Code = "WEIGHING_IN", FileName = "03_WeighingIn.xlsx", ModuleFa = "باسکول ورودی" },
                new TemplateChoice { Code = "PURCHASE_INVOICES", FileName = "04_PurchaseInvoices.xlsx", ModuleFa = "خرید" },
                new TemplateChoice { Code = "SALES_INVOICES", FileName = "05_SalesInvoices.xlsx", ModuleFa = "فروش" },
                new TemplateChoice { Code = "SORTING", FileName = "06_Sorting.xlsx", ModuleFa = "سورتینگ" },
                new TemplateChoice { Code = "BASKET_MOVEMENTS", FileName = "07_BasketMovements.xlsx", ModuleFa = "سبد" },
                new TemplateChoice { Code = "BANK_TRANSACTIONS", FileName = "08_BankTransactions.xlsx", ModuleFa = "بانک" },
                new TemplateChoice { Code = "CHEQUES", FileName = "09_Cheques.xlsx", ModuleFa = "چک" },
                new TemplateChoice { Code = "SETTLEMENTS", FileName = "10_Settlements.xlsx", ModuleFa = "تسویه" },
                new TemplateChoice { Code = "PARTNERSHIP", FileName = "11_Partnership.xlsx", ModuleFa = "شراکت" },
            };
            _vm.LoadTemplates(choices);
            TemplatePicker.ItemsSource = _vm.Templates;
        }

        private void Vm_PropertyChanged(object sender, System.ComponentModel.PropertyChangedEventArgs e)
        {
            switch (e.PropertyName)
            {
                case "StatusMessage": StatusText.Text = _vm.StatusMessage; break;
                case "FileSummary": FileSummaryText.Text = _vm.FileSummary; break;
                case "CanCommit":
                case "CommitButtonText":
                    CommitButton.IsEnabled = _vm.CanCommit;
                    CommitButton.Content = _vm.CommitButtonText;
                    break;
                case "ValidCount":
                    ValidCountText.Text = _vm.ValidCount + " ردیف درست";
                    break;
                case "InvalidCount":
                    InvalidCountText.Text = _vm.InvalidCount + " ردیف خطا";
                    break;
            }
        }

        private void ChooseFileButton_Click(object sender, RoutedEventArgs e)
        {
            var dialog = new Microsoft.Win32.OpenFileDialog();
            dialog.Title = "انتخاب فایل اکسل";
            dialog.Filter = "اکسل (*.xlsx)|*.xlsx|همه فایل‌ها (*.*)|*.*";
            dialog.CheckFileExists = true;

            if (dialog.ShowDialog(this) == true)
            {
                _vm.ChooseFile(dialog.FileName);
                FileSummaryText.Text = _vm.FileSummary;
                StatusText.Text = _vm.StatusMessage;
            }
        }

        private void TemplatePicker_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
        {
            if (_vm == null) return;
            _vm.SelectedTemplate = TemplatePicker.SelectedItem as TemplateChoice;
        }

        private void PreviewButton_Click(object sender, RoutedEventArgs e)
        {
            if (_vm == null) return;
            _vm.RunPreview();
            ValidCountText.Text = _vm.ValidCount + " ردیف درست";
            InvalidCountText.Text = _vm.InvalidCount + " ردیف خطا";
            FileSummaryText.Text = _vm.FileSummary;
            StatusText.Text = _vm.StatusMessage;
        }

        private void CommitButton_Click(object sender, RoutedEventArgs e)
        {
            if (_vm == null) return;

            // Explicit confirmation. A commit writes documents and cannot be
            // undone except through rollback, which an approved document
            // blocks. One click is too little for that.
            MessageBoxResult answer = MessageBox.Show(this,
                "این عملیات " + _vm.ValidCount + " ردیف را به‌صورت سند ثبت می‌کند.\n"
                + "پس از ثبت، تا زمانی که اسناد تأیید نشده‌اند می‌توانید از تاریخچه برگشت بزنید.\n\n"
                + "ادامه می‌دهید؟",
                "تأیید ثبت", MessageBoxButton.YesNo, MessageBoxImage.Question,
                MessageBoxResult.No);

            if (answer != MessageBoxResult.Yes) return;

            _vm.RunCommit();
            StatusText.Text = _vm.StatusMessage;
        }

        private void RefreshBatches_Click(object sender, RoutedEventArgs e)
        {
            if (_vm == null) return;
            _vm.RefreshBatches();
            StatusText.Text = _vm.StatusMessage;
        }

        private void Rollback_Click(object sender, RoutedEventArgs e)
        {
            if (_vm == null) return;
            var button = sender as System.Windows.Controls.Button;
            if (button == null) return;
            var row = button.Tag as BatchRow;
            if (row == null) return;

            if (!row.CanRollback)
            {
                MessageBox.Show(this,
                    "این دسته قابل برگشت نیست.\nوضعیت: " + row.StatusFa
                    + "\n\nفقط دسته‌های «منتظر تأیید» قابل برگشت‌اند. "
                    + "سند تأییدشده تغییرناپذیر است و اصلاحش با سند معکوس انجام می‌شود.",
                    "برگشت ممکن نیست", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            MessageBoxResult answer = MessageBox.Show(this,
                "دسته " + row.Code + " حذف می‌شود.\n"
                + "همه اسنادی که این دسته ساخته است پاک خواهند شد. این کار برگشت‌ناپذیر است.\n\n"
                + "برگشت بزنم؟",
                "تأیید برگشت", MessageBoxButton.YesNo, MessageBoxImage.Warning,
                MessageBoxResult.No);

            if (answer != MessageBoxResult.Yes) return;

            _vm.RollbackBatch(row);
            StatusText.Text = _vm.StatusMessage;
        }
    }
}
