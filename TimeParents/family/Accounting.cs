using System;
using System.Collections.Generic;
using System.Linq;

namespace TimeParents.Family
{
    public class Rule
    {
        public string Name { get; set; }
        public bool Enabled { get; set; }
        public int Weekday { get; set; }
        public int Weekend { get; set; }
        public string ExtraDay { get; set; }
        public int ExtraMinutes { get; set; }
    }

    public class QuietHours
    {
        public bool Enabled { get; set; }
        public int Start { get; set; }
        public int End { get; set; }

        public bool Contains(int minute)
        {
            return Enabled && (Start < End ? minute >= Start && minute < End :
                                             minute >= Start || minute < End);
        }
    }

    public class Visit
    {
        public long Login { get; set; }
        public long Start { get; set; }
        public long End { get; set; }
        public long Seen { get; set; }
        public int Selected { get; set; }
        public int Used { get; set; }
        public string Reason { get; set; }
    }

    // Times are UTC seconds. Each timed visit ends at local midnight at the latest.
    public class Ledger
    {
        public List<Visit> Visits { get; set; }
        public Ledger() { Visits = new List<Visit>(); }

        public static long Now() { return DateTimeOffset.UtcNow.ToUnixTimeSeconds(); }
        public static DateTime Local(long t) { return DateTimeOffset.FromUnixTimeSeconds(t).LocalDateTime; }
        public static string Day(long t) { return Local(t).ToString("yyyy-MM-dd"); }

        public int UsedToday(long t)
        {
            string day = Day(t);
            return Visits.Where(v => v.Start > 0 && Day(v.Start) == day).Sum(v => v.Used);
        }

        public int Budget(Rule rule, long t)
        {
            DayOfWeek day = Local(t).DayOfWeek;
            int minutes = day == DayOfWeek.Saturday || day == DayOfWeek.Sunday ? rule.Weekend : rule.Weekday;
            if (rule.ExtraDay == Day(t)) minutes += rule.ExtraMinutes;
            return Math.Max(0, minutes * 60 - UsedToday(t));
        }

        public int Available(Rule rule, QuietHours quiet, long t)
        {
            DateTime now = Local(t);
            if (quiet.Contains(now.Hour * 60 + now.Minute)) return 0;
            DateTime stop = now.Date.AddDays(1);
            DateTime quietStart = now.Date.AddMinutes(quiet.Start);
            if (quiet.Enabled && quietStart > now && quietStart < stop) stop = quietStart;
            int seconds = (int)(stop.ToUniversalTime() - now.ToUniversalTime()).TotalSeconds;
            return Math.Min(Budget(rule, t), Math.Max(0, seconds));
        }

        [System.Web.Script.Serialization.ScriptIgnore]
        public Visit Active { get { return Visits.LastOrDefault(v => v.End == 0); } }

        public void Login(long t)
        {
            if (Active != null) Close(Active.Seen, "interrupted");
            Visits.RemoveAll(v => v.End > 0 && v.End < t - 90L * 86400);
            Visits.Add(new Visit { Login = t, Seen = t });
        }

        public bool Begin(int seconds, Rule rule, QuietHours quiet, long t, long login)
        {
            if (seconds <= 0 || (Active != null && Active.Start != 0)) return false;
            int balance = UnfinishedSeconds(t);
            int grant = Math.Min(balance > 0 ? balance : seconds, Available(rule, quiet, t));
            if (grant <= 0) return false;
            if (Active == null) Visits.Add(new Visit { Login = login, Seen = t });
            Visit v = Active;
            v.Start = t; v.Seen = t; v.Selected = grant;
            return true;
        }

        public int UnfinishedSeconds(long t)
        {
            string today = Day(t);
            Visit v = Visits.LastOrDefault(row => row.Start > 0 && Day(row.Start) == today);
            if (v == null || v.End == 0 || v.Reason == "limit") return 0;
            return Math.Max(0, v.Selected - v.Used);
        }

        public void Close(long t, string reason)
        {
            Visit v = Active;
            if (v == null) return;
            v.End = Math.Max(v.Login, t); v.Reason = reason;
        }

        // Bound by the earliest deadline, even when a timer tick is delayed.
        public void Tick(Rule rule, QuietHours quiet, long t)
        {
            Visit v = Active;
            if (v == null) return;
            long previous = v.Seen;
            if (v.Start == 0) { v.Seen = t; return; }
            long delta = t - previous;
            if (delta < 0 || delta > 12)
            {
                Close(previous, "interrupted");
                return;
            }
            int allowed = Math.Min(v.Selected - v.Used, Available(rule, quiet, previous));
            int charge = (int)Math.Min(delta, allowed);
            v.Used += charge;
            v.Seen = previous + charge;
            if (charge >= allowed || Available(rule, quiet, t) == 0 || Day(t) != Day(v.Start))
                Close(v.Seen, "limit");
        }
    }
}

