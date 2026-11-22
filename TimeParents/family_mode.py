"""Open the separately installed family manager from the parent dashboard."""
import ctypes
import os
import sys
from pathlib import Path


def installed_exe():
    return Path(os.environ.get("ProgramW6432", os.environ.get("ProgramFiles", ""))) / "TimeParents Family" / "TimeParents.Family.exe"


def is_child_shell():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System") as key:
            value, _ = winreg.QueryValueEx(key, "Shell")
        return value.casefold() == f'"{installed_exe()}" --child'.casefold()
    except OSError:
        return False


def open_manager():
    if sys.platform != "win32":
        raise OSError("Windows Pro, Education or Enterprise is required.")
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent / "dist"
    exe = installed_exe()
    if not exe.is_file():
        exe = base / "family" / "TimeParents.Family.exe"
    if not exe.is_file():
        raise FileNotFoundError("TimeParents.Family.exe · family/ (python tools/build_family.py)")
    from ctypes import wintypes
    run = ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteW
    run.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    run.restype = wintypes.HINSTANCE
    result = run(None, "runas", str(exe), "--manage", str(exe.parent), 1)
    if not result or result <= 32:
        raise ctypes.WinError(ctypes.get_last_error() or 5)

