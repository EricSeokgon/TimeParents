import math
import platform
import time
import threading

WARNING_THRESHOLDS = (600, 300, 60)  # 경고 알림 (10분, 5분, 1분 전)
SUSPEND_GAP = 5  # 한 루프가 이보다 오래 걸리면 PC 절전/최대절전으로 간주 (초)

class GameTimer:
    """경과 시간을 실제 시계로 측정하는 카운트다운 타이머.

    end_at(epoch 초)이 주어지면 그 시각에 끝나는 '특정 시간' 모드로 동작하고,
    없으면 실제로 흐른 시간만큼 줄어듭니다 (PC 절전 중의 시간은 제외).
    """

    def __init__(self, duration_seconds, on_tick=None, on_finish=None, on_warning=None, end_at=None):
        self.duration = duration_seconds
        self.remaining = self.duration
        self.end_at = end_at
        self.running = False
        self.on_tick = on_tick
        self.on_finish = on_finish
        self.on_warning = on_warning
        self._stop_event = threading.Event()
        self._thread = None
        self._elapsed = 0.0
        # 시작 시점에 이미 지난 경고는 다시 띄우지 않습니다.
        self._warned = {t for t in WARNING_THRESHOLDS if t >= duration_seconds}

    def start(self):
        if not self.running:
            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_timer, daemon=True)
            self._thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()

    def _should_count(self):
        """이번 구간의 경과 시간을 차감할지 여부. ProcessTimer에서 재정의합니다."""
        return True

    def _update_remaining(self, delta):
        if self.end_at is not None:
            self.remaining = max(0, math.ceil(self.end_at - time.time()))
            return
        if delta > SUSPEND_GAP:
            delta = 0  # 절전 중이었던 시간은 사용 시간이 아님
        if self._should_count():
            self._elapsed += delta
        self.remaining = max(0, math.ceil(self.duration - self._elapsed))

    def _check_warnings(self):
        if not self.on_warning:
            return
        for threshold in WARNING_THRESHOLDS:
            if threshold not in self._warned and self.remaining <= threshold:
                self._warned.add(threshold)
                if self.remaining > 0:
                    self.on_warning(threshold)

    def _run_timer(self):
        last = time.monotonic()
        last_reported = None
        while self.remaining > 0 and not self._stop_event.wait(0.5):
            now = time.monotonic()
            self._update_remaining(now - last)
            last = now

            if self.remaining != last_reported:
                last_reported = self.remaining
                if self.on_tick:
                    self.on_tick(self.format_time(self.remaining))
                self._check_warnings()

        if self.remaining <= 0 and self.running:
            self.running = False
            if self.on_finish:
                self.on_finish()

    @staticmethod
    def format_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


def _normalize_exe(name):
    name = name.strip().lower()
    return name[:-4] if name.endswith(".exe") else name

if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260)
        ]

    _kernel32 = ctypes.windll.kernel32
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _INVALID_HANDLE = wintypes.HANDLE(-1).value

def list_process_names():
    """실행 중인 프로세스의 실행 파일 이름 집합을 반환합니다 (소문자, .exe 제외)."""
    names = set()
    if platform.system() == "Windows":
        try:
            snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if snap and snap != _INVALID_HANDLE:
                try:
                    pe32 = PROCESSENTRY32W()
                    pe32.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                    ok = _kernel32.Process32FirstW(snap, ctypes.byref(pe32))
                    while ok:
                        names.add(_normalize_exe(pe32.szExeFile))
                        ok = _kernel32.Process32NextW(snap, ctypes.byref(pe32))
                finally:
                    _kernel32.CloseHandle(snap)
                return names
        except Exception:
            pass

    # Windows가 아니거나 ctypes 실패 시 tasklist/ps 사용
    try:
        import subprocess
        if platform.system() == "Windows":
            output = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="cp949",
                errors="ignore"
            )
            for line in output.splitlines():
                if line.startswith('"'):
                    names.add(_normalize_exe(line.split('","')[0].strip('"')))
        else:
            output = subprocess.check_output(["ps", "-axco", "comm="]).decode("utf-8", errors="ignore")
            names.update(_normalize_exe(line) for line in output.splitlines() if line.strip())
    except Exception:
        pass
    return names


class ProcessTimer(GameTimer):
    """지정한 게임 프로세스가 실행 중일 때만 시간이 줄어드는 타이머."""

    CHECK_INTERVAL = 2  # 프로세스 상태 체크 주기 (초)

    def __init__(self, duration_seconds, process_name, on_tick=None, on_finish=None, on_warning=None, exact=True):
        super().__init__(duration_seconds, on_tick, on_finish, on_warning)
        self.process_name = process_name
        self.exact = exact
        self._last_check = 0.0
        self._is_running = False

    def _should_count(self):
        now = time.monotonic()
        if now - self._last_check >= self.CHECK_INTERVAL:
            self._is_running = self._check_process()
            self._last_check = now
        return self._is_running

    def _check_process(self):
        return bool(find_processes(self.process_name, self.exact))


def find_processes(process_name, exact=True):
    """실행 중인 프로세스 중 process_name에 해당하는 실행 파일 이름 목록을 반환합니다."""
    target = _normalize_exe(process_name)
    names = list_process_names()
    if exact:
        # 프리셋은 실행 파일 이름 정확히 일치 ("steam"이 "steamwebhelper"에 걸리지 않도록)
        return [target] if target in names else []
    # 직접 입력한 이름은 일부만 입력해도 동작하도록 부분 일치 유지
    return [name for name in names if target in name]


def kill_process(process_name, exact=True):
    """해당 게임 프로세스를 강제 종료하고, 종료한 실행 파일 이름 목록을 반환합니다."""
    matched = find_processes(process_name, exact)
    if platform.system() != "Windows":
        return matched
    import subprocess
    for name in matched:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/IM", f"{name}.exe"],
                           creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, check=False)
        except Exception:
            pass
    return matched
