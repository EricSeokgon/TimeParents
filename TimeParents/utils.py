import hashlib
import json
import os
from datetime import datetime

PASSWORD_FILE = "password.json"

def hash_password(password):
    """비밀번호를 해시화합니다."""
    return hashlib.sha256(password.encode()).hexdigest()

def save_password(password):
    """비밀번호를 파일에 저장합니다."""
    hashed = hash_password(password)
    with open(PASSWORD_FILE, "w") as f:
        json.dump({"password": hashed}, f)

def check_password(password):
    """입력된 비밀번호가 저장된 비밀번호와 일치하는지 확인합니다."""
    if not os.path.exists(PASSWORD_FILE):
        return False
    
    try:
        with open(PASSWORD_FILE, "r") as f:
            data = json.load(f)
            stored_hash = data.get("password")
            return stored_hash == hash_password(password)
    except Exception:
        return False

def is_password_set():
    """비밀번호가 설정되어 있는지 확인합니다."""
    return os.path.exists(PASSWORD_FILE)

SETTINGS_FILE = "settings.json"

def save_settings(settings):
    """설정을 파일에 저장합니다."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
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

STATS_FILE = "stats.json"

def save_log(duration_seconds, type_str, target=None):
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration_seconds,
        "type": type_str,
        "target": target
    }
    
    logs = load_logs()
    logs.append(log_entry)
    
    # Keep only last 1000 logs to prevent file from growing too large
    if len(logs) > 1000:
        logs = logs[-1000:]
        
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
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

def get_today_total():
    logs = load_logs()
    today_str = datetime.now().strftime("%Y-%m-%d")
    total_seconds = 0
    
    for log in logs:
        if log["timestamp"].startswith(today_str):
            total_seconds += log.get("duration", 0)
            
    return total_seconds
