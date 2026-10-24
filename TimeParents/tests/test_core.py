"""핵심 로직 테스트. 실행: python -m unittest discover -s tests

실제 사용자 데이터와 레지스트리를 건드리지 않도록 임시 폴더와 가짜 레지스트리를 사용합니다.
"""
import hashlib
import json
import os
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
    def _close(app):
        if app.timer:
            app.timer.stop()
        app._stop_enforcement()
        app.destroy()

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


if __name__ == "__main__":
    unittest.main()
