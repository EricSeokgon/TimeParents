import platform
import subprocess

def _run(args):
    """콘솔 창이 깜빡이지 않도록 셸 없이 실행합니다."""
    try:
        subprocess.run(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    except Exception:
        pass

def shutdown_system(message="TimeParents"):
    """시스템을 60초 후 종료합니다. (유예 시간 제공)"""
    if platform.system() == "Windows":
        _run(["shutdown", "/s", "/t", "60", "/c", message])
    else:
        print("이 기능은 Windows에서만 작동합니다. (종료 시뮬레이션)")

def logoff_system():
    """즉시 로그오프합니다. (유예 시간은 호출하는 쪽의 경고 창이 제공)"""
    if platform.system() == "Windows":
        _run(["shutdown", "/l"])
    else:
        print("이 기능은 Windows에서만 작동합니다. (로그오프 시뮬레이션)")

def cancel_shutdown():
    """예약된 종료를 취소합니다 (필요한 경우)."""
    if platform.system() == "Windows":
        _run(["shutdown", "/a"])

def lock_system():
    """시스템 화면을 잠급니다."""
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
        except Exception:
            _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    else:
        print("이 기능은 Windows에서만 작동합니다. (화면 잠금 시뮬레이션)")

def get_boot_time():
    """마지막 부팅 시각(epoch 초)을 반환합니다. 알 수 없으면 None."""
    try:
        import time
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            uptime = ctypes.windll.kernel32.GetTickCount64() / 1000.0
        else:
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
        return time.time() - uptime
    except Exception:
        return None
