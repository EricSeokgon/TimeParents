"""Shared Windows login profiles. All data and startup registry writes are isolated."""
from contextlib import ExitStack, nullcontext
from datetime import datetime
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
# utils also supports migration from the current directory on first import.
with tempfile.TemporaryDirectory() as boot:
    cwd = os.getcwd()
    try:
        os.chdir(boot)
        with patch.dict(os.environ, LOCALAPPDATA=boot):
            import profiles
            import utils
            import shared_runtime
    finally:
        os.chdir(cwd)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "family.sqlite3"
        self.store = profiles.ProfileStore(self.path)
        self.addCleanup(self.store.db.close)
        self.t = int(datetime(2026, 11, 21, 16).timestamp())
        self.a = self.store.save_child("민지", "5239", 30, 60)
        self.b = self.store.save_child("민호", "4987", 20, 15)
        self.store.set_enabled(True)
        self.token = self.store.new_gate(self.t)

    def start(self, seconds, at=None):
        t = self.t if at is None else at
        self.assertTrue(self.store.login(self.token, self.a, "5239", t))
        self.assertEqual(self.store.begin(self.token, seconds, t), seconds)
        self.assertEqual(self.store.take_grant(self.token), "child")

    def test_accounts_pin_and_independent_daily_limits(self):
        self.assertNotEqual(self.store.child(self.a)["pin"], "5239")
        self.assertFalse(self.store.login(self.token, self.a, "4987", self.t))
        self.assertIsNone(self.store.active())
        self.start(60)
        self.store.tick(self.t + 5)
        self.store.finish("early", self.t + 9)
        self.assertEqual(self.store.budget(self.a, self.t), 3591)
        self.assertEqual(self.store.budget(self.b, self.t), 900)
        self.assertEqual(self.store.budget(self.a, self.t + 2*86400), 1800)
        with patch("profiles.time.time", return_value=self.t + 10):
            visit, = self.store.history(self.a)
        self.assertEqual((visit["chosen"], visit["used"], visit["reason"]), (60, 9, "early"))

    def test_pending_login_and_one_time_grant(self):
        self.assertTrue(self.store.login(self.token, self.a, "5239", self.t))
        self.store.cancel_login(self.token, self.t + 10)
        self.assertIsNone(self.store.active())
        self.assertTrue(self.store.login(self.token, self.b, "4987", self.t + 11))
        self.assertEqual(self.store.begin(self.token, 9999, self.t + 15), 900)
        with profiles.ProfileStore(self.path) as second:
            self.assertEqual(second.take_grant(self.token), "child")
            self.assertIsNone(self.store.take_grant(self.token))
            self.store.cancel_login(self.token, self.t + 16)
            self.assertEqual(second.active()["start"], self.t + 15)

    def test_end_then_resume_same_child_across_restarts(self):
        self.start(1800)
        for elapsed in range(10, 721, 10):
            self.store.tick(self.t + elapsed)
        self.store.finish("early", self.t + 720)
        with profiles.ProfileStore(self.path) as reopened:
            t = self.t + 3600
            gate = reopened.new_gate(t)
            self.assertEqual(reopened.unfinished_seconds(self.a, t), 1080)
            self.assertEqual(reopened.unfinished_seconds(self.b, t), 0)
            self.assertTrue(reopened.login(gate, self.a, "5239", t))
            reopened.cancel_login(gate, t)
            self.assertTrue(reopened.login(gate, self.a, "5239", t))
            self.assertEqual(reopened.begin(gate, 5400, t), 1080)
            reopened.finish("early", t + 5)
            gate = reopened.new_gate(t + 10)
            self.assertTrue(reopened.login(gate, self.a, "5239", t + 10))
            self.assertEqual(reopened.begin(gate, None, t + 10), 1075)
            for elapsed in range(5, 1076, 5):
                reopened.tick(t + 10 + elapsed)
            self.assertEqual(reopened.unfinished_seconds(self.a, t + 1085), 0)
            self.assertEqual(reopened.budget(self.a, t + 1085), 1800)

    def test_resume_respects_date_and_current_limits(self):
        self.start(1800)
        self.store.finish("early", self.t + 5)
        tomorrow = self.t + 86400
        self.assertEqual(self.store.unfinished_seconds(self.a, tomorrow), 0)
        gate = self.store.new_gate(self.t + 10)
        self.store.login(gate, self.a, "5239", self.t + 10)
        self.assertEqual(self.store.begin(gate, None, tomorrow), 0)
        self.store.set_quiet(16*60, 18*60)
        self.assertEqual(self.store.begin(gate, None, self.t + 10), 0)
        self.store.set_quiet(None, None)
        self.store.save_child("민지", "", 10, 10, self.a)
        self.assertEqual(self.store.begin(gate, None, self.t + 10), 595)

    def test_parent_checks_existing_password_and_invalidated_gate(self):
        with patch.object(utils, "check_password", side_effect=lambda p: p == "test parent"):
            self.assertFalse(self.store.parent(self.token, "5239", self.t))
            new = self.store.new_gate(self.t)
            self.assertFalse(self.store.parent(self.token, "test parent", self.t))
            self.assertTrue(self.store.parent(new, "test parent", self.t))
            self.assertEqual(self.store.take_grant(new), "parent")
            self.assertIsNone(self.store.active())

    def test_boundary_quiet_midnight_and_bonus(self):
        self.store.bonus(self.a, self.t)
        self.assertEqual(self.store.budget(self.a, self.t), 4200)
        self.assertEqual(self.store.budget(self.a, self.t + 86400), 3600)
        self.store.set_quiet(21*60, 7*60)
        before = int(datetime(2026, 11, 21, 20, 59, 57).timestamp())
        self.assertTrue(self.store.login(self.token, self.a, "5239", before))
        self.assertEqual(self.store.begin(self.token, 60, before), 3)
        self.assertEqual(self.store.tick(before+4), 0)
        self.assertEqual(self.store.usage(self.a, before), 3)
        self.assertEqual(self.store.available(self.b, before+4), 0)
        self.assertEqual(self.store.available(self.b, before+10*3600+3), 900)
        self.store.set_quiet(None, None)
        midnight = int(datetime(2026, 11, 22).timestamp())
        self.assertEqual(self.store.available(self.a, midnight-5), 5)
        self.assertEqual(self.store.usage(self.a, midnight), 0)

    def test_interrupt_recovery_and_early_lock(self):
        self.start(120)
        self.store.tick(self.t + 4)
        with profiles.ProfileStore(self.path) as second:
            second.new_gate(self.t + 300)
            visit = second.db.execute("SELECT * FROM visits").fetchone()
            self.assertEqual((visit["reason"], visit["ended"], visit["used"]), ("interrupted", self.t+4, 4))
        self.token = self.store.new_gate(self.t+301)
        self.start(116, self.t+301)
        self.assertEqual(self.store.tick(self.t+350), 0)
        self.assertEqual(self.store.usage(self.a, self.t), 4)
        self.token = self.store.new_gate(self.t+351)
        self.start(116, self.t+351)
        self.store.finish("locked", self.t+355)
        self.assertEqual(self.store.usage(self.a, self.t), 8)

    def test_edit_archive_pin_and_reenable(self):
        for name, pin in [("민지","1234"), ("부모","3847"), ("A","12")]:
            with self.assertRaises(ValueError):
                self.store.save_child(name, pin, 30, 30)
        self.store.save_child("민지2", "", 10, 10, self.a)
        self.assertTrue(self.store.login(self.token, self.a, "5239", self.t))
        self.store.cancel_login(self.token, self.t)
        self.store.save_child("민지2", "6249", 10, 10, self.a)
        self.assertFalse(self.store.login(self.token, self.a, "5239", self.t))
        self.store.set_archived(self.a, True)
        self.assertFalse(self.store.login(self.token, self.a, "6249", self.t))
        self.store.set_archived(self.a, False)
        self.assertTrue(self.store.login(self.token, self.a, "6249", self.t))
        self.store.set_enabled(False)
        self.assertFalse(self.store.gate_ok(self.token))


@unittest.skipUnless(os.name == "nt", "Windows startup")
class StartupTests(unittest.TestCase):
    def test_current_exe_registration_is_verified_and_idempotent(self):
        import winreg
        data = {}
        def query(key, name):
            if name not in data:
                raise FileNotFoundError()
            return data[name], winreg.REG_SZ
        setter = Mock(side_effect=lambda key,name,zero,kind,value: data.update({name:value}))
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(winreg, "CreateKeyEx", side_effect=lambda *a: nullcontext(object())) as create, \
             patch.object(winreg, "QueryValueEx", side_effect=query), patch.object(winreg, "SetValueEx", setter):
            self.assertTrue(utils.ensure_autostart(required=True))
            self.assertTrue(utils.ensure_autostart(required=True))
            self.assertEqual(data["TimeParents"], '"' + sys.executable + '"')
            self.assertEqual(setter.call_count, 1)
            self.assertEqual(create.call_args.args[1], utils.RUN_KEY)
        with patch.object(winreg, "CreateKeyEx", side_effect=PermissionError()):
            with self.assertRaises(OSError):
                utils.ensure_autostart(required=True)


class ScreenTests(unittest.TestCase):
    def test_completed_login_is_accepted_after_waiting_at_picker(self):
        app = shared_runtime.SharedApp.__new__(shared_runtime.SharedApp)
        app.last_poll = shared_runtime.time.monotonic()
        app.was_locked = False
        app.role, app.token, app.instance = "waiting", "test-session", None
        app.events, app.store, app.worker = Mock(), Mock(), Mock()
        app.events.take.return_value = None
        app.store.settings.return_value = {"nonce": app.token, "grant_role": "child", "ready": 1}
        app.deadline = app.last_poll - 100
        app.worker.poll.return_value = None
        app.granted = Mock()
        with patch.object(shared_runtime.desks, "session_locked", return_value=False):
            app._poll()
        app.granted.assert_called_once()
        app.store.new_gate.assert_not_called()

    def test_setup_from_timer_requires_password_and_registers_before_enabling(self):
        from main import GameTimerApp
        import profile_ui
        legacy = Mock()
        legacy.switch_to_shared = False
        legacy._verify_password.return_value = False
        legacy._is_enforcing.return_value = False
        with tempfile.TemporaryDirectory() as folder, patch.object(utils, "DATA_DIR", folder), \
             patch.object(profile_ui, "ParentPanel") as panel, patch.object(utils, "ensure_autostart") as startup:
            GameTimerApp._open_profile_manager(legacy)
            panel.assert_not_called()
            self.assertFalse(profiles.configured())
            legacy._verify_password.return_value = True
            def configure(_panel):
                parent, store, activate = panel.call_args.args
                with self.assertRaises(ValueError):
                    activate(True)
                startup.assert_not_called()
                store.save_child("하나", "7125", 40, 50)
                startup.side_effect = OSError("denied")
                with self.assertRaises(OSError):
                    activate(True)
                self.assertFalse(store.settings()["enabled"])
                startup.side_effect = None
                activate(True)
            legacy.wait_window.side_effect = configure
            GameTimerApp._open_profile_manager(legacy)
            startup.assert_called_with(required=True)
            self.assertTrue(profiles.configured())
            self.assertTrue(legacy.switch_to_shared)
            legacy.quit.assert_called_once()

    def test_controller_and_panels_on_one_shared_login(self):
        from app_version import VERSION
        import tkinter as tk
        from tkinter import ttk
        from profile_ui import ParentPanel
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            moment = stack.enter_context(patch("time.time", return_value=datetime(2026, 11, 21, 12).timestamp()))
            store = stack.enter_context(profiles.ProfileStore(Path(folder)/"family.sqlite3"))
            root = tk.Tk()
            stack.callback(root.destroy)
            root.withdraw()
            stack.enter_context(patch.object(root, "deiconify"))
            stack.enter_context(patch.object(root, "focus_force"))
            made = []
            p = ParentPanel(root, store, made.append)
            self.assertIn(f"v{VERSION}", p.title())
            p.name.set("하나")
            p.pin.set("7259")
            p.weekend.set("120")
            p.save()
            p.mode(True)
            self.assertEqual(made, [True])
            self.assertEqual(len(p.rows), 1)
            p.destroy()
            store.set_enabled(True)
            desk = stack.enter_context(patch.object(shared_runtime.desks, "PickerDesktop"))
            desk.return_value.handle = None
            events = stack.enter_context(patch.object(shared_runtime.desks, "SessionEvents")).return_value
            events.take.return_value = None
            stack.enter_context(patch.object(shared_runtime.desks, "session_locked", return_value=False))
            stack.enter_context(patch.object(utils, "check_password", side_effect=lambda x:x=="test parent"))
            app = shared_runtime.SharedApp(root, store, None)
            stack.callback(app.cleanup)
            def press(widget, label):
                for w in widget.winfo_children():
                    if isinstance(w, ttk.Button) and w.cget("text") == label:
                        w.invoke()
                        return True
                    if press(w, label):
                        return True
                return False
            login = app.login
            def shows_version():
                return any(isinstance(w, ttk.Label) and w.cget("text") == f"TimeParents v{VERSION}"
                           for w in login.body.winfo_children())
            self.assertTrue(shows_version())
            login.pin.insert(0, "0000")
            login.sign_child()
            self.assertIsNone(store.active())
            login.pin.insert(0, "7259")
            login.sign_child()
            self.assertTrue(shows_version())
            self.assertTrue(press(login.body, "1시간 5분"))
            self.assertEqual(store.active()["chosen"], 3900)
            self.assertEqual(app.role, "child")
            self.assertIn(f"v{VERSION}", root.title())
            app.manage()
            self.assertIsNone(app.panel)
            moment.return_value += 7
            self.assertTrue(press(app.body, "사용 끝내기"))
            app.login.pin.insert(0, "7259")
            app.login.sign_child()
            self.assertTrue(press(app.login.body, "남은 64분 53초 이어쓰기"))
            self.assertEqual(store.active()["chosen"], 3893)
            events.take.return_value = ("locked", int(profiles.time.time()))
            app._poll()
            events.take.return_value = None
            self.assertEqual(app.role, "inline")
            self.assertIsNone(store.active())
            self.assertEqual(store.history(1)[0]["reason"], "locked")
            app.login.parent_page()
            field, = [w for w in app.login.body.winfo_children() if isinstance(w, ttk.Entry)]
            field.insert(0, "test parent")
            self.assertTrue(press(app.login.body, "부모로 사용"))
            self.assertEqual(app.role, "parent")
            self.assertIn(f"v{VERSION}", root.title())
            app.manage()
            self.assertEqual(len(app.panel.logs.get_children()), 2)

