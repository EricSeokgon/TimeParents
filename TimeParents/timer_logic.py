import time
import threading

class GameTimer:
    def __init__(self, duration_seconds, on_tick=None, on_finish=None, on_warning=None):
        self.duration = duration_seconds
        self.remaining = self.duration
        self.running = False
        self.on_tick = on_tick
        self.on_finish = on_finish
        self.on_warning = on_warning
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if not self.running:
            self.running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_timer, daemon=True)
            self._thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()

    def _run_timer(self):
        while self.remaining > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self.remaining -= 1
            
            if self.on_tick:
                self.on_tick(self.format_time(self.remaining))
            
            # 경고 알림 (10분, 5분, 1분 전)
            if self.remaining in [600, 300, 60]:
                if self.on_warning:
                    self.on_warning(self.remaining)

        if self.remaining <= 0 and self.running:
            self.running = False
            if self.on_finish:
                self.on_finish()

    @staticmethod
    def format_time(seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

class ProcessTimer(GameTimer):
    def __init__(self, duration_seconds, process_name, on_tick=None, on_finish=None, on_warning=None):
        super().__init__(duration_seconds, on_tick, on_finish, on_warning)
        self.process_name = process_name

    def _run_timer(self):
        import subprocess
        
        while self.remaining > 0 and not self._stop_event.is_set():
            if self._check_process():
                self.remaining -= 1
                
                if self.on_tick:
                    self.on_tick(self.format_time(self.remaining))
                
                # 경고 알림 (10분, 5분, 1분 전)
                if self.remaining in [600, 300, 60]:
                    if self.on_warning:
                        self.on_warning(self.remaining)
            
            time.sleep(1)

        if self.remaining <= 0 and self.running:
            self.running = False
            if self.on_finish:
                self.on_finish()

    def _check_process(self):
        try:
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            output = subprocess.check_output(
                ["tasklist"], 
                startupinfo=startupinfo,
                encoding='cp949',
                errors='ignore'
            )
            return self.process_name.lower() in output.lower()
        except Exception:
            return False
