using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Security.Principal;
using System.Threading;
using System.Windows.Forms;

namespace TimeParents.Family
{
    internal class Status
    {
        internal string Name, QuietStart;
        internal int Budget, Available, Left, Unfinished;

        internal static Status Request(char op, int seconds = 0)
        {
            var rights = PipeAccessRights.ReadData | PipeAccessRights.WriteData | PipeAccessRights.Synchronize;
            using (var pipe = new NamedPipeClientStream(".", Store.Pipe, rights, PipeOptions.None,
                TokenImpersonationLevel.Identification, HandleInheritability.None))
            {
                pipe.Connect(1000);
                if (!Native.IsBroker(pipe.SafePipeHandle)) throw new IOException("TimeParents service identity could not be verified.");
                var writer = new BinaryWriter(pipe);
                writer.Write((byte)op); writer.Write(seconds); writer.Flush();
                var reader = new BinaryReader(pipe);
                if (!reader.ReadBoolean()) return null;
                var status = new Status { Name = reader.ReadString(), Budget = reader.ReadInt32(),
                    Available = reader.ReadInt32(), Left = reader.ReadInt32(), QuietStart = reader.ReadString() };
                // Older services end the response after QuietStart.
                try { status.Unfinished = reader.ReadInt32(); } catch (EndOfStreamException) { }
                return status;
            }
        }

        internal static string Duration(int seconds)
        {
            return String.Format("{0}분 {1:00}초", seconds / 60, seconds % 60);
        }
    }

    internal sealed class ChildSession : Form
    {
        private readonly Label clock = new Label { AutoSize = true };
        private readonly IntPtr normal = Native.GetThreadDesktop(Native.GetCurrentThreadId());
        private bool warned, startedExplorer;

        internal ChildSession()
        {
            Text = "TimeParents v" + Application.ProductVersion + " · 사용 시간";
            Font = new Font("Malgun Gothic", 11);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            Size = new Size(320, 145); MaximizeBox = false;
            var box = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(12), FlowDirection = FlowDirection.TopDown };
            box.Controls.Add(clock);
            var end = new Button { Text = "사용 끝내기", AutoSize = true };
            end.Click += delegate { try { Status.Request('E'); } catch (IOException) { } catch (TimeoutException) { } };
            box.Controls.Add(end); Controls.Add(box);
            FormClosing += delegate(object sender, FormClosingEventArgs e) {
                if (e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; WindowState = FormWindowState.Minimized; }
            };
            Shown += delegate {
                Hide();
                var thread = new Thread(ShowPicker) { IsBackground = true };
                thread.SetApartmentState(ApartmentState.STA); thread.Start();
            };
        }

        private void ShowPicker()
        {
            // Create Windows controls only after attaching this new thread to the picker desktop.
            IntPtr desk = Native.CreateDesktop("TimeParents-" + Guid.NewGuid().ToString("N"),
                IntPtr.Zero, IntPtr.Zero, 0, 0x01ff, IntPtr.Zero);
            if (desk == IntPtr.Zero || !Native.SetThreadDesktop(desk))
            {
                Native.ExitWindowsEx(0, 0);
                return;
            }
            using (var picker = new Picker(desk, normal, this)) Application.Run(picker);
        }

        internal void Display(int left)
        {
            BeginInvoke((Action)delegate {
                if (left <= 0) { Hide(); warned = false; return; }
                if (!startedExplorer) { Native.StartExplorer(); startedExplorer = true; }
                if (!Visible) { Show(); WindowState = FormWindowState.Normal; }
                clock.Text = "남은 시간  " + Status.Duration(left);
                if (left <= 60 && !warned)
                {
                    warned = true; WindowState = FormWindowState.Normal;
                    clock.Text += "  ·  작업을 저장하세요"; Activate();
                    System.Media.SystemSounds.Exclamation.Play();
                }
            });
        }

        internal void RestoreShell()
        {
            BeginInvoke((Action)delegate { Native.StartExplorer(); Application.ExitThread(); });
        }
    }

    internal sealed class Picker : Form
    {
        private readonly IntPtr gate, normal;
        private readonly ChildSession session;
        private readonly Label title, detail;
        private readonly NumericUpDown minutes;
        private readonly Button begin, resume;
        private readonly FlowLayoutPanel choices, edit;
        private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 750 };
        private bool playing;
        private Status current;

        internal Picker(IntPtr gate, IntPtr normal, ChildSession session)
        {
            this.gate = gate; this.normal = normal; this.session = session;
            Text = "TimeParents v" + Application.ProductVersion + " · 오늘의 사용 시간";
            Font = new Font("Malgun Gothic", 12);
            FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen; ClientSize = new Size(490, 300);
            var column = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(22),
                FlowDirection = FlowDirection.TopDown, WrapContents = false };
            title = new Label { AutoSize = true, Text = "사용 시간 확인 중…", Font = new Font(Font, FontStyle.Bold) };
            detail = new Label { AutoSize = true, Margin = new Padding(3, 10, 3, 12) };
            column.Controls.Add(title); column.Controls.Add(detail);
            choices = new FlowLayoutPanel { AutoSize = true };
            foreach (int n in new[] { 30, 60, 65, 90 })
            {
                string caption = n < 60 ? n + "분" : "1시간" + (n == 60 ? "" : " " + (n - 60) + "분");
                var button = new Button { Text = caption, AutoSize = true };
                button.Click += delegate { Begin(n * 60); }; choices.Controls.Add(button);
            }
            column.Controls.Add(choices);
            edit = new FlowLayoutPanel { AutoSize = true };
            edit.Controls.Add(new Label { Text = "직접 입력", AutoSize = true });
            minutes = new NumericUpDown { Minimum = 1, Maximum = 1440, Value = 30, Width = 75 };
            begin = new Button { Text = "분 사용하기", AutoSize = true, Enabled = false };
            begin.Click += delegate { Begin((int)minutes.Value * 60); };
            edit.Controls.Add(minutes); edit.Controls.Add(begin); column.Controls.Add(edit);
            resume = new Button { Text = "남은 시간 이어쓰기", AutoSize = true, Visible = false };
            resume.Click += delegate { Begin(0); };
            column.Controls.Add(resume);
            var leave = new Button { Text = "로그아웃", AutoSize = true };
            leave.Click += delegate {
                try { Status.Request('X'); } catch (IOException) { } catch (TimeoutException) { }
                Native.ExitWindowsEx(0, 0);
            };
            column.Controls.Add(leave); Controls.Add(column);
            FormClosing += delegate(object sender, FormClosingEventArgs e) {
                if (e.CloseReason == CloseReason.UserClosing) e.Cancel = true;
            };
            timer.Tick += delegate { RefreshStatus(); };
            Shown += delegate { RefreshStatus(); timer.Start(); };
        }

        private void Begin(int seconds)
        {
            if (current == null || current.Available <= 0) return;
            try { Apply(seconds == 0 ? Status.Request('R') : Status.Request('B', Math.Min(seconds, current.Available))); }
            catch (Exception ex) { Unavailable(ex); }
        }

        private void RefreshStatus()
        {
            try
            {
                char op = !playing && Native.SelectDesktop(gate, normal) ? 'G' : 'P';
                Apply(Status.Request(op));
            }
            catch (Exception ex) { Unavailable(ex); }
        }

        private void Unavailable(Exception ex)
        {
            current = null; playing = false; Native.SelectDesktop(gate, normal); session.Display(0);
            title.Text = "부모 설정을 확인해 주세요";
            detail.Text = "시간 관리 서비스 연결을 기다리고 있어요.";
            choices.Enabled = begin.Enabled = resume.Enabled = false;
            Trace.TraceWarning(ex.Message);
        }

        private void Apply(Status s)
        {
            if (s == null)
            {
                if (!Program.ChildPolicyPresent() && Native.SelectDesktop(normal, gate))
                { timer.Stop(); session.RestoreShell(); Application.ExitThread(); return; }
                Unavailable(new InvalidOperationException("Account is not enrolled")); return;
            }
            current = s;
            if (s.Left > 0)
            {
                if (!playing && !Native.SelectDesktop(normal, gate)) return;
                playing = true; session.Display(s.Left); return;
            }
            if (playing) { Native.SelectDesktop(gate, normal); session.Display(0); }
            playing = false;
            title.Text = s.Name + " · 오늘 남은 시간 " + Status.Duration(s.Budget);
            detail.Text = s.Available > 0 ? "지금 사용 가능  " + Status.Duration(s.Available) : "지금은 사용할 수 없어요.";
            if (!String.IsNullOrEmpty(s.QuietStart)) detail.Text += "   금지 시간 시작 " + s.QuietStart;
            choices.Enabled = begin.Enabled = s.Available > 0;
            choices.Visible = edit.Visible = s.Unfinished == 0;
            resume.Visible = s.Unfinished > 0;
            resume.Enabled = s.Available > 0;
            resume.Text = "남은 " + Status.Duration(Math.Min(s.Unfinished, s.Available)) + " 이어쓰기";
            minutes.Maximum = Math.Max(1, (s.Available + 59) / 60);
            if (minutes.Value > minutes.Maximum) minutes.Value = minutes.Maximum;
            begin.Text = s.Available > 0 && s.Available < 60 ? "남은 " + s.Available + "초 사용" : "분 사용하기";
        }
    }
}

