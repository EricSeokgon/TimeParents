import os
import platform
import subprocess

def _run(args):
    """콘솔 창이 깜빡이지 않도록 셸 없이 실행합니다."""
    try:
        result = subprocess.run(args, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        return result.returncode == 0
    except OSError:
        return False

def shutdown_system(message="TimeParents", delay_seconds=60):
    """Windows에 종료를 요청하고 명령이 접수되었는지 반환합니다."""
    if platform.system() == "Windows":
        shutdown = os.path.join(os.environ["SystemRoot"], "System32", "shutdown.exe")
        return _run([shutdown, "/s", "/t", str(delay_seconds), "/c", message])
    return False

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
