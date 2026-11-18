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

    public sealed class ToolCard : INotifyPropertyChanged
    {
        private string _lastRun = "";
        private ToolState _state;

        public event PropertyChangedEventHandler PropertyChanged;

        /// <summary>Stable id the probe uses to fill LastRun. Titles are for
        /// humans and will be edited; an index would break silently.</summary>
        public string Key { get; set; }
        public string Title { get; set; }
        public string Summary { get; set; }
        /// <summary>
        /// Notifying properties, not auto-properties. The cards are created
        /// once and the probe fills LastRun afterwards; a plain property would
        /// leave the screen showing the construction-time text forever, which
        /// looks exactly like "the probe did not run".
        /// </summary>
        public string LastRun
        {
            get { return _lastRun; }
            set
            {
                if (_lastRun == value) return;
                _lastRun = value;
                Raise("LastRun");
            }
        }

        public ToolState State
        {
            get { return _state; }
            set
            {
                if (_state == value) return;
                _state = value;
                Raise("State");
                Raise("StateToken");
                Raise("StateText");
                Raise("IsActionable");
            }
        }

        private void Raise(string name)
        {
            PropertyChangedEventHandler h = PropertyChanged;
            if (h != null) h(this, new PropertyChangedEventArgs(name));
        }

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
                Key = "IMPORT",
                Title = "واردسازی از اکسل",
                Summary = "۱۱ قالب مالک · پیش‌نمایش قبل از ثبت · ثبت با تأیید مدیر",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Key = "ROLLBACK",
                Title = "برگشت دسته واردسازی",
                Summary = "حذف دقیق یک دسته، بدون دست زدن به داده پایه",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Key = "BACKUP",
                Title = "پشتیبان‌گیری",
                Summary = "SHA-256 · نسخه اسکیما · بررسی یکپارچگی",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Key = "HEALTH",
                Title = "بررسی سلامت پایگاه داده",
                Summary = "۴۰ آزمون اسکیمایی · کلیدهای خارجی · جمع‌های کنترلی",
                LastRun = "آخرین اجرا: —",
                State = ToolState.Ready,
            });
            Cards.Add(new ToolCard
            {
                Key = "REPORTS",
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
        /// <summary>
        /// Fill each card's LastRun from the real database, and adjust its state
        /// when the evidence does not support "Ready".
        ///
        /// Why this exists: the first version of this screen printed
        /// "آخرین اجرا: —" on every card. A card that says Ready and has never
        /// run is a claim without evidence — precisely what this project keeps
        /// having to correct. If the database has no batches, the import card
        /// says so instead of implying it has been used.
        /// </summary>
        public void ProbeDatabase(string path)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !File.Exists(path))
                {
                    StatusMessage = "پایگاه داده پیدا نشد. نصب اولیه را اجرا کنید.";
                    SetState("IMPORT", ToolState.Degraded, "بدون پایگاه داده");
                    SetState("ROLLBACK", ToolState.Degraded, "بدون پایگاه داده");
                    SetState("BACKUP", ToolState.Degraded, "بدون پایگاه داده");
                    SetState("HEALTH", ToolState.Degraded, "بدون پایگاه داده");
                    return;
                }

                FileInfo info = new FileInfo(path);
                StatusMessage = "پایگاه داده: " + path + " · "
                    + (info.Length / 1024).ToString("N0") + " کیلوبایت · "
                    + info.WriteTimeText();

                using (var probe = new DatabaseProbe(path))
                {
                    long batches = probe.Scalar(
                        "SELECT COUNT(*) FROM import_batches");
                    long rolled = probe.Scalar(
                        "SELECT COUNT(*) FROM import_batches WHERE status='ROLLED_BACK'");
                    long pending = probe.Scalar(
                        "SELECT COUNT(*) FROM import_batches WHERE status='REVIEW'");
                    string lastImport = probe.Text(
                        "SELECT MAX(created_at) FROM import_batches");
                    long audit = probe.Scalar("SELECT COUNT(*) FROM audit_events");
                    string lastAudit = probe.Text(
                        "SELECT MAX(created_at) FROM audit_events");

                    SetLastRun("IMPORT", batches == 0
                        ? "هنوز هیچ فایلی وارد نشده"
                        : batches.ToString("N0") + " دسته · آخرین: " + When(lastImport));

                    SetLastRun("ROLLBACK", rolled == 0
                        ? "هیچ دسته‌ای برگشت نخورده"
                        : rolled.ToString("N0") + " برگشت · "
                          + pending.ToString("N0") + " دسته منتظر تأیید");

                    // Backup has no in-database timestamp by design: the manifest
                    // is a file next to the copy, not a table row. Say so rather
                    // than inventing a date.
                    SetLastRun("BACKUP", "زمان آخرین نسخه در فایل مانیفست است، نه در پایگاه داده");

                    string integrity = probe.IntegrityCheck();
                    SetLastRun("HEALTH", integrity == "ok"
                        ? "آخرین اجرا: همین حالا · integrity_check: ok"
                        : "integrity_check: " + integrity);
                    if (integrity != "ok")
                        SetState("HEALTH", ToolState.Degraded, integrity);

                    SetLastRun("REPORTS", "دلیل توقف: BLOCKED-02");

                    if (audit > 0)
                        StatusMessage += " · حسابرسی: " + audit.ToString("N0")
                            + " رویداد · آخرین: " + When(lastAudit);
                    else
                        StatusMessage += " · حسابرسی: هیچ رویدادی ثبت نشده";
                }
            }
            catch (Exception ex)
            {
                StatusMessage = "خواندن اطلاعات پایگاه داده ناموفق: " + ex.Message;
            }
        }

        /// <summary>
        /// Setting the property is enough: ToolCard raises its own
        /// PropertyChanged. An earlier version also called Raise("Cards") on the
        /// view model, which is meaningless (there is no Cards notification the
        /// view listens to) and papered over the fact that ToolCard was not
        /// notifying at all.
        /// </summary>
        private void SetLastRun(string key, string text)
        {
            foreach (ToolCard c in Cards)
                if (c.Key == key) { c.LastRun = text; return; }
        }

        private void SetState(string key, ToolState state, string text)
        {
            foreach (ToolCard c in Cards)
            {
                if (c.Key != key) continue;
                c.State = state;
                if (!string.IsNullOrEmpty(text)) c.LastRun = text;
                return;
            }
        }

        /// <summary>
        /// Format a stored timestamp for display.
        ///
        /// The schema stores created_at as "YYYY-MM-DD HH:MM:SS" — a SPACE, not
        /// an ISO "T". An earlier version of this method sliced at a fixed
        /// offset assuming the T form and produced "2026-11-1808:43" on real
        /// rows. Parse the actual separators instead of assuming one.
        /// </summary>
        private static string When(string iso)
        {
            if (string.IsNullOrEmpty(iso)) return "—";
            // Accept both "2026-11-17 14:32:07" and "2026-11-17T14:32:07".
            string normalised = iso.Replace('T', ' ');
            if (normalised.Length >= 16)
                return normalised.Substring(0, 16);
            return normalised;
        }
    }

    public sealed class PendingReport
    {
        public string Title { get; set; }
        public string Reason { get; set; }
    }
}
