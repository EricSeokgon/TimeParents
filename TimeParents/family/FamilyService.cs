using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Threading;

namespace TimeParents.Family
{
    internal sealed class FamilyService : ServiceBase
    {
        private sealed class Session
        {
            internal string Sid;
            internal int Id;
            internal Ledger Book;
            internal long Login, GateConfirmed, LastSave;
            internal bool Locked, Disconnected, Suspended, Attached;
            internal bool Paused { get { return Locked || Disconnected || Suspended; } }
        }

        private readonly Dictionary<int, Session> sessions = new Dictionary<int, Session>();
        private readonly object sync = new object();
        private Timer timer;
        private volatile bool stopping;
        private NamedPipeServerStream listener;

        public FamilyService()
        {
            ServiceName = Store.Service;
            CanHandleSessionChangeEvent = true;
            CanHandlePowerEvent = true;
            CanShutdown = true;
        }

        protected override void OnStart(string[] args)
        {
            stopping = false;
            foreach (string sid in Store.Children())
            {
                var book = Store.Read<Ledger>(@"\History", sid);
                if (book != null && book.Active != null)
                {
                    book.Close(book.Active.Seen, "interrupted");
                    Store.Write(@"\History", sid, book);
                }
            }
            // Recover enforcement even if the broker restarted while the user interface was closed.
            foreach (int id in Native.ActiveSessions())
            {
                string sid = Native.UserSid(id);
                var rule = sid == null ? null : Store.Read<Rule>(@"\Rules", sid);
                if (rule != null && rule.Enabled && Store.HasChildShell(sid)) GetSession(id, sid, Ledger.Now());
            }
            new Thread(Listen) { IsBackground = true }.Start();
            timer = new Timer(Poll, null, 1000, 1000);
        }

        private void Listen()
        {
            var acl = new PipeSecurity();
            acl.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.NetworkSid, null),
                PipeAccessRights.FullControl, AccessControlType.Deny));
            acl.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
                PipeAccessRights.FullControl, AccessControlType.Allow));
            // Do not grant CreateNewInstance to clients.
            acl.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.AuthenticatedUserSid, null),
                PipeAccessRights.ReadData | PipeAccessRights.WriteData | PipeAccessRights.Synchronize |
                PipeAccessRights.ReadAttributes, AccessControlType.Allow));
            while (!stopping)
            {
                NamedPipeServerStream pipe = null;
                try
                {
                    pipe = new NamedPipeServerStream(Store.Pipe, PipeDirection.InOut, 16,
                        PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 512, 512, acl);
                    lock (sync) { if (stopping) { pipe.Dispose(); break; } listener = pipe; }
                    pipe.WaitForConnection();
                    var accepted = pipe;
                    ThreadPool.QueueUserWorkItem(delegate { Serve(accepted); });
                    pipe = null;
                }
                catch (Exception) { if (!stopping) Thread.Sleep(200); }
                finally { if (pipe != null) pipe.Dispose(); }
            }
        }

        private void Serve(NamedPipeServerStream pipe)
        {
            using (pipe)
            using (var timeout = new Timer(delegate { pipe.Dispose(); }, null, 3000, Timeout.Infinite))
            {
                try
                {
                    int session, pid;
                    if (!Native.GetNamedPipeClientSessionId(pipe.SafePipeHandle, out session) ||
                        !Native.GetNamedPipeClientProcessId(pipe.SafePipeHandle, out pid)) return;
                    using (var proc = Process.GetProcessById(pid))
                        if (!String.Equals(proc.MainModule.FileName, Store.InstalledExe, StringComparison.OrdinalIgnoreCase)) return;
                    using (var input = new BinaryReader(pipe, System.Text.Encoding.UTF8, true))
                    using (var output = new BinaryWriter(pipe, System.Text.Encoding.UTF8, true))
                    {
                        byte op = input.ReadByte();
                        int seconds = input.ReadInt32();
                        string sid = null;
                        pipe.RunAsClient(delegate { using (var id = WindowsIdentity.GetCurrent(true)) sid = id.User.Value; });
                        if (sid == null || sid != Native.UserSid(session)) return;
                        lock (sync)
                        {
                            var rule = Store.Read<Rule>(@"\Rules", sid);
                            bool enabled = !stopping && rule != null && rule.Enabled && Store.HasChildShell(sid) &&
                                !sessions.Values.Any(x => x.Sid == sid && x.Id != session && Native.UserSid(x.Id) == sid);
                            output.Write(enabled);
                            if (enabled)
                            {
                                long t = Ledger.Now();
                                var s = GetSession(session, sid, t);
                                s.Attached = true;
                                var quiet = Store.Read<QuietHours>("", "Quiet") ?? new QuietHours();
                                if (!s.Paused) s.Book.Tick(rule, quiet, t);
                                if (op == (byte)'G') s.GateConfirmed = t;
                                if (op == (byte)'B' && !s.Paused && seconds > 0 && seconds <= 86400)
                                    s.Book.Begin(seconds, rule, quiet, t, s.Login);
                                if (op == (byte)'R' && !s.Paused)
                                    s.Book.Begin(s.Book.UnfinishedSeconds(t), rule, quiet, t, s.Login);
                                if (op == (byte)'E') s.Book.Close(t, "early");
                                if (op == (byte)'X') s.Book.Close(t, "logoff");
                                var active = s.Book.Active;
                                int left = active == null || active.Start == 0 ? 0 : active.Selected - active.Used;
                                if (op == (byte)'B' || op == (byte)'R' || op == (byte)'E' || op == (byte)'X') Save(s, t);
                                output.Write(rule.Name ?? "");
                                output.Write(s.Book.Budget(rule, t));
                                output.Write(s.Paused ? 0 : s.Book.Available(rule, quiet, t));
                                output.Write(left);
                                output.Write(quiet.Enabled ? String.Format("{0:00}:{1:00}", quiet.Start / 60, quiet.Start % 60) : "");
                                output.Write(s.Book.UnfinishedSeconds(t));
                            }
                            output.Flush();
                        }
                    }
                }
                catch (Exception ex) { if (!(ex is IOException || ex is ObjectDisposedException)) Trace.TraceWarning(ex.Message); }
            }
        }

        private Session GetSession(int id, string sid, long t)
        {
            Session s;
            if (sessions.TryGetValue(id, out s) && s.Sid == sid) return s;
            // Windows normally reconnects the same local account to one session.
            foreach (var old in sessions.Values.Where(x => x.Sid == sid || x.Id == id).ToArray())
            {
                End(old, t, "switch");
                if (old.Id != id) SignOut(old);
            }
            var book = Store.Read<Ledger>(@"\History", sid) ?? new Ledger();
            long login = t; bool locked;
            Native.SessionTimes(id, ref login, out locked);
            book.Login(t);
            book.Active.Login = login;
            s = new Session { Sid = sid, Id = id, Login = login, GateConfirmed = t, Book = book, Locked = locked };
            sessions[id] = s;
            Save(s, t);
            return s;
        }

        private static void Save(Session s, long t)
        {
            Store.Write(@"\History", s.Sid, s.Book);
            s.LastSave = t;
        }

        private static void SignOut(Session s)
        {
            if (Native.UserSid(s.Id) == s.Sid)
                Native.WTSLogoffSession(IntPtr.Zero, s.Id, false);
        }

        private void End(Session s, long t, string reason)
        {
            var rule = Store.Read<Rule>(@"\Rules", s.Sid);
            if (rule != null) s.Book.Tick(rule, Store.Read<QuietHours>("", "Quiet") ?? new QuietHours(), t);
            s.Book.Close(t, reason);
            Save(s, t);
            sessions.Remove(s.Id);
        }

        private void Poll(object ignored)
        {
            lock (sync)
            {
                if (stopping) return;
                long t = Ledger.Now();
                var quiet = Store.Read<QuietHours>("", "Quiet") ?? new QuietHours();
                foreach (var s in sessions.Values.ToArray())
                {
                    var rule = Store.Read<Rule>(@"\Rules", s.Sid);
                    if (rule == null || !rule.Enabled) { End(s, t, "removed"); continue; }
                    if (s.Locked && t % 5 == 0)
                    {
                        bool locked; long login = s.Login;
                        if (Native.SessionTimes(s.Id, ref login, out locked) && !locked)
                        { s.Locked = false; s.GateConfirmed = t; }
                    }
                    if (s.Paused) continue;
                    bool playing = s.Book.Active != null && s.Book.Active.Start != 0;
                    s.Book.Tick(rule, quiet, t);
                    bool stillPlaying = s.Book.Active != null && s.Book.Active.Start != 0;
                    if (stillPlaying || playing) s.GateConfirmed = t;
                    // If selection UI crashes or cannot reclaim its desktop, Windows ends this child's session.
                    if (!stillPlaying && t - s.GateConfirmed > (s.Attached ? 15 : 90)) SignOut(s);
                    if (t - s.LastSave >= 5 || playing != stillPlaying) Save(s, t);
                }
            }
        }

        protected override void OnSessionChange(SessionChangeDescription e)
        {
            lock (sync)
            {
                long t = Ledger.Now();
                int id = e.SessionId;
                if (e.Reason == SessionChangeReason.SessionLogon)
                {
                    string sid = Native.UserSid(id);
                    if (sid != null) {
                        var rule = Store.Read<Rule>(@"\Rules", sid);
                        if (rule != null && rule.Enabled && Store.HasChildShell(sid)) GetSession(id, sid, t);
                    }
                    return;
                }
                Session s;
                if (!sessions.TryGetValue(id, out s)) return;
                if (e.Reason == SessionChangeReason.SessionLogoff) { End(s, t, "logoff"); return; }
                if (e.Reason == SessionChangeReason.SessionLock) { Pause(s, t, "locked"); s.Locked = true; }
                if (e.Reason == SessionChangeReason.ConsoleDisconnect || e.Reason == SessionChangeReason.RemoteDisconnect)
                { Pause(s, t, "switch"); s.Disconnected = true; }
                if (e.Reason == SessionChangeReason.SessionUnlock) { s.Locked = false; s.GateConfirmed = t; }
                if (e.Reason == SessionChangeReason.ConsoleConnect || e.Reason == SessionChangeReason.RemoteConnect)
                { s.Disconnected = false; s.GateConfirmed = t; }
            }
        }

        private static void Pause(Session s, long t, string reason)
        {
            var rule = Store.Read<Rule>(@"\Rules", s.Sid);
            if (rule != null) s.Book.Tick(rule, Store.Read<QuietHours>("", "Quiet") ?? new QuietHours(), t);
            s.Book.Close(t, reason);
            Save(s, t);
        }

        protected override bool OnPowerEvent(PowerBroadcastStatus status)
        {
            lock (sync)
            {
                foreach (var s in sessions.Values)
                {
                    if (status == PowerBroadcastStatus.Suspend) { Pause(s, Ledger.Now(), "sleep"); s.Suspended = true; }
                    if (status == PowerBroadcastStatus.ResumeAutomatic || status == PowerBroadcastStatus.ResumeSuspend)
                    { s.Suspended = false; s.GateConfirmed = Ledger.Now(); }
                }
            }
            return true;
        }

        protected override void OnStop()
        {
            lock (sync)
            {
                stopping = true;
                if (timer != null) timer.Dispose();
                if (listener != null) listener.Dispose();
                foreach (var s in sessions.Values.ToArray()) End(s, Ledger.Now(), "interrupted");
            }
        }
        protected override void OnShutdown() { OnStop(); }
    }
}

