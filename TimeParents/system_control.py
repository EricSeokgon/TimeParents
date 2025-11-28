import os
import platform

def shutdown_system():
    """시스템을 종료합니다."""
    if platform.system() == "Windows":
        os.system("shutdown /s /t 0")
    else:
        print("이 기능은 Windows에서만 작동합니다. (종료 시뮬레이션)")

def logoff_system():
    """시스템을 로그오프합니다."""
    if platform.system() == "Windows":
        os.system("shutdown /l")
    else:
        print("이 기능은 Windows에서만 작동합니다. (로그오프 시뮬레이션)")

def cancel_shutdown():
    """예약된 종료를 취소합니다 (필요한 경우)."""
    if platform.system() == "Windows":
        os.system("shutdown /a")
