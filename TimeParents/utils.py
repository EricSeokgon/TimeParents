import hashlib
import hmac
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

def get_data_dir():
    """앱의 데이터 저장 디렉토리 경로를 반환하고 생성합니다."""
    local_appdata = os.environ.get('LOCALAPPDATA')
    if local_appdata:
        data_dir = os.path.join(local_appdata, "TimeParents")
    else:
        data_dir = os.path.join(os.path.expanduser("~"), ".timeparents")

    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DATA_DIR = get_data_dir()

def migrate_file(old_name, new_path):
    """기존 로컬에 있던 파일을 보안 폴더로 마이그레이션하고 기존 파일을 삭제합니다."""
    if os.path.exists(old_name) and not os.path.exists(new_path):
        try:
            shutil.copy2(old_name, new_path)
            os.remove(old_name)
        except Exception:
            pass
    elif os.path.exists(old_name):
        try:
            os.remove(old_name)
        except Exception:
            pass

PASSWORD_FILE = os.path.join(DATA_DIR, "password.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")

# 마이그레이션 실행
migrate_file("password.json", PASSWORD_FILE)
migrate_file("settings.json", SETTINGS_FILE)
migrate_file("stats.json", STATS_FILE)

def write_json_atomic(path, data, **kwargs):
    """임시 파일에 먼저 쓴 뒤 교체하여, 쓰는 도중 강제 종료되어도 파일이 깨지지 않게 합니다."""
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        raise

# --- Password (PBKDF2 + 레지스트리 백업) ---
PBKDF2_ITERATIONS = 200_000
REG_PATH = r"Software\TimeParents"
REG_VALUE = "PasswordHash"

def hash_password(password, salt=None, iterations=PBKDF2_ITERATIONS):
    """비밀번호를 솔트가 포함된 PBKDF2-SHA256으로 해시화합니다."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${digest.hex()}"

def _verify_hash(password, stored):
    if not stored:
        return False
    if stored.startswith("pbkdf2$"):
        try:
            _, iterations, salt_hex, _ = stored.split("$")
            candidate = hash_password(password, bytes.fromhex(salt_hex), int(iterations))
        except Exception:
            return False
        return hmac.compare_digest(candidate, stored)
    # 구버전(솔트 없는 SHA-256) 호환
    legacy = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(legacy, stored)

def _read_registry_hash():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            value, _ = winreg.QueryValueEx(key, REG_VALUE)
            return value
    except Exception:
        return None

def _write_registry_hash(stored):
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, stored)
    except Exception:
        pass

def _read_file_hash():
    try:
        with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("password")
    except Exception:
        return None

def _write_file_hash(stored):
    try:
        write_json_atomic(PASSWORD_FILE, {"password": stored})
    except Exception:
        pass

def _load_stored_hash():
    """파일 또는 레지스트리에서 해시를 읽고, 한쪽이 지워졌거나 바뀌었으면 복구합니다."""
    file_hash = _read_file_hash()
    reg_hash = _read_registry_hash()
    if file_hash and not reg_hash:
        _write_registry_hash(file_hash)
    elif reg_hash and file_hash != reg_hash:
        # password.json이 삭제/변조됨 → 레지스트리 값으로 복구하고 기록을 남깁니다.
        _write_file_hash(reg_hash)
        save_log(0, "tamper", "password.json")
        file_hash = reg_hash
    return file_hash

def save_password(password):
    """비밀번호를 파일과 레지스트리에 저장합니다."""
    stored = hash_password(password)
    _write_file_hash(stored)
    _write_registry_hash(stored)

def check_password(password):
    """입력된 비밀번호가 저장된 비밀번호와 일치하는지 확인합니다."""
    stored = _load_stored_hash()
    if not _verify_hash(password, stored):
        return False
    if not stored.startswith("pbkdf2$"):
        save_password(password)  # 구버전 해시를 새 형식으로 업그레이드
    return True

def is_password_set():
    """비밀번호가 설정되어 있는지 확인합니다."""
    return bool(_load_stored_hash())

def detect_tampering():
    """비밀번호는 없는데 사용 기록이 남아 있으면 비밀번호가 삭제된 것으로 판단합니다."""
    return not is_password_set() and os.path.exists(STATS_FILE)

def save_settings(settings):
    """설정을 파일에 저장합니다."""
    try:
        write_json_atomic(SETTINGS_FILE, settings)
    except Exception:
        pass

def load_settings():
    """설정을 파일에서 불러옵니다."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


# 건수 대신 기간 기준으로 보관 (통계 검색이 전년도까지 조회하므로 2년)
LOG_RETENTION_DAYS = 730
# 일일 사용량에 포함하지 않는 기록 유형 ("특정 시간"은 종료 예약이지 사용 시간이 아님)
NON_USAGE_TYPES = ("schedule", "tamper")

def save_log(duration_seconds, type_str, target=None, timestamp=None):
    log_entry = {
        "timestamp": (timestamp or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration_seconds,
        "type": type_str,
        "target": target
    }

    logs = load_logs()
    logs.append(log_entry)

    cutoff = (datetime.now() - timedelta(days=LOG_RETENTION_DAYS)).strftime("%Y-%m-%d")
    logs = [log for log in logs if log.get("timestamp", "") >= cutoff]

    try:
        write_json_atomic(STATS_FILE, logs, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving log: {e}")

def load_logs():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def get_today_total(usage_only=False):
    logs = load_logs()
    today_str = datetime.now().strftime("%Y-%m-%d")
    total_seconds = 0

    for log in logs:
        if usage_only and log.get("type") in NON_USAGE_TYPES:
            continue
        if log["timestamp"].startswith(today_str):
            total_seconds += log.get("duration", 0)

    return total_seconds

def get_weekly_stats():
    """Returns a list of 7 tuples: (day_name, total_seconds) for Mon-Sun of current week"""
    logs = load_logs()
    now = datetime.now()

    # Get Monday of current week (weekday 0 = Monday)
    days_since_monday = now.weekday()
    monday = now - timedelta(days=days_since_monday)

    weekly_data = []
    day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

    for i in range(7):
        day = monday + timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        total_seconds = 0

        for log in logs:
            if log["timestamp"].startswith(day_str):
                total_seconds += log.get("duration", 0)

        weekly_data.append((day_names[i], total_seconds))

    return weekly_data

def save_language(lang_code):
    """Save language preference"""
    settings = load_settings()
    settings["language"] = lang_code
    save_settings(settings)

def load_language():
    """Load language preference, default to Korean"""
    settings = load_settings()
    return settings.get("language", "ko")

def save_theme(theme_mode):
    """Save theme preference"""
    settings = load_settings()
    settings["theme"] = theme_mode
    save_settings(settings)

def load_theme():
    """Load theme preference, default to Dark"""
    settings = load_settings()
    return settings.get("theme", "Dark")

# --- Timer State Persistence (작업 관리자 강제 종료 대응) ---
TIMER_STATE_FILE = os.path.join(DATA_DIR, "timer_state.json")

def save_timer_state(remaining, timer_type, target, action, initial_duration, end_at=None, exact=True):
    """실행 중인 타이머 상태를 파일에 저장합니다. 프로세스 강제 종료/재부팅 시 복원용."""
    state = {
        "remaining": remaining,
        "timer_type": timer_type,
        "target": target,
        "action": action,
        "initial_duration": initial_duration,
        "end_at": end_at,
        "exact": exact,
        "saved_at": datetime.now().isoformat()
    }
    try:
        write_json_atomic(TIMER_STATE_FILE, state)
    except Exception:
        pass

def load_timer_state():
    """저장된 타이머 상태를 불러옵니다."""
    if os.path.exists(TIMER_STATE_FILE):
        try:
            with open(TIMER_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def clear_timer_state():
    """저장된 타이머 상태를 삭제합니다 (정상 종료 시)."""
    try:
        if os.path.exists(TIMER_STATE_FILE):
            os.remove(TIMER_STATE_FILE)
    except Exception:
        pass

# --- Daily Limit (일일 사용 제한) ---

def save_daily_limit(seconds):
    """일일 사용 제한 시간을 저장합니다 (초 단위). 0이면 제한 없음."""
    settings = load_settings()
    settings["daily_limit"] = seconds
    save_settings(settings)

def load_daily_limit():
    """일일 사용 제한 시간을 불러옵니다 (초 단위). 0이면 제한 없음."""
    settings = load_settings()
    return settings.get("daily_limit", 0)

def get_daily_remaining():
    """오늘 남은 허용 시간을 초 단위로 반환합니다. 제한 없으면 -1."""
    limit = load_daily_limit()
    if limit <= 0:
        return -1
    used = get_today_total(usage_only=True)
    return max(0, limit - used)

# --- Game Block (게임 시간 만료 후 그날은 게임을 다시 실행해도 자동 종료) ---

def save_game_block(target, exact):
    settings = load_settings()
    settings["game_block"] = {"target": target, "exact": exact, "date": datetime.now().strftime("%Y-%m-%d")}
    save_settings(settings)

def load_game_block():
    """오늘 날짜의 게임 차단 정보를 반환합니다. 날짜가 지났으면 지우고 None."""
    block = load_settings().get("game_block")
    if not block:
        return None
    if block.get("date") != datetime.now().strftime("%Y-%m-%d"):
        clear_game_block()
        return None
    return block

def clear_game_block():
    settings = load_settings()
    if settings.pop("game_block", None) is not None:
        save_settings(settings)

# --- Autostart (강제 종료 후 재로그인 시 자동 실행 → 저장된 타이머 복원) ---
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def ensure_autostart():
    """빌드된 exe로 실행 중이면 현재 사용자 시작 프로그램에 등록합니다."""
    if not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, "TimeParents", 0, winreg.REG_SZ, f'"{sys.executable}"')
    except Exception:
        pass
