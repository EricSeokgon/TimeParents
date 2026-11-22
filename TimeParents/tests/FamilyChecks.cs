using System;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Threading;
using System.Web.Script.Serialization;
using TimeParents.Family;

// Run without installing the service or changing the interactive desktop.
class FamilyChecks
{
    static int checks;
    static void Check(bool ok, string name)
    {
        if (!ok) throw new Exception(name);
        checks++; Console.WriteLine("PASS " + name);
    }
    static long At(int day, int hour, int minute, int second = 0)
    {
        return new DateTimeOffset(new DateTime(2026, 11, day, hour, minute, second, DateTimeKind.Local)).ToUnixTimeSeconds();
    }
    static void Advance(Ledger b, Rule r, QuietHours q, long t, int n)
    { for (int i = 1; i <= n; i++) b.Tick(r, q, t + i); }
    static void Transport()
    {
        string name = "TimeParentsTest-" + Guid.NewGuid().ToString("N");
        var acl = new PipeSecurity();
        using (var identity = WindowsIdentity.GetCurrent())
            acl.AddAccessRule(new PipeAccessRule(identity.User, PipeAccessRights.FullControl, AccessControlType.Allow));
        using (var server = new NamedPipeServerStream(name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous, 512, 512, acl))
        {
            var worker = new Thread(delegate() {
                server.WaitForConnection();
                var r = new BinaryReader(server);
                if (r.ReadByte() != 'B' || r.ReadInt32() != 600) return;
                int pid, sessionId;
                Check(Native.GetNamedPipeClientSessionId(server.SafePipeHandle, out sessionId) &&
                    sessionId == System.Diagnostics.Process.GetCurrentProcess().SessionId, "client session comes from Windows");
                Check(Native.GetNamedPipeClientProcessId(server.SafePipeHandle, out pid) &&
                    pid == System.Diagnostics.Process.GetCurrentProcess().Id, "client process comes from Windows");
                string peer = null;
                server.RunAsClient(delegate { using (var id = WindowsIdentity.GetCurrent(true)) peer = id.User.Value; });
                using (var own = WindowsIdentity.GetCurrent())
                    Check(peer == own.User.Value, "pipe caller identity comes from the Windows token");
                var writer = new BinaryWriter(server); writer.Write(true); writer.Flush();
            }) { IsBackground = true };
            worker.Start();
            using (var client = new NamedPipeClientStream(".", name, PipeAccessRights.ReadData | PipeAccessRights.WriteData |
                PipeAccessRights.Synchronize, PipeOptions.None, TokenImpersonationLevel.Identification, HandleInheritability.None))
            {
                client.Connect(1000);
                Check(!Native.IsBroker(client.SafePipeHandle), "an unregistered pipe server cannot authorize the desktop");
                var w = new BinaryWriter(client); w.Write((byte)'B'); w.Write(600); w.Flush();
                Check(new BinaryReader(client).ReadBoolean(), "Windows pipe transport");
            }
            worker.Join(2000);
        }
    }

    [STAThread]
    static int Main()
    {
        var r = new Rule { Weekday = 30, Weekend = 60, Enabled = true };
        var q = new QuietHours { Enabled = true, Start = 21*60, End = 7*60 };
        long t = At(21, 16, 0);
        var a = new Ledger(); var b = new Ledger();
        a.Login(t); b.Login(t + 10);
        Check(a.UsedToday(t) == 0 && a.Active.Start == 0, "login alone does not consume time");
        Check(a.Begin(1200, r, q, t, t), "child chooses a session");
        Check(!a.Begin(60, r, q, t, t), "duplicate start preserves active session");
        Advance(a, r, q, t, 720);
        a.Close(t + 720, "early");
        Check(a.Budget(r,t) == 2880 && b.Budget(r,t) == 3600, "early finish and sibling isolation");
        b.Close(t + 30, "logoff");
        Check(b.Visits[0].Used == 0 && b.Visits[0].Start == 0, "logout without choosing a time is recorded");
        a.Begin(7200, r, q, t + 720, t);
        Check(a.Active.Selected == 480, "early end retains original choice on restart");
        Advance(a,r,q,t + 720,480);
        a.Begin(7200, r, q, t + 1200, t);
        Check(a.Active.Selected == 2400, "new session clamped to remaining daily allowance");
        Advance(a,r,q,t + 1200,2400);
        Check(a.Active == null && a.Budget(r,t) == 0 && !a.Begin(1,r,q,t+3600,t), "expired quota cannot be reused");
        r.ExtraDay = Ledger.Day(t); r.ExtraMinutes = 10;
        Check(a.Budget(r,t) == 600 && a.Budget(r,At(22,12,0)) == 3600, "bonus expires on local date change");
        Check(a.Budget(r,At(23,12,0)) == 1800, "weekday allowance");
        long near = At(22,20,59,50);
        var c = new Ledger(); c.Login(near); c.Begin(600,r,q,near,near);
        Check(c.Active.Selected == 10, "curfew truncates a session");
        Advance(c,r,q,near,11);
        Check(c.Active == null && c.UsedToday(near) == 10 && !c.Begin(60,r,q,near+11,near), "overnight curfew enforced");
        Check(c.Available(r,q,At(23,6,59)) == 0 && c.Available(r,q,At(23,7,0)) == 1800, "curfew endpoint");
        q.Enabled = false;
        long midnight = At(22,23,59,58);
        c.Begin(60,r,q,midnight,midnight);
        Advance(c,r,q,midnight,3);
        Check(c.Active == null && c.UsedToday(midnight+3) == 0, "midnight splits daily quota");
        var d = new Ledger(); d.Login(t); d.Begin(600,r,q,t,t); d.Tick(r,q,t+5);
        d.Close(t+5,"locked"); d.Tick(r,q,t+500);
        Check(d.UsedToday(t) == 5 && d.Active == null, "locked time not billed");
        Check(d.UnfinishedSeconds(t+500) == 595 && d.UnfinishedSeconds(At(22,12,0)) == 0, "resume only on the same day");
        d.Begin(60,r,q,t+500,t); d.Tick(r,q,t+501); d.Tick(r,q,t+700);
        Check(d.UsedToday(t)==6 && d.Active==null, "long sleep gap not billed");
        d.Begin(60,r,q,t+710,t); d.Tick(r,q,t+712);
        var json = new JavaScriptSerializer(); var copy = json.Deserialize<Ledger>(json.Serialize(d));
        copy.Login(t+800);
        Check(copy.UsedToday(t)==8 && copy.Visits[2].End==t+712 && copy.Active.Start==0, "restart retains verified usage only");
        Check(copy.UnfinishedSeconds(t+800)==592, "login without usage preserves saved session balance");
        var reduced = new Ledger(); reduced.Login(t); reduced.Begin(600, r, q, t, t);
        Advance(reduced, r, q, t, 4);
        var noTime = new Rule { Enabled = true };
        reduced.Tick(noTime, q, t+5);
        Check(reduced.Active == null && reduced.UsedToday(t) == 4, "parent can reduce a running allowance");
        Check(!reduced.Begin(-5, r, q, t+6, t), "invalid duration rejected");
        Transport();
        Console.WriteLine(checks + " checks passed."); return 0;
    }
}

