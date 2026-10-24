"""핵심 로직 테스트. 실행: python -m unittest discover -s tests

실제 사용자 데이터와 레지스트리를 건드리지 않도록 임시 폴더와 가짜 레지스트리를 사용합니다.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

_TMP = tempfile.mkdtemp()
os.environ["LOCALAPPDATA"] = _TMP
os.chdir(_TMP)  # utils의 구버전 파일 마이그레이션이 저장소 파일을 건드리지 않도록
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import languages  # noqa: E402
import system_control  # noqa: E402
import timer_logic  # noqa: E402
import utils  # noqa: E402

_fake_reg = {}
utils._read_registry_hash = lambda: _fake_reg.get("h")
utils._write_registry_hash = lambda v: _fake_reg.__setitem__("h", v)

_calls = []
system_control.shutdown_system = lambda *a: _calls.append("shutdown")
system_control.logoff_system = lambda: _calls.append("logoff")
system_control.lock_system = lambda: _calls.append("lock")
system_control.cancel_shutdown = lambda: _calls.append("cancel")


def _reset_data():
    _fake_reg.clear()
    for path in (utils.PASSWORD_FILE, utils.SETTINGS_FILE, utils.STATS_FILE, utils.TIMER_STATE_FILE):
        if os.path.exists(path):
            os.remove(path)


class PasswordTests(unittest.TestCase):
    def setUp(self):
        _reset_data()

    def test_pbkdf2_roundtrip(self):
        self.assertFalse(utils.is_password_set())
        utils.save_password("pw1")
        with open(utils.PASSWORD_FILE) as f:
            self.assertTrue(json.load(f)["password"].startswith("pbkdf2$"))
        self.assertTrue(utils.check_password("pw1"))
        self.assertFalse(utils.check_password("nope"))

    def test_deleted_file_restored_from_registry_and_logged(self):
        utils.save_password("pw1")
        os.remove(utils.PASSWORD_FILE)
        self.assertTrue(utils.check_password("pw1"))
        self.assertTrue(any(log["type"] == "tamper" for log in utils.load_logs()))

    def test_legacy_hash_upgraded(self):
        legacy = hashlib.sha256(b"old").hexdigest()
        with open(utils.PASSWORD_FILE, "w") as f:
            json.dump({"password": legacy}, f)
        _fake_reg["h"] = legacy
        self.assertTrue(utils.check_password("old"))
        with open(utils.PASSWORD_FILE) as f:
            self.assertTrue(json.load(f)["password"].startswith("pbkdf2$"))

    def test_tampering_detected_when_all_password_copies_deleted(self):
        utils.save_log(60, "countdown")
        self.assertTrue(utils.detect_tampering())


class LogTests(unittest.TestCase):
    def setUp(self):
        _reset_data()

    def test_daily_usage_excludes_schedule(self):
        utils.save_log(600, "countdown")
        utils.save_log(3600, "schedule")
        self.assertEqual(utils.get_today_total(usage_only=True), 600)
        self.assertEqual(utils.get_today_total(), 4200)

    def test_weekend_limit(self):
        saturday = datetime(2026, 10, 24)
        monday = datetime(2026, 10, 26)
        self.assertEqual(utils.get_limit_for_date(saturday), 0)  # 일일 제한 꺼짐
        utils.save_daily_limit(3600)
        self.assertEqual(utils.get_limit_for_date(saturday), 3600)  # 주말 별도 설정 없음 → 평일과 같음
        utils.save_weekend_limit(3 * 3600)
        self.assertEqual(utils.get_limit_for_date(saturday), 3 * 3600)
        self.assertEqual(utils.get_limit_for_date(monday), 3600)
        utils.save_daily_limit(0)
        self.assertEqual(utils.get_limit_for_date(saturday), 0)  # 일일 제한을 끄면 주말도 해제

    def test_daily_remaining_uses_todays_limit(self):
        utils.save_daily_limit(3600)
        utils.save_weekend_limit(7200)
        utils.save_log(600, "countdown")
        expected = (7200 if datetime.now().weekday() >= 5 else 3600) - 600
        self.assertEqual(utils.get_daily_remaining(), expected)

    def test_old_logs_pruned_by_age(self):
        utils.save_log(5, "countdown", timestamp=datetime.now() - timedelta(days=800))
        utils.save_log(1, "countdown")
        self.assertEqual(len(utils.load_logs()), 1)

    def test_format_hm(self):
        self.assertEqual(languages.format_hm(3900, "ko"), "1시간 5분")
        self.assertEqual(languages.format_hm(300, "en", compact=True), "5m")


class TimerTests(unittest.TestCase):
    def test_countdown_finishes_on_time(self):
        start = time.monotonic()
        done = []
        t = timer_logic.GameTimer(2, on_finish=lambda: done.append(time.monotonic() - start))
        t.start()
        t._thread.join(5)
        self.assertTrue(done and 1.8 < done[0] < 3.0)

    def test_stop_is_immediate(self):
        t = timer_logic.GameTimer(100)
        t.start()
        time.sleep(0.2)
        start = time.monotonic()
        t.stop()
        t._thread.join(2)
        self.assertLess(time.monotonic() - start, 0.2)

    def test_suspend_gap_not_counted(self):
        t = timer_logic.GameTimer(1000)
        t._update_remaining(1.0)
        t._update_remaining(3600)
        self.assertEqual(t.remaining, 999)

    def test_schedule_uses_wall_clock(self):
        t = timer_logic.GameTimer(10, end_at=time.time() + 3)
        t._update_remaining(0)
        self.assertEqual(t.remaining, 3)

    def test_warnings_fire_once_on_crossing(self):
        warned = []
        t = timer_logic.GameTimer(700, on_warning=warned.append)
        for remaining in (599, 250, 250):
            t.remaining = remaining
            t._check_warnings()
        self.assertEqual(warned, [600, 300])

    def test_process_match(self):
        original = timer_logic.list_process_names
        timer_logic.list_process_names = lambda: {"steamwebhelper", "robloxplayerbeta"}
        try:
            self.assertFalse(timer_logic.ProcessTimer(60, "steam", exact=True)._check_process())
            self.assertTrue(timer_logic.ProcessTimer(60, "RobloxPlayerBeta.exe", exact=True)._check_process())
            self.assertTrue(timer_logic.ProcessTimer(60, "Roblox", exact=False)._check_process())
        finally:
            timer_logic.list_process_names = original


class CurfewTests(unittest.TestCase):
    def setUp(self):
        _reset_data()

    def test_parse_hhmm(self):
        self.assertEqual(utils.parse_hhmm("21:00"), (21, 0))
        self.assertEqual(utils.parse_hhmm("7:5"), (7, 5))
        self.assertEqual(utils.parse_hhmm("2130"), (21, 30))
        self.assertEqual(utils.parse_hhmm("7"), (7, 0))
        for bad in ("24:00", "12:60", "abc", ""):
            with self.assertRaises(ValueError):
                utils.parse_hhmm(bad)

    def test_overnight_window(self):
        c = {"enabled": True, "start": "21:00", "end": "07:00"}
        day = datetime(2026, 10, 24)
        self.assertIsNone(utils.curfew_window(c, day.replace(hour=20, minute=59)))
        self.assertEqual(utils.curfew_window(c, day.replace(hour=21)),
                         (day.replace(hour=21), day.replace(hour=7) + timedelta(days=1)))
        self.assertEqual(utils.curfew_window(c, day.replace(hour=6, minute=59)),
                         (day.replace(hour=21) - timedelta(days=1), day.replace(hour=7)))
        self.assertIsNone(utils.curfew_window(c, day.replace(hour=7)))

    def test_same_day_window_and_disabled(self):
        c = {"enabled": True, "start": "13:00", "end": "15:00"}
        day = datetime(2026, 10, 24)
        self.assertIsNotNone(utils.curfew_window(c, day.replace(hour=14)))
        self.assertIsNone(utils.curfew_window(c, day.replace(hour=16)))
        self.assertIsNone(utils.curfew_window(dict(c, enabled=False), day.replace(hour=14)))

    def test_next_start(self):
        c = {"enabled": True, "start": "21:00", "end": "07:00"}
        day = datetime(2026, 10, 24)
        self.assertEqual(utils.next_curfew_start(c, day.replace(hour=20)), day.replace(hour=21))
        self.assertEqual(utils.next_curfew_start(c, day.replace(hour=22)), day.replace(hour=21) + timedelta(days=1))

    def test_saved_curfew_roundtrip(self):
        self.assertFalse(utils.load_curfew()["enabled"])
        utils.save_curfew(True, "22:30", "06:00")
        self.assertEqual(utils.load_curfew(), {"enabled": True, "start": "22:30", "end": "06:00"})


class GameBlockTests(unittest.TestCase):
    def setUp(self):
        _reset_data()

    def test_block_persists_today_and_expires_next_day(self):
        utils.save_game_block("RobloxPlayerBeta", True)
        self.assertEqual(utils.load_game_block()["target"], "RobloxPlayerBeta")
        settings = utils.load_settings()
        settings["game_block"]["date"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        utils.save_settings(settings)
        self.assertIsNone(utils.load_game_block())
        self.assertNotIn("game_block", utils.load_settings())

    def test_find_processes(self):
        original = timer_logic.list_process_names
        timer_logic.list_process_names = lambda: {"robloxplayerbeta", "robloxstudio", "steam"}
        try:
            self.assertEqual(timer_logic.find_processes("RobloxPlayerBeta"), ["robloxplayerbeta"])
            self.assertEqual(sorted(timer_logic.find_processes("roblox", exact=False)), ["robloxplayerbeta", "robloxstudio"])
            self.assertEqual(timer_logic.find_processes("minecraft"), [])
        finally:
            timer_logic.list_process_names = original

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_kill_process_really_terminates(self):
        import subprocess
        proc = subprocess.Popen(["ping", "-n", "60", "127.0.0.1"], stdout=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            time.sleep(0.5)
            self.assertIn("ping", timer_logic.kill_process("PING.EXE"))
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.returncode)
        finally:
            if proc.poll() is None:
                proc.kill()


class ResumeTests(unittest.TestCase):
    """저장된 타이머 상태로부터의 복원 (GUI 필요)."""

    @classmethod
    def setUpClass(cls):
        try:
            import main
        except Exception as e:  # 디스플레이가 없는 환경
            raise unittest.SkipTest(f"GUI unavailable: {e}")
        main.GameTimerApp.setup_tray_icon = lambda self: None
        cls.main = main

    def setUp(self):
        _reset_data()
        utils.save_password("pw1")
        _calls.clear()

    def _make_app(self, saved_at, boot_time, **kw):
        system_control.get_boot_time = lambda: boot_time
        state = dict(remaining=1800, timer_type="countdown", target=None, action="lock", initial_duration=3600)
        state.update(kw)
        utils.save_timer_state(**state)
        with open(utils.TIMER_STATE_FILE) as f:
            data = json.load(f)
        data["saved_at"] = saved_at.isoformat()
        with open(utils.TIMER_STATE_FILE, "w") as f:
            json.dump(data, f)
        app = self.main.GameTimerApp()
        app.withdraw()
        app.update()
        self.addCleanup(self._close, app)
        return app

    @staticmethod
    def _drain(app, seconds=0.7):
        """지연 파괴(close_window) 등 예약된 Tk 이벤트를 처리한 뒤 창을 닫도록 잠시 이벤트를 돌립니다."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                app.update()
            except Exception:
                return
            time.sleep(0.05)

    @classmethod
    def _close(cls, app):
        if app.timer:
            app.timer.stop()
        app._stop_enforcement()
        cls._drain(app)
        try:
            # 남은 after 작업이 다음 테스트의 이벤트 루프에서 파괴된 창을 호출하지 않도록 취소
            for job in app.tk.splitlist(app.tk.call("after", "info")):
                app.after_cancel(job)
            app.destroy()
        except Exception:
            pass  # 테스트에서 이미 닫은 창

    def test_new_day_resets_and_logs_on_saved_date(self):
        yesterday = datetime.now() - timedelta(days=1)
        app = self._make_app(yesterday, time.time() - 10)
        self.assertIsNone(app.timer)
        self.assertIsNone(utils.load_timer_state())
        last = utils.load_logs()[-1]
        self.assertTrue(last["timestamp"].startswith(yesterday.strftime("%Y-%m-%d")))
        self.assertEqual(last["duration"], 1800)

    def test_reboot_keeps_remaining(self):
        app = self._make_app(datetime.now() - timedelta(minutes=10), time.time() - 60)
        self.assertLessEqual(abs(app.timer.remaining - 1800), 2)

    def test_killed_app_subtracts_elapsed(self):
        app = self._make_app(datetime.now() - timedelta(minutes=10), time.time() - 43200)
        self.assertLessEqual(abs(app.timer.remaining - 1200), 2)

    def test_expired_resume_arms_action_and_relocks(self):
        app = self._make_app(datetime.now() - timedelta(minutes=40), time.time() - 43200)
        time.sleep(0.5)
        app.update()
        self.assertIsNotNone(app.grace_dialog)
        self.assertIsNotNone(app._fallback_timer)
        app.execute_expire_action("lock")
        self.assertIn("lock", _calls)
        self.assertTrue(app._is_enforcing())
        app._stop_timer()
        self.assertFalse(app._is_enforcing())

    def _plain_app(self):
        app = self.main.GameTimerApp()
        app.withdraw()
        self.addCleanup(self._close, app)
        return app

    def test_curfew_enforces_once_and_password_overrides_until_window_end(self):
        now = datetime.now()
        start, end = now - timedelta(minutes=1), now + timedelta(minutes=30)
        utils.save_curfew(True, start.strftime("%H:%M"), end.strftime("%H:%M"))
        utils.save_settings(dict(utils.load_settings(), action="lock"))
        errors = []
        self.main.messagebox.showerror = lambda *a, **k: errors.append(a)
        app = self.main.GameTimerApp()
        app.withdraw()
        app._verify_password = lambda: True
        results = {}

        # 화면 전환이 있는 흐름은 실제 앱처럼 mainloop 안에서 진행 (mainloop 없이 위젯을 만들고 지우면 Tk가 비정상 종료됨)
        def start_countdown():
            app.tab_view.set(languages.get_text("tab_countdown", app.current_lang))
            app.min_entry.delete(0, "end")
            app.min_entry.insert(0, "10")
            app.start_timer()

        def step1():
            start_countdown()  # 금지 시간대에는 타이머 시작 거부
            results["refused"] = app.timer is None and bool(errors)
            app._curfew_tick()
            results["enforced"] = app.grace_dialog is not None and app._timer_action == "lock" and app._fallback_timer is not None
            dialog = app.grace_dialog
            app._curfew_tick()
            results["once_per_window"] = app.grace_dialog is dialog
            # 유예 창이 뜬 직후 바로 중지해도 Tk가 비정상 종료되지 않아야 함 (close_window 회귀 테스트)
            app.prompt_stop_timer()  # 부모가 비밀번호로 중지 → 대시보드
            app.after(500, step2)

        def step2():
            results["stopped"] = not app._is_enforcing() and app._curfew_override_until is not None
            app._curfew_tick()
            results["not_reenforced"] = app.grace_dialog is None
            start_countdown()
            results["start_allowed_after_override"] = app.timer is not None
            app.timer.stop()
            app._stop_enforcement()
            app.after(200, app.quit)

        app.after(300, step1)
        app.after(15000, app.quit)  # 안전장치
        app.mainloop()
        self._close(app)
        self.assertEqual(results, dict.fromkeys(
            ["refused", "enforced", "once_per_window", "stopped", "not_reenforced", "start_allowed_after_override"], True))

    def test_curfew_stops_running_timer_and_logs_usage(self):
        app = self._plain_app()
        app.timer = timer_logic.GameTimer(1800)
        app.timer.remaining = 1200
        app.timer.running = True
        app.initial_duration, app.timer_type, app.timer_target = 1800, "countdown", None
        before = len(utils.load_logs())
        app._enforce_curfew({"enabled": True, "start": "21:00", "end": "07:00"})
        self.assertIsNone(app.timer)
        self.assertEqual(utils.load_logs()[before]["duration"], 600)

    def test_quit_needs_password_while_curfew_enabled(self):
        app = self._plain_app()
        quits = []
        app.quit_app = lambda: quits.append(True)
        utils.save_curfew(True, "21:00", "07:00")

        app.on_closing()  # X 버튼: 타이머가 없어도 트레이로 숨기기만 함
        self.assertEqual(quits, [])
        self.assertFalse(app.winfo_viewable())

        app._verify_password = lambda: False
        app._restore_and_quit_app()  # 트레이 "종료": 비밀번호가 틀리면 계속 실행
        self.assertEqual(quits, [])

        app._verify_password = lambda: True
        app._restore_and_quit_app()
        self.assertEqual(quits, [True])

    def test_quit_without_password_when_nothing_enforced(self):
        app = self._plain_app()
        quits = []
        app.quit_app = lambda: quits.append(True)
        app._verify_password = lambda: self.fail("password should not be asked")
        app.on_closing()
        app._restore_and_quit_app()
        self.assertEqual(quits, [True, True])

    def test_curfew_warning_shows_nearest_only_once(self):
        shown = []
        original = self.main.WarningDialog
        self.main.WarningDialog = lambda parent, text, **k: shown.append(text)
        self.addCleanup(setattr, self.main, "WarningDialog", original)
        app = self._plain_app()
        c = {"enabled": True, "start": "21:00", "end": "07:00"}
        day = datetime.now().replace(hour=20, minute=56, second=0, microsecond=0)
        app._warn_before_curfew(c, day)  # 4분 전: 5분 경고 하나만
        app._warn_before_curfew(c, day + timedelta(seconds=15))
        self.assertEqual(len(shown), 1)
        app._warn_before_curfew(c, day.replace(minute=59, second=30))  # 1분 경고
        self.assertEqual(len(shown), 2)

    def test_limit_change_needs_password_and_is_not_overwritten(self):
        self.main.messagebox.showinfo = lambda *a, **k: None
        utils.save_daily_limit(3600)
        utils.save_weekend_limit(3 * 3600)
        app = self.main.GameTimerApp()
        app.withdraw()
        self.addCleanup(self._close, app)
        app.tab_view.set(languages.get_text("tab_countdown", app.current_lang))
        app.min_entry.insert(0, "10")
        app.daily_h_entry.delete(0, "end")
        app.daily_h_entry.insert(0, "2")
        app.weekend_h_entry.delete(0, "end")
        app.weekend_h_entry.insert(0, "8")

        app._verify_password = lambda: False
        app.start_timer()
        self.assertIsNone(app.timer)
        self.assertEqual((utils.load_daily_limit(), utils.load_weekend_limit()), (3600, 3 * 3600))

        app._verify_password = lambda: True
        app.start_timer()
        self.assertIsNotNone(app.timer)
        self.assertEqual((utils.load_daily_limit(), utils.load_weekend_limit()), (2 * 3600, 8 * 3600))

    def test_kill_game_blocks_until_password_stop_and_survives_restart(self):
        killed = []
        original = timer_logic.kill_process
        timer_logic.kill_process = lambda name, exact=True: killed.append((name, exact)) or []
        self.addCleanup(setattr, timer_logic, "kill_process", original)

        app = self._make_app(datetime.now() - timedelta(minutes=40), time.time() - 43200,
                             timer_type="game", target="RobloxPlayerBeta", action="kill_game")
        time.sleep(0.5)
        app.update()
        app.execute_expire_action("kill_game")
        time.sleep(0.3)
        app.update()
        self.assertIn(("RobloxPlayerBeta", True), killed)
        self.assertTrue(app._is_enforcing())
        self.assertEqual(utils.load_game_block()["target"], "RobloxPlayerBeta")
        app.timer = None
        app._game_block_job.set()  # 이 앱 인스턴스 종료 (강제 종료 흉내)
        app._game_block_job = None
        app.destroy()

        # 재시작하면 차단이 이어짐
        killed.clear()
        restarted = self.main.GameTimerApp()
        restarted.withdraw()
        self.addCleanup(self._close, restarted)
        time.sleep(0.3)
        restarted.update()
        self.assertTrue(killed and restarted._game_block_job is not None)

        restarted._stop_timer()
        self.assertIsNone(utils.load_game_block())
        self.assertFalse(restarted._is_enforcing())


class VersionTests(unittest.TestCase):
    def test_readme_matches_version(self):
        # 기능 추가 시 main.VERSION을 올리면 README 제목과 버전 기록도 함께 갱신해야 합니다.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "main.py"), encoding="utf-8") as f:
            version = re.search(r'^VERSION = "([\d.]+)"', f.read(), re.M).group(1)
        with open(os.path.join(root, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn(f"# TimeParents (타임페어런츠) v{version}", readme.splitlines()[0])
        self.assertIn(f"- **v{version}**", readme)


if __name__ == "__main__":
    unittest.main()
