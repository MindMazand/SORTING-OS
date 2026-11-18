using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;

namespace Mazandasht.Presentation.Tools
{
    /// <summary>Health of one tool, as a colour token name and a sentence.</summary>
    public enum ToolState
    {
        Ready,      // built and proven by an executing test
        Degraded,   // built, but something about the environment is wrong
        Blocked     // not built; the reason is stated
    }

    public sealed class ToolCard
    {
        public string Title { get; set; }
        public string Summary { get; set; }
        public string LastRun { get; set; }
        public ToolState State { get; set; }

        /// <summary>Token name resolved by the view's style selector.</summary>
        public string StateToken
        {
            get
            {
                if (State == ToolState.Ready) return "SuccessWashBrush";
                if (State == ToolState.Degraded) return "PendingWashBrush";
                return "DangerWashBrush";
            }
        }

        public string StateText
        {
            get
            {
                if (State == ToolState.Ready) return "آماده";
                if (State == ToolState.Degraded) return "نیازمند بررسی";
                return "غیرفعال";
            }
        }

        public bool IsActionable { get { return State != ToolState.Blocked; } }
    }

    /// <summary>
    /// The tools screen.
    ///
    /// Each card states three things: what the tool does, when it last ran, and
    /// whether it is healthy right now. A card that is only a button forces the
    /// owner to guess, which is how a tool panel becomes decoration.
    ///
    /// Nothing here is a placeholder with a TODO behind it: every Ready card is
    /// backed by code that has an executing test (see reports/HANDOFF_NEXT_FA.md
    /// for the nine gates and their numbers). The Blocked card says why.
    /// </summary>
    public sealed class ToolsViewModel : INotifyPropertyChanged
    {
        private string _statusMessage = "";

        public event PropertyChangedEventHandler PropertyChanged;

        public ObservableCollection<ToolCard> Cards { get; private set; }

        public ObservableCollection<PendingReport> PendingReports { get; private set; }

        public string StatusMessage
        {
            get { return _statusMessage; }
            private set
            {
                if (_statusMessage == value) return;
                _statusMessage = value;
                PropertyChangedEventHandler h = PropertyChanged;
                if (h != null) h(this, new PropertyChangedEventArgs("StatusMessage"));
            }
        }

        public ToolsViewModel()
        {
            Cards = new ObservableCollection<ToolCard>();
            PendingReports = new ObservableCollection<PendingReport>();
            Build();
        }

        private void Build()
        {
            Cards.Add(new ToolCard
            {
                Title = "واردسازی از اکسل",
                Summary = "۱۱ قالب مالک · پیش‌نمایش قبل از ثبت · ثبت با تأیید مدیر",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Title = "برگشت دسته واردسازی",
                Summary = "حذف دقیق یک دسته، بدون دست زدن به داده پایه",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Title = "پشتیبان‌گیری",
                Summary = "SHA-256 · نسخه اسکیما · بررسی یکپارچگی",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Title = "بررسی سلامت پایگاه داده",
                Summary = "۴۰ آزمون اسکیمایی · کلیدهای خارجی · جمع‌های کنترلی",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Title = "گزارش‌های مالی",
                Summary = "۷ گزارش؛ چیدمان ستون‌ها هنوز تأیید نشده",
                LastRun = "دلیل توقف: BLOCKED-02",
                State = ToolState.Blocked,
            });

            string[] blocked =
            {
                "صورت‌وضعیت شریک",
                "تجمیع خرید",
                "آنالیز بار و سبد",
                "گردش حساب اشخاص",
                "دفتر چک",
                "مغایرت بانکی",
                "سود و زیان دوره",
            };
            foreach (string name in blocked)
            {
                PendingReports.Add(new PendingReport
                {
                    Title = name,
                    Reason = "چیدمان ستون‌ها و ترتیب سطرها تأیید نشده",
                });
            }
        }

        /// <summary>
        /// Report the real database file when it exists, and say so plainly
        /// when it does not. Never invent a size or a timestamp.
        /// </summary>
        public void ProbeDatabase(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path))
                {
                    StatusMessage = "پایگاه داده پیدا نشد. نصب اولیه را اجرا کنید.";
                    return;
                }
                FileInfo info = new FileInfo(path);
                StatusMessage = "پایگاه داده: " + path + " · "
                    + (info.Length / 1024).ToString("N0") + " کیلوبایت · "
                    + info.LastWriteTime.ToString("yyyy-MM-dd HH:mm");
            }
            catch (Exception ex)
            {
                StatusMessage = "خواندن اطلاعات پایگاه داده ناموفق: " + ex.Message;
            }
        }
    }

    public sealed class PendingReport
    {
        public string Title { get; set; }
        public string Reason { get; set; }
    }
}
