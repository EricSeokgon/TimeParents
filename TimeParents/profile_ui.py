"""Family account selection and parent settings. Both run with ordinary user privileges."""
from datetime import datetime
import time
import tkinter as tk
from tkinter import messagebox, ttk

import utils
from app_version import VERSION
from profiles import clock_text


def now():
    return int(time.time())


def center(win, width, height):
    win.geometry(f"{width}x{height}+{max(0, (win.winfo_screenwidth()-width)//2)}+{max(0, (win.winfo_screenheight()-height)//2)}")


class LoginView:
    def __init__(self, root, store, token, done):
        self.root, self.store, self.token, self.done = root, store, token, done
        self.child = None
        root.title(f"TimeParents v{VERSION} · 가족 로그인")
        root.protocol("WM_DELETE_WINDOW", self.choose)
        self.body = ttk.Frame(root, padding=24)
        self.body.place(relx=.5, rely=.5, anchor="center")
        self.choose()

    def clear(self):
        self.root.unbind("<Return>")
        for widget in self.body.winfo_children():
            widget.destroy()

    def title(self, text):
        ttk.Label(self.body, text=f"TimeParents v{VERSION}").pack(anchor="w", pady=(0, 4))
        ttk.Label(self.body, text=text, font=("맑은 고딕", 18, "bold")).pack(anchor="w", pady=(0, 12))

    def choose(self):
        if self.child is not None:
            self.store.cancel_login(self.token, now())
        self.child = None
        self.clear()
        self.title("누가 사용하나요?")
        self.accounts = self.store.children()
        names = [p["name"] for p in self.accounts]
        self.combo = ttk.Combobox(self.body, values=names, state="readonly", width=28)
        self.combo.pack(fill="x")
        if names:
            self.combo.current(0)
        ttk.Label(self.body, text="자녀 PIN").pack(anchor="w", pady=(14, 3))
        self.pin = ttk.Entry(self.body, show="●")
        self.pin.pack(fill="x")
        self.feedback = ttk.Label(self.body, foreground="#a33329")
        self.feedback.pack(anchor="w")
        ttk.Button(self.body, text="자녀 로그인", command=self.sign_child,
                   state="normal" if names else "disabled").pack(fill="x", pady=4)
        ttk.Button(self.body, text="부모 로그인", command=self.parent_page).pack(fill="x", pady=4)
        self.root.bind("<Return>", lambda event: self.sign_child())
        self.pin.focus_set()

    def sign_child(self):
        index = self.combo.current()
        if index < 0:
            return
        child = self.accounts[index]["id"]
        if not self.store.login(self.token, child, self.pin.get(), now()):
            self.pin.delete(0, "end")
            self.feedback.configure(text="자녀 이름과 PIN을 확인하세요.")
            return
        self.child = child
        self.duration_page()

    def parent_page(self):
        self.clear()
        self.title("부모 로그인")
        ttk.Label(self.body, text="기존 TimeParents 부모 비밀번호").pack(anchor="w")
        pw = ttk.Entry(self.body, width=30, show="●")
        pw.pack(fill="x", pady=6)
        note = ttk.Label(self.body, foreground="#a33329")
        note.pack(anchor="w")

        def submit():
            if self.store.parent(self.token, pw.get(), now()):
                self.done()
            else:
                pw.delete(0, "end")
                note.configure(text="부모 비밀번호를 확인하세요.")

        ttk.Button(self.body, text="부모로 사용", command=submit).pack(fill="x", pady=4)
        ttk.Button(self.body, text="뒤로", command=self.choose).pack(fill="x", pady=4)
        self.root.bind("<Return>", lambda event: submit())
        pw.focus_set()

    def duration_page(self):
        self.clear()
        child = self.store.child(self.child)
        self.title(child["name"] + " · 사용 시간 선택")
        label = ttk.Label(self.body)
        label.pack(anchor="w")
        self.feedback = ttk.Label(self.body, foreground="#a33329")
        actions = ttk.Frame(self.body)
        actions.pack(fill="x", pady=4)
        fresh = ttk.Frame(actions)
        fresh.grid(row=0, column=0, sticky="w")
        choices = ttk.Frame(fresh)
        choices.pack(fill="x", pady=(12, 4))
        duration = tk.StringVar(self.root)

        def start(seconds):
            if self.store.begin(self.token, seconds, now()):
                self.done()
            else:
                self.feedback.configure(text="지금은 사용할 수 있는 시간이 없습니다.")

        def custom():
            try:
                minutes = int(duration.get())
                if not 1 <= minutes <= 1440:
                    raise ValueError
            except ValueError:
                self.feedback.configure(text="1~1440 사이의 분을 입력하세요.")
                return
            start(minutes * 60)

        for minutes, caption in ((30, "30분"), (60, "1시간"), (65, "1시간 5분"), (90, "1시간 30분")):
            ttk.Button(choices, text=caption, command=lambda m=minutes: start(m*60)).pack(side="left", padx=2)
        field = ttk.Frame(fresh)
        field.pack(fill="x", pady=6)
        ttk.Label(field, text="직접 입력").pack(side="left", padx=(0, 4))
        ttk.Entry(field, textvariable=duration, width=6).pack(side="left")
        ttk.Label(field, text="분").pack(side="left", padx=3)
        ttk.Button(field, text="시작", command=custom).pack(side="left", padx=4)
        resume = ttk.Button(actions, command=lambda: start(None))
        self.feedback.pack(anchor="w")
        ttk.Button(self.body, text="다른 가족 선택", command=self.choose).pack(fill="x", pady=(8, 0))

        def refresh():
            if label.winfo_exists():
                t = now()
                available = self.store.available(self.child, t)
                balance = self.store.unfinished_seconds(self.child, t)
                if balance:
                    fresh.grid_remove()
                    resume.configure(text=f"남은 {clock_text(min(balance, available))} 이어쓰기",
                                     state="normal" if available else "disabled")
                    resume.grid(row=0, column=0, sticky="w")
                else:
                    resume.grid_remove()
                    fresh.grid()
                label.configure(text=f"오늘 남은 시간  {clock_text(self.store.budget(self.child, t))}"
                                     f"\n지금 사용 가능  {clock_text(min(balance or available, available))}")
                self.root.after(1000, refresh)
        refresh()


class ParentPanel(tk.Toplevel):
    def __init__(self, parent, store, change_mode):
        super().__init__(parent)
        self.store, self.change_mode = store, change_mode
        self.title(f"TimeParents v{VERSION} · 가족 프로필 관리")
        center(self, 790, 550)
        self.minsize(660, 460)
        self.transient(parent)
        self.grab_set()
        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)
        self.pick = ttk.Combobox(frm, state="readonly", width=25)
        self.pick.grid(row=0, column=0, sticky="ew", columnspan=2)
        self.pick.bind("<<ComboboxSelected>>", lambda _e: self.select())
        ttk.Button(frm, text="새 자녀", command=self.new).grid(row=0, column=2, padx=5)
        self.archive_btn = ttk.Button(frm, text="등록 해제", command=self.archive)
        self.archive_btn.grid(row=0, column=3)
        self.name, self.pin, self.weekday, self.weekend = [tk.StringVar(self) for _ in range(4)]
        for col, (label, var) in enumerate(zip(("자녀 이름", "자녀 PIN", "평일 한도(분)", "주말 한도(분)"),
                                               (self.name, self.pin, self.weekday, self.weekend))):
            ttk.Label(frm, text=label).grid(row=1, column=col, sticky="w", pady=(12, 3))
            ttk.Entry(frm, width=14, textvariable=var, show="●" if col == 1 else "").grid(row=2, column=col, sticky="ew", padx=(0, 5))
            frm.columnconfigure(col, weight=1)
        ttk.Button(frm, text="프로필 저장", command=self.save).grid(row=3, column=0, sticky="w", pady=6)
        ttk.Button(frm, text="오늘만 10분 추가", command=self.extra).grid(row=3, column=1, sticky="w")
        self.info = ttk.Label(frm, wraplength=700)
        self.info.grid(row=4, column=0, columnspan=4, sticky="w")
        q = store.settings()
        self.quiet = tk.BooleanVar(self, q["quiet_start"] is not None)
        self.start = tk.StringVar(self, self.hm(q["quiet_start"] if self.quiet.get() else 21*60))
        self.end = tk.StringVar(self, self.hm(q["quiet_end"] if self.quiet.get() else 7*60))
        row = ttk.Frame(frm)
        row.grid(row=5, column=0, columnspan=4, sticky="w", pady=10)
        ttk.Checkbutton(row, text="공통 금지 시간", variable=self.quiet).pack(side="left")
        ttk.Entry(row, textvariable=self.start, width=7).pack(side="left", padx=3)
        ttk.Label(row, text="부터").pack(side="left")
        ttk.Entry(row, textvariable=self.end, width=7).pack(side="left", padx=3)
        ttk.Button(row, text="금지 시간 저장", command=self.save_quiet).pack(side="left", padx=5)
        columns = ("앱 로그인", "사용 시작", "종료", "선택", "사용", "종료 사유")
        table = ttk.Frame(frm)
        table.grid(row=6, column=0, columnspan=4, sticky="nsew")
        frm.rowconfigure(6, weight=1)
        self.logs = ttk.Treeview(table, columns=columns, show="headings", height=7)
        bar = ttk.Scrollbar(table, orient="vertical", command=self.logs.yview)
        self.logs.configure(yscrollcommand=bar.set)
        for i, col in enumerate(columns):
            self.logs.heading(col, text=col)
            self.logs.column(col, width=110 if i < 3 else 72, minwidth=52)
        bar.pack(side="right", fill="y")
        self.logs.pack(fill="both", expand=True)
        enabled = store.settings()["enabled"]
        button = "공유 로그인 끄기" if enabled else "공유 로그인 시작"
        ttk.Button(frm, text=button, command=lambda: self.mode(not enabled)).grid(row=7, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Button(frm, text="닫기", command=self.destroy).grid(row=7, column=3, sticky="e")
        self.reload()

    @staticmethod
    def hm(minutes):
        return f"{minutes//60:02d}:{minutes%60:02d}"

    def reload(self, selected=None):
        self.rows = self.store.children(True)
        self.pick.configure(values=[r["name"] + (" (해제)" if r["archived"] else "") for r in self.rows])
        if self.rows:
            self.pick.current(next((i for i, r in enumerate(self.rows) if r["id"] == selected), 0))
            self.select()
        else:
            self.new()

    def new(self):
        self.selected = None
        self.pick.set("")
        self.name.set("")
        self.pin.set("")
        self.weekday.set("60")
        self.weekend.set("60")
        self.info.configure(text="자녀 이름과 숫자 PIN 4~12자리를 입력하고 저장하세요.")
        self.archive_btn.configure(state="disabled")
        self.logs.delete(*self.logs.get_children())

    def select(self):
        self.selected = self.rows[self.pick.current()]["id"]
        p = self.store.child(self.selected)
        self.name.set(p["name"])
        self.pin.set("")
        self.weekday.set(p["weekday"])
        self.weekend.set(p["weekend"])
        self.archive_btn.configure(text="다시 등록" if p["archived"] else "등록 해제", state="normal")
        t = now()
        self.info.configure(text=f"오늘 사용 {clock_text(self.store.usage(self.selected,t))}   ·   "
                                 f"남은 시간 {clock_text(self.store.budget(self.selected,t))}   ·   PIN을 비워 두면 유지합니다.")
        self.logs.delete(*self.logs.get_children())
        def stamp(value):
            return datetime.fromtimestamp(value).strftime("%m-%d %H:%M:%S") if value is not None else "—"
        reasons = {"early":"직접 종료","switch":"사용자 전환","locked":"Windows 잠금","interrupted":"중단",
                   "limit":"시간 만료","logoff":"종료","sleep":"절전"}
        for v in self.store.history(self.selected):
            self.logs.insert("", "end", values=(stamp(v["login"]),stamp(v["start"]),stamp(v["ended"]),
                clock_text(v["chosen"]),clock_text(v["used"]),reasons.get(v["reason"],"사용 중" if v["start"] else "선택 대기")))

    def save(self):
        try:
            selected = self.store.save_child(self.name.get(), self.pin.get(), int(self.weekday.get()),
                                             int(self.weekend.get()), self.selected)
            self.reload(selected)
        except ValueError as exc:
            messagebox.showerror("프로필", str(exc) if "invalid literal" not in str(exc) else "한도는 분 단위 숫자로 입력하세요.", parent=self)

    def extra(self):
        if self.selected is not None:
            self.store.bonus(self.selected, now())
            self.select()

    def archive(self):
        if self.selected is None:
            return
        state = self.store.child(self.selected)["archived"]
        if messagebox.askyesno("프로필", "이 프로필을 다시 등록할까요?" if state else "이 프로필의 사용을 중지할까요? 기록은 보관합니다.", parent=self):
            self.store.set_archived(self.selected, not state)
            self.reload(self.selected)

    def save_quiet(self):
        try:
            start, end = None, None
            if self.quiet.get():
                h, m = utils.parse_hhmm(self.start.get())
                start = h*60 + m
                h, m = utils.parse_hhmm(self.end.get())
                end = h*60 + m
            self.store.set_quiet(start, end)
            messagebox.showinfo("금지 시간", "저장했습니다.", parent=self)
        except ValueError:
            messagebox.showerror("금지 시간", "시작과 종료를 서로 다른 시각으로 입력하세요. 예: 21:00, 07:00", parent=self)

    def mode(self, enable):
        if not enable and not messagebox.askyesno("공유 로그인", "공유 로그인을 끄고 기존 타이머로 돌아갈까요?", parent=self):
            return
        try:
            self.change_mode(enable)
        except (OSError, ValueError) as exc:
            messagebox.showerror("공유 로그인", str(exc), parent=self)

