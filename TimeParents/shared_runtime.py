"""Interactive shared-account route. No service, Windows account or elevation is needed."""
import os
from pathlib import Path
import subprocess
import sys
import time

import profile_desktop as desks
from app_version import VERSION


def worker_args(name, token):
    prefix = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).with_name("main.py"))]
    return prefix + ["--profile-picker", name, token, str(os.getpid())]


def run_picker(name, token, controller_pid):
    # This entry point must run before Tk creates windows on the ordinary desktop.
    from profiles import ProfileStore
    with ProfileStore() as store:
        if not store.gate_ok(token):
            return 2
        original = desks.thread_desk(desks.thread_id())
        original_name = desks.desktop_name(original)
        owner = desks.process_open(0x00100000, False, controller_pid)
        if not owner:
            return 2
        gate = desks.attach_picker(name)
        if not gate:
            desks.close_handle(owner)
            return 3
        try:
            import tkinter as tk
            from profile_ui import LoginView
            root = tk.Tk()
            root.attributes("-fullscreen", True)
            root.attributes("-topmost", True)
            LoginView(root, store, token, root.quit)
            root.update_idletasks()
            store.db.execute("UPDATE config SET ready=1 WHERE nonce=?", (token,))
            def check_controller():
                if desks.wait(owner, 0) == 0 or store.settings()["nonce"] != token:
                    root.quit()
                else:
                    root.after(500, check_controller)
            root.after(500, check_controller)
            root.mainloop()
            root.destroy()
        finally:
            # The controller may have exited while the family's selection screen was visible.
            active = desks.input_desk(0, False, 1)
            if active:
                try:
                    if desks.desktop_name(active) == name and original_name:
                        desks.switch(original)
                finally:
                    desks.close(active)
            desks.close_handle(owner)
        return 0


class SharedApp:
    def __init__(self, root, store, instance):
        import tkinter as tk
        from tkinter import ttk
        from profile_ui import center

        self.root, self.store, self.instance = root, store, instance
        self.role = "starting"
        self.panel = self.worker = self.desktop = self.token = None
        self.warned = self.was_locked = self.legacy = False
        self.last_poll = time.monotonic()
        self.deadline = 0
        self.body = ttk.Frame(root, padding=20)
        self.body.pack(fill="both", expand=True)
        self.info = tk.StringVar(root)
        root.title(f"TimeParents v{VERSION} · 가족 사용")
        center(root, 440, 235)
        self.events = desks.SessionEvents(root)
        root.protocol("WM_DELETE_WINDOW", self.close_window)
        self.request_gate("interrupted")
        self.job = root.after(300, self.poll)

    def clear(self):
        self.root.unbind("<Return>")
        for widget in self.root.winfo_children():
            if widget != self.body:
                widget.destroy()
        self.panel = None
        for widget in self.body.winfo_children():
            widget.destroy()

    def stop_worker(self):
        if self.desktop:
            self.desktop.release()
            self.desktop = None
        if self.worker is not None:
            if self.worker.poll() is None:
                try:
                    self.worker.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.worker.terminate()
                    self.worker.wait(timeout=2)
            self.worker = None

    def request_gate(self, reason, at=None):
        from tkinter import ttk
        t = int(time.time())
        if self.role in ("child", "inline", "waiting"):
            self.store.finish(reason, at if at is not None else t)
        self.role = "waiting"
        self.warned = False
        self.token = self.store.new_gate(t)
        self.stop_worker()
        self.clear()
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self.root.deiconify()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        ttk.Label(self.body, text="가족 로그인 화면을 여는 중…", font=("맑은 고딕", 16)).pack(expand=True)
        self.root.update_idletasks()
        self.desktop = desks.PickerDesktop("TimeParents-" + self.token)
        self.presented = False
        if self.desktop.handle:
            try:
                self.worker = subprocess.Popen(worker_args(self.desktop.name, self.token),
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.deadline = time.monotonic() + 20
                return
            except OSError:
                pass
        self.fallback()

    def fallback(self):
        from profile_ui import LoginView
        self.stop_worker()
        self.clear()
        self.role = "inline"
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.login = LoginView(self.root, self.store, self.token, self.granted)

    def granted(self):
        import tkinter as tk
        from tkinter import ttk
        from profile_ui import center

        role = self.store.take_grant(self.token)
        if role not in ("parent", "child") or (role == "child" and not self.store.active()):
            self.request_gate("interrupted")
            return
        self.stop_worker()
        self.token = None
        self.role = role
        self.clear()
        self.root.title(f"TimeParents v{VERSION} · 가족 사용")
        self.root.attributes("-fullscreen", False)
        self.root.attributes("-topmost", False)
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        center(self.root, 440, 235)
        self.root.deiconify()
        title = "부모로 사용 중" if role == "parent" else self.store.child(self.store.active()["child"])["name"] + " · 사용 중"
        ttk.Label(self.body, text=title, font=("맑은 고딕", 17, "bold")).pack(anchor="w", pady=(0,10))
        self.info.set("자리를 비울 때 사용자 전환을 누르거나 Windows를 잠그세요." if role == "parent" else "남은 시간 확인 중…")
        ttk.Label(self.body, textvariable=self.info, wraplength=400).pack(anchor="w", pady=(0,10))
        if role == "parent":
            ttk.Button(self.body, text="가족 프로필 및 사용 기록", command=self.manage).pack(fill="x", pady=3)
        ttk.Button(self.body, text="사용자 전환" if role == "parent" else "사용 끝내기",
                   command=lambda: self.request_gate("early")).pack(fill="x", pady=3)

    def manage(self):
        from profile_ui import ParentPanel
        if self.role != "parent":
            return
        if self.panel is not None and self.panel.winfo_exists():
            self.panel.lift()
            return
        def leave(enabled):
            if self.role == "parent" and not enabled:
                self.store.set_enabled(False)
                self.legacy = True
                self.root.quit()
        self.panel = ParentPanel(self.root, self.store, leave)

    def close_window(self):
        if self.role == "parent":
            self.request_gate("switch")
        elif self.role == "child":
            self.root.iconify()

    def poll(self):
        try:
            self._poll()
        finally:
            self.job = self.root.after(350, self.poll)

    def _poll(self):
        from profiles import clock_text
        locked = desks.session_locked()
        mono = time.monotonic()
        gap = mono - self.last_poll
        self.last_poll = mono
        boundary = self.events.take()
        if boundary:
            self.request_gate(*boundary)
        elif (locked and not self.was_locked) or gap > 12:
            self.request_gate("locked" if locked else "sleep")
        self.was_locked = locked
        if locked:
            return
        if self.instance and self.instance.show_requested():
            self.root.deiconify()
            self.root.lift()
        if self.role == "waiting":
            cfg = self.store.settings()
            if cfg["nonce"] == self.token and cfg["grant_role"]:
                self.granted()
            elif self.worker.poll() is not None:
                self.token = self.store.new_gate(int(time.time()))
                self.fallback()
            elif cfg["ready"]:
                if self.desktop.select(True):
                    self.presented = True
                elif not self.presented and mono > self.deadline:
                    self.token = self.store.new_gate(int(time.time()))
                    self.fallback()
            elif mono > self.deadline:
                self.token = self.store.new_gate(int(time.time()))
                self.fallback()
        elif self.role == "child":
            t = int(time.time())
            left = self.store.tick(t)
            if left <= 0:
                self.request_gate("limit")
            else:
                child = self.store.active()["child"]
                self.info.set("이번 사용 남은 시간  " + clock_text(left) +
                              "\n오늘 남은 시간  " + clock_text(self.store.budget(child, t)) +
                              ("   ·   작업을 저장하세요." if left <= 60 else ""))
                if left <= 60 and not self.warned:
                    self.warned = True
                    self.root.deiconify()
                    self.root.lift()
                    self.root.bell()

    def cleanup(self):
        self.events.close()
        self.stop_worker()
        self.store.finish("logoff", int(time.time()))
        self.root.after_cancel(self.job)


def run_shared(instance):
    import tkinter as tk
    from profiles import ProfileStore

    with ProfileStore() as store:
        root = tk.Tk()
        app = SharedApp(root, store, instance)
        try:
            root.mainloop()
            return app.legacy
        finally:
            app.cleanup()
            root.destroy()

