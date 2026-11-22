"""Isolate the family picker from ordinary apps without changing the Windows shell."""
import ctypes
from ctypes import wintypes as wt
import os
import time


if os.name == "nt":
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)

    def bind(dll, name, result, *args):
        fn = getattr(dll, name)
        fn.restype, fn.argtypes = result, args
        return fn

    create = bind(user, "CreateDesktopW", wt.HANDLE, wt.LPCWSTR, wt.LPCWSTR, wt.LPVOID, wt.DWORD, wt.DWORD, wt.LPVOID)
    open_desk = bind(user, "OpenDesktopW", wt.HANDLE, wt.LPCWSTR, wt.DWORD, wt.BOOL, wt.DWORD)
    input_desk = bind(user, "OpenInputDesktop", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
    thread_desk = bind(user, "GetThreadDesktop", wt.HANDLE, wt.DWORD)
    thread_id = bind(kernel, "GetCurrentThreadId", wt.DWORD)
    attach = bind(user, "SetThreadDesktop", wt.BOOL, wt.HANDLE)
    switch = bind(user, "SwitchDesktop", wt.BOOL, wt.HANDLE)
    close = bind(user, "CloseDesktop", wt.BOOL, wt.HANDLE)
    get_name = bind(user, "GetUserObjectInformationW", wt.BOOL, wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD, ctypes.POINTER(wt.DWORD))
    process_open = bind(kernel, "OpenProcess", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
    wait = bind(kernel, "WaitForSingleObject", wt.DWORD, wt.HANDLE, wt.DWORD)
    close_handle = bind(kernel, "CloseHandle", wt.BOOL, wt.HANDLE)
    query = bind(wts, "WTSQuerySessionInformationW", wt.BOOL, wt.HANDLE, wt.DWORD, ctypes.c_int,
                 ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD))
    free = bind(wts, "WTSFreeMemory", None, wt.LPVOID)
    com = ctypes.WinDLL("comctl32", use_last_error=True)
    ptr = ctypes.c_size_t
    result_ptr = ctypes.c_ssize_t
    subclass_proc = ctypes.WINFUNCTYPE(result_ptr, wt.HWND, wt.UINT, ptr, result_ptr, ptr, ptr)
    install_proc = bind(com, "SetWindowSubclass", wt.BOOL, wt.HWND, subclass_proc, ptr, ptr)
    remove_proc = bind(com, "RemoveWindowSubclass", wt.BOOL, wt.HWND, subclass_proc, ptr)
    chain_proc = bind(com, "DefSubclassProc", result_ptr, wt.HWND, wt.UINT, ptr, result_ptr)
    ancestor = bind(user, "GetAncestor", wt.HWND, wt.HWND, wt.UINT)
    register_session = bind(wts, "WTSRegisterSessionNotification", wt.BOOL, wt.HWND, wt.DWORD)
    unregister_session = bind(wts, "WTSUnRegisterSessionNotification", wt.BOOL, wt.HWND)


class SessionEvents:
    """Remember the first lock/disconnect/suspend even if it ends between UI ticks."""
    def __init__(self, root):
        self.event = self.hwnd = self.callback = None
        if os.name != "nt":
            return
        root.update_idletasks()
        hwnd = ancestor(root.winfo_id(), 2)

        def receive(window, msg, wp, lp, ident, data):
            reason = None
            if msg == 0x02B1 and wp in (2, 4, 6, 7):  # disconnect, logoff, lock
                reason = "locked"
            elif msg == 0x0218 and wp == 4:  # PBT_APMSUSPEND
                reason = "sleep"
            if reason and self.event is None:
                self.event = (reason, int(time.time()))
            return chain_proc(window, msg, wp, lp)

        self.callback = subclass_proc(receive)
        if hwnd and install_proc(hwnd, self.callback, 1, 0):
            self.hwnd = hwnd
            register_session(hwnd, 0)

    def take(self):
        event, self.event = self.event, None
        return event

    def close(self):
        if self.hwnd:
            unregister_session(self.hwnd)
            remove_proc(self.hwnd, self.callback, 1)
            self.hwnd = None


def desktop_name(handle):
    buffer = ctypes.create_unicode_buffer(256)
    length = wt.DWORD()
    return buffer.value if handle and get_name(handle, 2, buffer, ctypes.sizeof(buffer), ctypes.byref(length)) else None


class PickerDesktop:
    def __init__(self, name):
        self.name = name
        self.normal = thread_desk(thread_id()) if os.name == "nt" else None
        self.handle = create(name, None, None, 0, 0x01FF, None) if self.normal else None

    def select(self, picker):
        if not self.handle:
            return False
        active = input_desk(0, False, 1)
        if not active:
            return False
        try:
            current = desktop_name(active)
            target, other = (self.handle, self.normal) if picker else (self.normal, self.handle)
            # Leave Windows sign-in, UAC and unrelated input desktops to Windows.
            return bool(current and (current == desktop_name(target) or
                        (current == desktop_name(other) and switch(target))))
        finally:
            close(active)

    def release(self):
        if self.handle:
            self.select(False)
            close(self.handle)
            self.handle = None


def attach_picker(name):
    if os.name != "nt" or not name:
        return None
    handle = open_desk(name, 0, False, 0x01FF)
    if handle and not attach(handle):
        close(handle)
        return None
    return handle


def session_locked():
    if os.name != "nt":
        return False
    data, length = ctypes.c_void_p(), wt.DWORD()
    # WTSSessionInfoEx level 1, x64. Union starts after the aligned DWORD Level.
    if not query(None, 0xFFFFFFFF, 25, ctypes.byref(data), ctypes.byref(length)):
        return False
    try:
        if length.value < 20 or ctypes.c_uint32.from_address(data.value).value != 1:
            return False
        state = ctypes.c_int32.from_address(data.value + 12).value
        flags = ctypes.c_int32.from_address(data.value + 16).value
        return state == 4 or flags == 0
    finally:
        free(data)

