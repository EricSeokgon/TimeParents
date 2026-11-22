using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace TimeParents.Family
{
    internal sealed class Manager : Form
    {
        private readonly ComboBox children = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 165 };
        private readonly NumericUpDown weekday = Minutes(), weekend = Minutes();
        private readonly CheckBox quiet = new CheckBox { Text = "공통 금지 시간", AutoSize = true };
        private readonly DateTimePicker from = Clock(), to = Clock();
        private readonly Label summary = new Label { AutoSize = true };
        private readonly DataGridView grid = new DataGridView { Dock = DockStyle.Fill, ReadOnly = true,
            AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false,
            AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill };
        private readonly List<string> sids = new List<string>();
        private string Sid { get { return children.SelectedIndex < 0 ? null : sids[children.SelectedIndex]; } }
        private static NumericUpDown Minutes() { return new NumericUpDown { Minimum = 0, Maximum = 1440, Width = 70 }; }
        private static DateTimePicker Clock() { return new DateTimePicker { Format = DateTimePickerFormat.Custom, CustomFormat = "HH:mm", ShowUpDown = true, Width = 76 }; }

        public Manager()
        {
            Text = "TimeParents v" + Application.ProductVersion + " · 자녀 계정과 사용 기록";
            Font = new Font("Malgun Gothic", 10); StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(900, 520); MinimumSize = new Size(760, 440);
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 5, ColumnCount = 1, Padding = new Padding(12) };
            for (int i = 0; i < 4; i++) layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            var accounts = Row(); accounts.Controls.Add(children);
            AddButton(accounts, "자녀 계정 등록", Enroll);
            AddButton(accounts, "등록 해제", Remove);
            AddButton(accounts, "기록 새로 고침", ShowHistory);
            var limits = Row(); AddText(limits, "평일(분)"); limits.Controls.Add(weekday);
            AddText(limits, "주말(분)"); limits.Controls.Add(weekend);
            AddButton(limits, "한도 저장", SaveLimit); AddButton(limits, "오늘 10분 추가", Extra);
            var hours = Row(); hours.Controls.Add(quiet); hours.Controls.Add(from); AddText(hours, "부터"); hours.Controls.Add(to);
            AddText(hours, "까지"); AddButton(hours, "금지 시간 저장", SaveQuiet);
            layout.Controls.Add(accounts, 0, 0); layout.Controls.Add(limits, 0, 1);
            layout.Controls.Add(hours, 0, 2); layout.Controls.Add(summary, 0, 3); layout.Controls.Add(grid, 0, 4);
            foreach (string col in new[] { "로그인", "이용 시작", "종료", "선택", "사용", "종료 사유" }) grid.Columns.Add(col, col);
            Controls.Add(layout);
            children.SelectedIndexChanged += delegate { LoadRule(); };
            Reload(null);
            var q = Store.Read<QuietHours>("", "Quiet") ?? new QuietHours { Start = 21 * 60, End = 7 * 60 };
            quiet.Checked = q.Enabled; from.Value = DateTime.Today.AddMinutes(q.Start); to.Value = DateTime.Today.AddMinutes(q.End);
        }

        private static FlowLayoutPanel Row()
        { return new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill, Margin = new Padding(0, 3, 0, 3) }; }
        private static void AddText(Control row, string text)
        { row.Controls.Add(new Label { Text = text, AutoSize = true, Margin = new Padding(4, 6, 4, 0) }); }
        private void AddButton(Control row, string text, Action action)
        {
            var b = new Button { Text = text, AutoSize = true };
            b.Click += delegate { try { action(); } catch (Exception ex) { MessageBox.Show(this, ex.Message, Text); } };
            row.Controls.Add(b);
        }

        private void Reload(string select)
        {
            children.Items.Clear(); sids.Clear();
            foreach (string sid in Store.Children())
            {
                Rule rule = Store.Read<Rule>(@"\Rules", sid);
                sids.Add(sid); children.Items.Add(rule.Name + (rule.Enabled ? "" : " (해제됨)"));
            }
            int i = sids.IndexOf(select);
            if (sids.Count > 0) children.SelectedIndex = i < 0 ? 0 : i;
            else ShowHistory();
        }
        private void LoadRule()
        {
            if (Sid == null) return;
            var r = Store.Read<Rule>(@"\Rules", Sid);
            weekday.Value = r.Weekday; weekend.Value = r.Weekend; ShowHistory();
        }
        private void SaveLimit()
        {
            if (Sid == null) return;
            var r = Store.Read<Rule>(@"\Rules", Sid);
            r.Weekday = (int)weekday.Value; r.Weekend = (int)weekend.Value;
            Store.Write(@"\Rules", Sid, r); ShowHistory();
        }
        private void Extra()
        {
            if (Sid == null) return;
            var r = Store.Read<Rule>(@"\Rules", Sid);
            string today = Ledger.Day(Ledger.Now());
            r.ExtraMinutes = Math.Min(1440, (r.ExtraDay == today ? r.ExtraMinutes : 0) + 10);
            r.ExtraDay = today; Store.Write(@"\Rules", Sid, r); ShowHistory();
        }
        private void SaveQuiet()
        {
            int start = from.Value.Hour * 60 + from.Value.Minute, end = to.Value.Hour * 60 + to.Value.Minute;
            if (quiet.Checked && start == end) throw new ArgumentException("시작과 끝 시각을 다르게 설정하세요.");
            Store.Write("", "Quiet", new QuietHours { Enabled = quiet.Checked, Start = start, End = end });
            MessageBox.Show(this, "가족 공통 금지 시간을 저장했습니다.", Text);
        }

        private static string When(long t) { return t > 0 ? Ledger.Local(t).ToString("MM-dd HH:mm:ss") : "—"; }
        private static string Reason(Visit v)
        {
            if (v.End == 0) return v.Start > 0 ? "사용 중" : "선택 대기";
            switch (v.Reason) {
                case "locked": return "잠금·전환";
                case "sleep": return "절전";
                case "early": return "직접 종료";
                case "logoff": return "로그아웃";
                case "limit": return "시간 만료";
                case "removed": return "등록 해제";
                case "switch": return "계정 전환";
                default: return "연결 종료";
            }
        }
        private void ShowHistory()
        {
            grid.Rows.Clear();
            if (Sid == null) { summary.Text = "자녀의 Windows 표준 계정을 먼저 등록하세요."; return; }
            var r = Store.Read<Rule>(@"\Rules", Sid);
            var book = Store.Read<Ledger>(@"\History", Sid) ?? new Ledger();
            long now = Ledger.Now();
            summary.Text = String.Format("{0}  ·  오늘 사용 {1}  ·  남은 시간 {2}", r.Name,
                Status.Duration(book.UsedToday(now)), Status.Duration(book.Budget(r, now)));
            foreach (var v in book.Visits.Where(v => v.End == 0 || v.End >= now - 90L * 86400).Reverse())
                grid.Rows.Add(When(v.Login), When(v.Start), When(v.End), Status.Duration(v.Selected), Status.Duration(v.Used), Reason(v));
        }
        private void Enroll()
        {
            using (var form = new Form { Text = "자녀 Windows 계정 등록", Font = Font, ClientSize = new Size(440, 165),
                FormBorderStyle = FormBorderStyle.FixedDialog, StartPosition = FormStartPosition.CenterParent, MinimizeBox = false, MaximizeBox = false })
            {
                var label = new Label { Left = 14, Top = 12, Width = 415, Height = 54,
                    Text = "한 번 로그인한 적이 있는 자녀 표준 계정의 Windows 사용자 이름을 입력하세요. 다음 로그인부터 적용됩니다." };
                var name = new TextBox { Left = 14, Top = 69, Width = 400 };
                var ok = new Button { Text = "등록", Left = 320, Top = 109, DialogResult = DialogResult.OK };
                form.Controls.AddRange(new Control[] { label, name, ok }); form.AcceptButton = ok;
                if (form.ShowDialog(this) != DialogResult.OK || String.IsNullOrWhiteSpace(name.Text)) return;
                Program.Setup("Enroll", name.Text.Trim());
                string selected = Store.Children().FirstOrDefault(s => String.Equals(Store.Read<Rule>(@"\Rules", s).Name, name.Text.Trim(), StringComparison.OrdinalIgnoreCase));
                Reload(selected);
            }
        }
        private void Remove()
        {
            if (Sid == null) return;
            var r = Store.Read<Rule>(@"\Rules", Sid);
            if (!r.Enabled || MessageBox.Show(this, r.Name + " 계정의 자녀 모드를 해제할까요?", Text,
                MessageBoxButtons.YesNo) != DialogResult.Yes) return;
            Program.Setup("Remove", Sid); Reload(Sid);
        }
    }
}

