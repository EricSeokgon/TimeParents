import hashlib
import json
import os

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
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}
