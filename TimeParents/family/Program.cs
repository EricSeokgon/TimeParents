using System;
using System.Diagnostics;
using System.IO;
using System.Security.Principal;
using System.ServiceProcess;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace TimeParents.Family
{
    internal static class Program
    {
        internal static bool ChildPolicyPresent()
        {
            string policy = Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Policies\System", "Shell", "") as string;
            return String.Equals(policy, "\"" + Store.InstalledExe + "\" --child", StringComparison.OrdinalIgnoreCase);
        }
        internal static void Setup(string action, string account = null)
        {
            string script = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Setup.ps1");
            string ps = Path.Combine(Environment.SystemDirectory, @"WindowsPowerShell\v1.0\powershell.exe");
            var info = new ProcessStartInfo(ps, "-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File \"" +
                script + "\" -Action " + action) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardError = true };
            info.EnvironmentVariables["TIMEPARENTS_SETUP_ACCOUNT"] = account ?? "";
            using (var child = Process.Start(info))
            {
                string error = child.StandardError.ReadToEnd(); child.WaitForExit();
                if (child.ExitCode != 0) throw new InvalidOperationException(error.Trim());
            }
        }

        [STAThread]
        internal static int Main(string[] args)
        {
            string mode = args.Length == 1 ? args[0] : "";
            if (mode == "--service")
            {
                ServiceBase.Run(new FamilyService()); return 0;
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                if (mode == "--child")
                {
                    if (!ChildPolicyPresent() ||
                        !String.Equals(Application.ExecutablePath, Store.InstalledExe, StringComparison.OrdinalIgnoreCase)) return 2;
                    bool first;
                    using (var mutex = new Mutex(true, @"Local\TimeParentsFamilyChild", out first))
                        if (first) Application.Run(new ChildSession());
                    return 0;
                }
                if (mode != "--manage") return 2;
                if (!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator))
                    throw new InvalidOperationException("부모 관리자 계정에서 자녀 모드를 여세요.");
                using (var key = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\" + Store.Service))
                    if (key == null)
                    {
                        if (MessageBox.Show("자녀 계정의 시간과 기록을 관리할 Windows 서비스를 설치할까요?\n계정은 다음 화면에서 직접 선택합니다.",
                            "TimeParents", MessageBoxButtons.YesNo) != DialogResult.Yes) return 0;
                        Setup("Install");
                    }
                if (!String.Equals(Application.ExecutablePath, Store.InstalledExe, StringComparison.OrdinalIgnoreCase))
                {
                    Process.Start(Store.InstalledExe, "--manage"); return 0;
                }
                using (var controller = new ServiceController(Store.Service))
                    if (controller.Status == ServiceControllerStatus.Stopped)
                    { controller.Start(); controller.WaitForStatus(ServiceControllerStatus.Running, TimeSpan.FromSeconds(15)); }
                Application.Run(new Manager());
                return 0;
            }
            catch (Exception ex) { MessageBox.Show(ex.Message, "TimeParents", MessageBoxButtons.OK, MessageBoxIcon.Error); return 1; }
        }
    }
}

