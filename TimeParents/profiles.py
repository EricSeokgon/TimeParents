"""TimeParents identities and time accounting for one shared Windows login."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import secrets
import sqlite3
import time

import utils


def database_path():
    return Path(utils.DATA_DIR) / "profiles.sqlite3"


def configured():
    if not database_path().is_file():
        return False
    with ProfileStore() as store:
        return bool(store.settings()["enabled"])


def day_key(t):
    return datetime.fromtimestamp(t).date().isoformat()


def clock_text(seconds):
    return f"{seconds // 60}분 {seconds % 60:02d}초"


class ProfileStore:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or database_path(), timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS config (
              id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
              quiet_start INTEGER, quiet_end INTEGER, nonce TEXT, ready INTEGER DEFAULT 0, grant_role TEXT
            );
            INSERT OR IGNORE INTO config(id) VALUES(1);
            CREATE TABLE IF NOT EXISTS children (
              id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, pin TEXT NOT NULL,
              weekday INTEGER NOT NULL, weekend INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
              bonus_day TEXT, bonus INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS visits (
              id INTEGER PRIMARY KEY, child INTEGER NOT NULL REFERENCES children(id), login INTEGER NOT NULL,
              start INTEGER, day TEXT, chosen INTEGER NOT NULL DEFAULT 0, used INTEGER NOT NULL DEFAULT 0,
              seen INTEGER NOT NULL, ended INTEGER, reason TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_open_visit ON visits((1)) WHERE ended IS NULL;
            CREATE INDEX IF NOT EXISTS child_days ON visits(child,day);
        """)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def settings(self):
        return self.db.execute("SELECT * FROM config WHERE id=1").fetchone()

    def children(self, include_archived=False):
        return list(self.db.execute("SELECT id,name,archived FROM children WHERE archived=0 OR ? ORDER BY id",
                                    (include_archived,)))

    def child(self, child):
        return self.db.execute("SELECT * FROM children WHERE id=?", (child,)).fetchone()

    def save_child(self, name, pin, weekday, weekend, child=None):
        name = name.strip()
        if not name or len(name) > 40 or name.casefold() in ("부모", "parent"):
            raise ValueError("자녀 이름을 1~40자로 입력하세요.")
        if (child is None or pin) and not (4 <= len(pin) <= 12 and pin.isascii() and pin.isdigit()):
            raise ValueError("자녀 PIN은 숫자 4~12자리로 정하세요.")
        if not (0 <= weekday <= 1440 and 0 <= weekend <= 1440):
            raise ValueError("하루 한도는 0~1440분입니다.")
        encoded = utils.hash_password(pin) if pin else None
        try:
            with self.transaction():
                if child is None:
                    return self.db.execute("INSERT INTO children(name,pin,weekday,weekend) VALUES(?,?,?,?)",
                                           (name, encoded, weekday, weekend)).lastrowid
                self.db.execute("UPDATE children SET name=?,pin=COALESCE(?,pin),weekday=?,weekend=? WHERE id=?",
                                (name, encoded, weekday, weekend, child))
                return child
        except sqlite3.IntegrityError as exc:
            raise ValueError("이미 등록된 이름입니다. 다른 이름을 입력하세요.") from exc

    def set_enabled(self, enabled):
        if enabled and not self.children():
            raise ValueError("자녀 프로필을 하나 이상 만들어 주세요.")
        self.db.execute("UPDATE config SET enabled=?,nonce=NULL,ready=0,grant_role=NULL WHERE id=1", (int(enabled),))

    def set_quiet(self, start, end):
        if start is not None and (end is None or not 0 <= start < 1440 or not 0 <= end < 1440 or start == end):
            raise ValueError("서로 다른 시작·종료 시각을 입력하세요.")
        self.db.execute("UPDATE config SET quiet_start=?, quiet_end=? WHERE id=1", (start, end))

    def set_archived(self, child, archived):
        self.db.execute("UPDATE children SET archived=? WHERE id=?", (int(archived), child))

    def bonus(self, child, now):
        today = day_key(now)
        self.db.execute("""UPDATE children SET bonus=MIN(1440,(CASE WHEN bonus_day=? THEN bonus ELSE 0 END)+10),
                           bonus_day=? WHERE id=?""", (today, today, child))

    def active(self):
        return self.db.execute("SELECT * FROM visits WHERE ended IS NULL").fetchone()

    def usage(self, child, now):
        return self.db.execute("SELECT COALESCE(SUM(used),0) FROM visits WHERE child=? AND day=?",
                               (child, day_key(now))).fetchone()[0]

    def unfinished_seconds(self, child, now):
        # A PIN-only visit has no start/day and must not hide an earlier balance.
        visit = self.db.execute("""SELECT chosen, used, ended, reason FROM visits
                                   WHERE child=? AND day=? ORDER BY id DESC LIMIT 1""",
                                (child, day_key(now))).fetchone()
        if visit is None or visit["ended"] is None or visit["reason"] == "limit":
            return 0
        return max(0, visit["chosen"] - visit["used"])

    def budget(self, child, now):
        p = self.child(child)
        base = p["weekend"] if datetime.fromtimestamp(now).weekday() >= 5 else p["weekday"]
        bonus = p["bonus"] if p["bonus_day"] == day_key(now) else 0
        return max(0, (base + bonus) * 60 - self.usage(child, now))

    def available(self, child, now):
        local = datetime.fromtimestamp(now)
        midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time())
        cfg = self.settings()
        start, end = cfg["quiet_start"], cfg["quiet_end"]
        if start is not None:
            minute = local.hour * 60 + local.minute
            quiet = start <= minute < end if start < end else minute >= start or minute < end
            if quiet:
                return 0
            if minute < start:
                midnight = local.replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
        return min(self.budget(child, now), max(0, int(midnight.timestamp()) - now))

    def new_gate(self, now):
        token = secrets.token_urlsafe(24)
        with self.transaction():
            self._close("interrupted", now, checkpoint=True)
            self.db.execute("DELETE FROM visits WHERE ended IS NOT NULL AND ended < ?", (now - 90 * 86400,))
            self.db.execute("UPDATE config SET nonce=?,ready=0,grant_role=NULL WHERE id=1", (token,))
        return token

    def gate_ok(self, token):
        cfg = self.settings()
        return bool(token and cfg["enabled"] and cfg["nonce"] == token and cfg["grant_role"] is None)

    def login(self, token, child, pin, now):
        with self.transaction():
            p = self.child(child)
            if not self.gate_ok(token) or not p or p["archived"] or not utils._verify_hash(pin, p["pin"]):
                return False
            self._close("switch", now)
            self.db.execute("INSERT INTO visits(child,login,seen) VALUES(?,?,?)", (child, now, now))
            return True

    def parent(self, token, password, now):
        if not utils.check_password(password):
            return False
        with self.transaction():
            if not self.gate_ok(token):
                return False
            self._close("switch", now)
            self.db.execute("UPDATE config SET grant_role='parent' WHERE id=1")
        return True

    def cancel_login(self, token, now):
        with self.transaction():
            if self.gate_ok(token):
                self._close("switch", now)

    def begin(self, token, seconds, now):
        with self.transaction():
            visit = self.active()
            if not self.gate_ok(token) or not visit or visit["start"] is not None:
                return 0
            # None is an explicit resume. A stale resume after midnight cannot
            # create a fresh allocation. Recheck inside the write transaction.
            if seconds is not None and seconds <= 0:
                return 0
            requested = self.unfinished_seconds(visit["child"], now) or seconds or 0
            grant = min(requested, self.available(visit["child"], now))
            if grant <= 0:
                return 0
            self.db.execute("UPDATE visits SET start=?,day=?,seen=?,chosen=? WHERE id=?",
                            (now, day_key(now), now, grant, visit["id"]))
            self.db.execute("UPDATE config SET grant_role='child' WHERE id=1")
            return grant

    def take_grant(self, token):
        with self.transaction():
            cfg = self.settings()
            if not token or cfg["nonce"] != token:
                return None
            self.db.execute("UPDATE config SET nonce=NULL,ready=0,grant_role=NULL WHERE id=1")
            return cfg["grant_role"]

    def _close(self, reason, now, checkpoint=False):
        visit = self.active()
        if visit:
            end = visit["seen"] if checkpoint else max(now, visit["login"])
            self.db.execute("UPDATE visits SET ended=?,reason=? WHERE id=?", (end, reason, visit["id"]))

    def _tick(self, now):
        v = self.active()
        if not v or v["start"] is None:
            return 0
        gap = now - v["seen"]
        if gap < 0 or gap > 12:
            self._close("interrupted", now, checkpoint=True)
            return 0
        allowance = min(v["chosen"] - v["used"], self.available(v["child"], v["seen"]))
        used = min(allowance, gap)
        if used:
            self.db.execute("UPDATE visits SET used=used+?,seen=seen+? WHERE id=?", (used, used, v["id"]))
        if gap >= allowance or day_key(now) != v["day"] or self.available(v["child"], now) == 0:
            self._close("limit", v["seen"] + used)
            return 0
        return v["chosen"] - v["used"] - used

    def tick(self, now):
        with self.transaction():
            return self._tick(now)

    def finish(self, reason, now):
        with self.transaction():
            self._tick(now)
            self._close(reason, now)

    def history(self, child):
        return list(self.db.execute("SELECT * FROM visits WHERE child=? AND login>=? ORDER BY id DESC",
                                    (child, int(time.time()) - 90 * 86400)))

