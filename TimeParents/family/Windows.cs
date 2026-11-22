using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32;
using Microsoft.Win32.SafeHandles;
using System.Web.Script.Serialization;

namespace TimeParents.Family
{
    internal static class Store
    {
        internal const string Key = @"SOFTWARE\TimeParents\Family";
        internal const string Service = "TimeParentsFamily";
        internal const string Pipe = "TimeParents.Family.v1";
        internal static readonly string InstalledExe = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "TimeParents Family", "TimeParents.Family.exe");

        internal static T Read<T>(string path, string name) where T : class
        {
            using (var key = Registry.LocalMachine.OpenSubKey(Key + path))
            {
                string value = key == null ? null : key.GetValue(name) as string;
                return value == null ? null : Serializer().Deserialize<T>(value);
            }
        }

        internal static void Write(string path, string name, object value)
        {
            using (var key = Registry.LocalMachine.CreateSubKey(Key + path))
                key.SetValue(name, Json(value), RegistryValueKind.String);
        }

        internal static string Json(object x) { return Serializer().Serialize(x); }
        private static JavaScriptSerializer Serializer()
        {
            return new JavaScriptSerializer { MaxJsonLength = 32 * 1024 * 1024 };
        }

        internal static string[] Children()
        {
            using (var key = Registry.LocalMachine.OpenSubKey(Key + @"\Rules"))
                return key == null ? new string[0] : key.GetValueNames();
        }

        internal static bool HasChildShell(string sid)
        {
            string shell = Registry.GetValue(@"HKEY_USERS\" + sid +
                @"\Software\Microsoft\Windows\CurrentVersion\Policies\System", "Shell", "") as string;
            return String.Equals(shell, "\"" + InstalledExe + "\" --child", StringComparison.OrdinalIgnoreCase);
        }
    }

    internal static class Native
    {
        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern bool GetNamedPipeClientSessionId(SafePipeHandle pipe, out int session);
        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe, out int pid);
        [DllImport("kernel32.dll")] private static extern bool GetNamedPipeServerProcessId(SafePipeHandle pipe, out int pid);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr OpenSCManager(string machine, string db, int access);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr OpenService(IntPtr scm, string name, int access);
        [StructLayout(LayoutKind.Sequential)]
        private struct ServiceInfo { public int Type, State, Accepts, Exit, ServiceExit, Checkpoint, Hint, Pid, Flags; }
        [DllImport("advapi32.dll")] private static extern bool QueryServiceStatusEx(IntPtr service, int level, out ServiceInfo info, int size, out int needed);
        [DllImport("advapi32.dll")] private static extern bool CloseServiceHandle(IntPtr service);
        internal static bool IsBroker(SafePipeHandle pipe)
        {
            int pid, needed;
            if (!GetNamedPipeServerProcessId(pipe, out pid)) return false;
            IntPtr scm = OpenSCManager(null, null, 1);
            if (scm == IntPtr.Zero) return false;
            try
            {
                IntPtr service = OpenService(scm, Store.Service, 4);
                if (service == IntPtr.Zero) return false;
                try {
                    ServiceInfo info;
                    return QueryServiceStatusEx(service, 0, out info, Marshal.SizeOf(typeof(ServiceInfo)), out needed)
                        && info.State == 4 && info.Pid == pid;
                }
                finally { CloseServiceHandle(service); }
            }
            finally { CloseServiceHandle(scm); }
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct SessionInfo { public int Id; public IntPtr Station; public int State; }
        [DllImport("wtsapi32.dll", CharSet = CharSet.Unicode)]
        private static extern bool WTSEnumerateSessions(IntPtr server, int reserved, int version, out IntPtr rows, out int count);
        [DllImport("wtsapi32.dll")] private static extern void WTSFreeMemory(IntPtr data);
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct ExtendedSession {
            public uint Id; public int State, Flags;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=33)] public string Station;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=21)] public string User;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=18)] public string Domain;
            public long Logon, Connect, Disconnect, Input, Current;
            public uint InBytes, OutBytes, InFrames, OutFrames, InCompressed, OutCompressed;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct SessionDetails { public uint Level; public ExtendedSession Data; }
        [DllImport("wtsapi32.dll", CharSet = CharSet.Unicode)]
        private static extern bool WTSQuerySessionInformation(IntPtr server, int id, int infoClass, out IntPtr data, out int bytes);
        internal static bool SessionTimes(int id, ref long login, out bool locked)
        {
            locked = false;
            IntPtr buffer; int bytes;
            if (!WTSQuerySessionInformation(IntPtr.Zero, id, 25, out buffer, out bytes)) return false;
            try {
                if (bytes < Marshal.SizeOf(typeof(SessionDetails))) return false;
                var info = (SessionDetails)Marshal.PtrToStructure(buffer, typeof(SessionDetails));
                if (info.Level != 1 || info.Data.Id != (uint)id) return false;
                locked = info.Data.Flags == 0;
                if (info.Data.Logon > 0)
                    login = Math.Min(login, new DateTimeOffset(DateTime.FromFileTimeUtc(info.Data.Logon)).ToUnixTimeSeconds());
                return info.Data.Flags == 0 || info.Data.Flags == 1;
            }
            finally { WTSFreeMemory(buffer); }
        }
        internal static List<int> ActiveSessions()
        {
            var result = new List<int>(); IntPtr rows; int count;
            if (!WTSEnumerateSessions(IntPtr.Zero, 0, 1, out rows, out count)) return result;
            try {
                for (int i = 0; i < count; i++) {
                    var s = (SessionInfo)Marshal.PtrToStructure(IntPtr.Add(rows, i * Marshal.SizeOf(typeof(SessionInfo))), typeof(SessionInfo));
                    if (s.Id > 0 && s.State == 0) result.Add(s.Id);
                }
            }
            finally { WTSFreeMemory(rows); }
            return result;
        }
        [DllImport("wtsapi32.dll", SetLastError = true)]
        internal static extern bool WTSLogoffSession(IntPtr server, int session, bool wait);
        [DllImport("wtsapi32.dll", SetLastError = true)]
        private static extern bool WTSQueryUserToken(int session, out IntPtr token);
        [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr h);

        internal static string UserSid(int session)
        {
            IntPtr token;
            if (!WTSQueryUserToken(session, out token)) return null;
            try { using (var id = new WindowsIdentity(token)) return id.User.Value; }
            finally { CloseHandle(token); }
        }

        // A separate input desktop prevents minimizing the picker onto the normal desktop.
        [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        internal static extern IntPtr CreateDesktop(string name, IntPtr device, IntPtr devmode,
            uint flags, uint access, IntPtr security);
        [DllImport("user32.dll", SetLastError = true)] internal static extern bool SetThreadDesktop(IntPtr desktop);
        [DllImport("user32.dll", SetLastError = true)] internal static extern bool SwitchDesktop(IntPtr desktop);
        [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern bool GetUserObjectInformation(
            IntPtr handle, int index, System.Text.StringBuilder name, int length, out int needed);
        private static string DesktopName(IntPtr handle)
        {
            var value = new System.Text.StringBuilder(256);
            int needed;
            return GetUserObjectInformation(handle, 2, value, value.Capacity * 2, out needed) ? value.ToString() : null;
        }
        internal static bool SelectDesktop(IntPtr target, IntPtr other)
        {
            IntPtr input = OpenInputDesktop(0, false, 1);
            if (input == IntPtr.Zero) return false;
            try
            {
                string name = DesktopName(input);
                if (name == null) return false;
                if (name == DesktopName(target)) return true;
                // Never switch away from a Windows sign-in, UAC or other secure desktop.
                return name == DesktopName(other) && SwitchDesktop(target);
            }
            finally { CloseDesktop(input); }
        }
        [DllImport("user32.dll")] internal static extern bool CloseDesktop(IntPtr desktop);
        [DllImport("user32.dll")] internal static extern IntPtr GetThreadDesktop(uint id);
        [DllImport("kernel32.dll")] internal static extern uint GetCurrentThreadId();
        [DllImport("user32.dll", SetLastError = true)] internal static extern bool ExitWindowsEx(uint flags, uint reason);
        [DllImport("user32.dll")] internal static extern IntPtr GetShellWindow();

        internal static void StartExplorer()
        {
            if (GetShellWindow() == IntPtr.Zero)
                Process.Start(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "explorer.exe"));
        }
    }
}

