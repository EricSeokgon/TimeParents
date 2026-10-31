"""TimeParents가 한 번에 하나만 실행되도록 합니다.

두 개가 동시에 실행되면 둘 다 저장된 타이머 상태를 복원해 같은 타이머가 두 번 돌고,
만료 시 사용 기록이 두 번 남습니다. 두 번째로 실행된 쪽은 이미 실행 중인 창을
앞으로 꺼내 달라고 알리고 바로 종료합니다.
"""
import platform

MUTEX_NAME = "Local\\TimeParents_SingleInstance"
SHOW_EVENT_NAME = "Local\\TimeParents_ShowWindow"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0

if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.CreateEventW.restype = wintypes.HANDLE
    _kernel32.CreateEventW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
    _kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


class SingleInstance:
    def __init__(self, mutex_name=MUTEX_NAME, event_name=SHOW_EVENT_NAME):
        self.is_primary = True
        self._mutex = None
        self._event = None
        if platform.system() != "Windows":
            return
        # 뮤텍스는 프로세스가 종료(강제 종료 포함)되면 자동으로 해제됩니다.
        self._mutex = _kernel32.CreateMutexW(None, False, mutex_name)
        self.is_primary = ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        # 자동 리셋 이벤트: 두 번째 실행이 신호를 보내면 첫 번째가 한 번 받아 창을 띄웁니다.
        self._event = _kernel32.CreateEventW(None, False, False, event_name)

    def notify_primary(self):
        """이미 실행 중인 TimeParents에 창을 앞으로 꺼내 달라고 알립니다."""
        if self._event:
            _kernel32.SetEvent(self._event)

    def show_requested(self):
        """다른 실행에서 창 표시 요청이 왔는지 확인합니다 (기다리지 않음)."""
        return bool(self._event) and _kernel32.WaitForSingleObject(self._event, 0) == WAIT_OBJECT_0

    def close(self):
        for handle in (self._event, self._mutex):
            if handle:
                _kernel32.CloseHandle(handle)
        self._event = self._mutex = None
