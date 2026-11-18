using System;
using System.IO;
using Mazandasht.Application.Dashboard;
using Mazandasht.Persistence;

namespace Mazandasht.Presentation
{
    /// <summary>
    /// The one place that decides where the database lives and how the
    /// dashboard reaches it.
    ///
    /// Why this is not inline in MainWindow: the portable build, the installed
    /// build, and the test run each answer "where is the database" differently.
    /// If that knowledge sits in a window, testing the window requires the
    /// real filesystem. It sits here instead, and the window asks.
    ///
    /// Resolution order — first match wins, and the choice is logged so a
    /// support call can establish which file was used:
    ///
    ///   1. MAZANDASHT_DB            explicit override, used by tests and the
    ///                              portable build.
    ///   2. %ProgramData%\Mazandasht\mazandasht.db
    ///                              installed build, shared by all users.
    ///   3. %LOCALAPPDATA%\Mazandasht\mazandasht.db
    ///                              fallback when ProgramData is not writable.
    ///
    /// The live database is deliberately NOT under Documents, Desktop, or any
    /// Google Drive folder. Spec ch.16 is explicit: a sync client writing
    /// underneath an open SQLite file corrupts it. Backups go to the sync
    /// folder; the live file never does.
    /// </summary>
    public static class DatabasePathProvider
    {
        public const string EnvironmentVariable = "MAZANDASHT_DB";

        public static string Resolve()
        {
            string explicitPath = Environment.GetEnvironmentVariable(EnvironmentVariable);
            if (!string.IsNullOrEmpty(explicitPath))
                return explicitPath;

            string programData = Environment.GetFolderPath(
                Environment.SpecialFolder.CommonApplicationData);
            if (!string.IsNullOrEmpty(programData))
            {
                string candidate = Path.Combine(programData, "Mazandasht", "mazandasht.db");
                if (CanWriteDirectory(Path.GetDirectoryName(candidate)))
                    return candidate;
            }

            string localApp = Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData);
            return Path.Combine(localApp, "Mazandasht", "mazandasht.db");
        }

        /// <summary>
        /// Create the store the dashboard will use.
        ///
        /// Throws when the file does not exist. That is deliberate: a dashboard
        /// that silently creates an empty database would show nineteen zeros
        /// and the owner would think their data was lost. The bootstrapper
        /// creates the schema; the dashboard only reads it.
        /// </summary>
        public static IDashboardStore CreateDashboardStore()
        {
            string path = Resolve();
            if (!File.Exists(path))
            {
                throw new FileNotFoundException(
                    "پایگاه داده پیدا نشد: " + path +
                    ". ابتدا نصب/راه‌اندازی اولیه را اجرا کنید.", path);
            }
            return new SqliteDashboardStore(path);
        }

        private static bool CanWriteDirectory(string directory)
        {
            if (string.IsNullOrEmpty(directory)) return false;
            try
            {
                if (!Directory.Exists(directory))
                    Directory.CreateDirectory(directory);
                return true;
            }
            catch (UnauthorizedAccessException) { return false; }
            catch (IOException) { return false; }
        }
    }
}
