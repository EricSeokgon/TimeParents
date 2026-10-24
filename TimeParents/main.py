import customtkinter as ctk
from tkinter import messagebox
import utils
import system_control
from timer_logic import GameTimer, ProcessTimer
import sys
from datetime import datetime, timedelta
import webbrowser
import languages
import pystray
from PIL import Image, ImageDraw
import threading
import re
import time

VERSION = "1.5.0"

GRACE_SECONDS = 60
RELOCK_INTERVAL_MS = 60 * 1000  # 잠금 동작 후 비밀번호로 중지할 때까지 재잠금 주기
TAB_KEYS = ("tab_game", "tab_countdown", "tab_schedule")

# Load theme before creating app
current_theme = utils.load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")

def create_tray_icon_image():
    """시스템 트레이 아이콘으로 사용할 64x64 시계 모양 이미지를 생성합니다."""
    try:
        # Create a 64x64 icon resembling a blue clock for TimeParents
        image = Image.new('RGB', (64, 64), color='#3B8ED0')
        dc = ImageDraw.Draw(image)
        # Outer circle
        dc.ellipse((8, 8, 56, 56), fill='#1F538D', outline='white', width=2)
        # Clock hands
        dc.line((32, 32, 32, 18), fill='white', width=3)
        dc.line((32, 32, 44, 32), fill='white', width=3)
        return image
    except Exception:
        # Fallback to a blank image if PIL fails
        return Image.new('RGB', (64, 64), color='blue')

class WarningDialog(ctk.CTkToplevel):
    """메인 루프를 막지 않는 알림 창 (messagebox는 열어 둔 채 방치하면 타이머 동작이 멈춤)."""
    def __init__(self, parent, text, title_key="warning", color="#FF5555"):
        super().__init__(parent)

        self.title(languages.get_text(title_key, parent.current_lang))
        self.geometry("350x150")
        self.resizable(False, False)
        
        # 화면 최상단 플로팅 설정 (포커스는 뺏지 않음)
        self.attributes("-topmost", True)
        self.transient(parent)
        
        # 레이블
        label = ctk.CTkLabel(self, text=text, font=("Arial", 16, "bold"), text_color=color, wraplength=300)
        label.pack(pady=30, padx=20)
        
        # 확인 버튼
        btn = ctk.CTkButton(self, text=languages.get_text("confirm", parent.current_lang), command=self.destroy, width=100)
        btn.pack(pady=10)
        
        # 10초 후 자동 닫힘
        self.after(10000, self._auto_close)

    def _auto_close(self):
        if self.winfo_exists():
            self.destroy()


class GraceWarningDialog(ctk.CTkToplevel):
    def __init__(self, parent, action, seconds=60):
        super().__init__(parent)
        self.parent = parent
        self.action = action
        self.remaining = seconds
        self._timer_id = None
        
        self.title(languages.get_text("warning", parent.current_lang))
        self.geometry("380x180")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(parent)
        
        # Disable window close button to prevent bypassing/dismissing
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        
        self.label = ctk.CTkLabel(self, text="", font=("Arial", 16, "bold"), text_color="#FF5555", wraplength=340)
        self.label.pack(pady=40, padx=20)
        
        self.update_countdown()

    def update_countdown(self):
        if self.remaining <= 0:
            self.execute_action()
            return
            
        action_str = languages.get_text(self.action, self.parent.current_lang)
        
        if self.parent.current_lang == "ko":
            msg = f"⚠️ 시간이 만료되었습니다!\n{self.remaining}초 후에 {action_str}이(가) 실행됩니다.\n작업을 저장하세요!"
        else:
            msg = f"⚠️ Time's up!\n{action_str} will execute in {self.remaining} seconds.\nPlease save your work!"
            
        self.label.configure(text=msg)
        self.remaining -= 1
        self._timer_id = self.after(1000, self.update_countdown)

    def execute_action(self):
        self._timer_id = None
        self.parent.grace_dialog = None
        self.destroy()
        self.parent.execute_expire_action(self.action)

    def cancel_dialog(self):
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self.parent.grace_dialog = None
        self.destroy()


class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent, title=None, text=None):
        super().__init__(parent)
        
        self.lang = utils.load_language()
        
        if title is None:
            title = languages.get_text("password_input", self.lang)
        if text is None:
            text = languages.get_text("password_enter", self.lang)
            
        self.title(title)
        self.geometry("300x200")
        self.resizable(False, False)
        
        self.result = None
        
        # Center the dialog
        self.transient(parent)
        self.grab_set()
        
        # Label
        ctk.CTkLabel(self, text=text).pack(pady=20)
        
        # Password entry
        self.pw_entry = ctk.CTkEntry(self, show="*", width=250)
        self.pw_entry.pack(pady=10)
        self.pw_entry.bind("<Return>", lambda e: self.ok_clicked())
        self.pw_entry.focus()
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10)
        
        ctk.CTkButton(btn_frame, text=languages.get_text("confirm", self.lang), command=self.ok_clicked, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text=languages.get_text("cancel", self.lang), command=self.cancel_clicked, width=100).pack(side="left", padx=5)
    
    def ok_clicked(self):
        self.result = self.pw_entry.get()
        self.destroy()
    
    def cancel_clicked(self):
        self.result = None
        self.destroy()
    
    def get_input(self):
        self.wait_window()
        return self.result

class TimePickerDialog(ctk.CTkToplevel):
    def __init__(self, parent, initial_hour=12, initial_min=0):
        super().__init__(parent)
        
        self.lang = utils.load_language()
        
        self.title(languages.get_text("time_picker_title", self.lang))
        self.geometry("300x350")
        self.resizable(False, False)
        
        self.result = None
        
        # Center the dialog
        self.transient(parent)
        self.grab_set()
        
        # Label
        ctk.CTkLabel(self, text=languages.get_text("select_end_time", self.lang), font=("Arial", 16, "bold")).pack(pady=20)
        
        # Time picker frame
        time_frame = ctk.CTkFrame(self, fg_color="transparent")
        time_frame.pack(pady=20)
        
        # Hour picker
        hour_frame = ctk.CTkFrame(time_frame, fg_color="transparent")
        hour_frame.pack(side="left", padx=20)
        
        ctk.CTkLabel(hour_frame, text=languages.get_text("hour", self.lang), font=("Arial", 14)).pack()
        self.hour_var = ctk.StringVar(value=str(initial_hour))
        hour_spinbox = ctk.CTkSegmentedButton(hour_frame, values=[str(i) for i in range(24)], 
                                               variable=self.hour_var, width=100)
        
        # Create custom hour selector with buttons
        self.hour_value = initial_hour
        self.hour_label = ctk.CTkLabel(hour_frame, text=f"{self.hour_value:02d}", font=("Arial", 32, "bold"))
        self.hour_label.pack(pady=10)
        
        hour_btn_frame = ctk.CTkFrame(hour_frame, fg_color="transparent")
        hour_btn_frame.pack()
        ctk.CTkButton(hour_btn_frame, text="▲", width=50, command=self.hour_up).pack()
        ctk.CTkButton(hour_btn_frame, text="▼", width=50, command=self.hour_down).pack()
        
        # Minute picker
        min_frame = ctk.CTkFrame(time_frame, fg_color="transparent")
        min_frame.pack(side="left", padx=20)
        
        ctk.CTkLabel(min_frame, text=languages.get_text("minute", self.lang), font=("Arial", 14)).pack()
        self.min_value = initial_min
        self.min_label = ctk.CTkLabel(min_frame, text=f"{self.min_value:02d}", font=("Arial", 32, "bold"))
        self.min_label.pack(pady=10)
        
        min_btn_frame = ctk.CTkFrame(min_frame, fg_color="transparent")
        min_btn_frame.pack()
        ctk.CTkButton(min_btn_frame, text="▲", width=50, command=self.min_up).pack()
        ctk.CTkButton(min_btn_frame, text="▼", width=50, command=self.min_down).pack()
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text=languages.get_text("confirm", self.lang), command=self.ok_clicked, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text=languages.get_text("cancel", self.lang), command=self.cancel_clicked, width=100).pack(side="left", padx=5)
    
    def hour_up(self):
        self.hour_value = (self.hour_value + 1) % 24
        self.hour_label.configure(text=f"{self.hour_value:02d}")
    
    def hour_down(self):
        self.hour_value = (self.hour_value - 1) % 24
        self.hour_label.configure(text=f"{self.hour_value:02d}")
    
    def min_up(self):
        self.min_value = (self.min_value + 1) % 60
        self.min_label.configure(text=f"{self.min_value:02d}")
    
    def min_down(self):
        self.min_value = (self.min_value - 1) % 60
        self.min_label.configure(text=f"{self.min_value:02d}")
    
    def ok_clicked(self):
        self.result = (self.hour_value, self.min_value)
        self.destroy()
    
    def cancel_clicked(self):
        self.result = None
        self.destroy()
    
    def get_input(self):
        self.wait_window()
        return self.result

class GameTimerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.current_lang = utils.load_language()
        self.title(f"{languages.get_text('app_title', self.current_lang)} v{VERSION}")
        self.geometry("400x920")
        self.resizable(False, True)

        self.timer = None
        self.grace_dialog = None
        self.action_var = ctk.StringVar(value="shutdown")
        self._fallback_timer = None  # UI가 막혀도 만료 동작을 실행하기 위한 백업 타이머
        self._relock_job = None
        self._action_done = False
        self._timer_action = "shutdown"
        self.timer_type = None
        self.timer_target = None
        self.timer_end_at = None
        self.timer_exact = True
        self.initial_duration = 0

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        self.tray_icon = None
        self.setup_tray_icon()

        self._tick_count = 0  # 타이머 상태 저장 주기 카운터

        utils.ensure_autostart()

        if not utils.is_password_set():
            self.show_setup_password()
            if utils.detect_tampering():
                # 비밀번호 파일과 레지스트리 백업이 모두 삭제됨 → 기록을 남겨 부모가 통계에서 확인 가능
                utils.save_log(0, "tamper", "password")
                self.after(300, lambda: WarningDialog(self, languages.get_text("tamper_detected", self.current_lang)))
        else:
            # 저장된 타이머 상태가 있으면 자동 복원
            saved_state = utils.load_timer_state()
            if saved_state:
                self._resume_timer(saved_state)
            else:
                self.show_dashboard()

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def show_setup_password(self):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text=languages.get_text("password_setup", self.current_lang), font=("Arial", 24, "bold")).pack(pady=20)
        ctk.CTkLabel(self.container, text=languages.get_text("password_setup_msg", self.current_lang)).pack(pady=10)

        self.pw_entry = ctk.CTkEntry(self.container, show="*", placeholder_text=languages.get_text("password", self.current_lang))
        self.pw_entry.pack(pady=10, fill="x")
        self.pw_entry.bind("<Return>", lambda e: self.pw_confirm.focus())
        
        self.pw_confirm = ctk.CTkEntry(self.container, show="*", placeholder_text=languages.get_text("password_confirm", self.current_lang))
        self.pw_confirm.pack(pady=10, fill="x")
        self.pw_confirm.bind("<Return>", lambda e: self.set_password())

        ctk.CTkButton(self.container, text=languages.get_text("setup_complete", self.current_lang), command=self.set_password).pack(pady=20, fill="x")

    def set_password(self):
        pw = self.pw_entry.get()
        confirm = self.pw_confirm.get()

        if not pw:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("password_empty", self.current_lang))
            return
        if pw != confirm:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("password_mismatch", self.current_lang))
            return

        utils.save_password(pw)
        messagebox.showinfo(languages.get_text("success", self.current_lang), languages.get_text("password_set_success", self.current_lang))
        self.show_dashboard()

    def _resume_timer(self, state):
        """저장된 타이머 상태로부터 자동 복원합니다."""
        remaining = int(state.get("remaining", 0))
        timer_type = state.get("timer_type", "countdown")
        target = state.get("target")
        action = state.get("action", "shutdown")
        initial_duration = state.get("initial_duration", remaining)
        end_at = state.get("end_at")
        try:
            saved_time = datetime.fromisoformat(state.get("saved_at", ""))
        except Exception:
            saved_time = None

        # 날짜가 바뀌었으면 남은 시간은 초기화 (그때까지 쓴 시간만 그날 기록으로 남김)
        if saved_time is None or saved_time.date() != datetime.now().date():
            utils.clear_timer_state()
            used = initial_duration - remaining
            if saved_time and used > 0 and timer_type != "schedule":
                utils.save_log(used, timer_type, target, timestamp=saved_time)
            self.show_dashboard()
            return

        if timer_type == "schedule" and end_at:
            remaining = max(0, int(end_at - time.time()))
        elif timer_type == "countdown":
            # 컴퓨터를 껐다 켠 경우: 꺼져 있던 시간은 차감하지 않고 남은 시간 그대로 이어감
            # 컴퓨터는 켜진 채 프로그램만 강제 종료된 경우: 그동안 흐른 시간도 차감 (우회 방지)
            boot_time = system_control.get_boot_time()
            rebooted = boot_time is not None and boot_time > saved_time.timestamp()
            if not rebooted:
                elapsed = int((datetime.now() - saved_time).total_seconds())
                remaining = max(0, remaining - elapsed)
        # game: 게임 실행 중에만 차감되므로 꺼져 있던 시간은 차감하지 않음

        self.action_var.set(action)
        self._timer_action = action
        self.initial_duration = initial_duration
        self.timer_type = timer_type
        self.timer_target = target
        self.timer_end_at = end_at if timer_type == "schedule" else None

        if remaining <= 0:
            # 타이머가 이미 만료됨 → 확인 창을 기다리지 않고 유예 경고 후 동작 실행
            utils.clear_timer_state()
            utils.save_log(initial_duration, timer_type, target)
            self.timer = None
            self.show_timer_screen()
            self.time_label.configure(text="00:00")
            self._arm_expire_action(action)
            self.after(300, self._show_grace_warning)
            return

        # 타이머 복원
        self.timer_exact = state.get("exact", True)
        self.timer = self._create_timer(remaining, target, self.timer_end_at, self.timer_exact)
        self.timer.start()
        self.show_timer_screen()

        # 복원 알림 (메인 루프를 막지 않는 창)
        time_str = GameTimer.format_time(remaining)
        self.after(300, lambda: WarningDialog(
            self, languages.get_text("timer_resumed", self.current_lang).format(time=time_str),
            title_key="app_title", color="#3B8ED0"))

    def _create_timer(self, seconds, process_name=None, end_at=None, exact=True):
        if process_name:
            return ProcessTimer(seconds, process_name, self.update_timer_display, self.on_timer_finish, self.on_warning, exact=exact)
        return GameTimer(seconds, self.update_timer_display, self.on_timer_finish, self.on_warning, end_at=end_at)

    def show_dashboard(self):
        self.clear_container()

        ctk.CTkLabel(self.container, text=languages.get_text("game_time_settings", self.current_lang), font=("Arial", 24, "bold")).pack(pady=10)

        # Tab View
        self.tab_view = ctk.CTkTabview(self.container)
        self.tab_view.pack(pady=10, fill="x")
        
        self.tab_game = self.tab_view.add(languages.get_text("tab_game", self.current_lang))
        self.tab_duration = self.tab_view.add(languages.get_text("tab_countdown", self.current_lang))
        self.tab_schedule = self.tab_view.add(languages.get_text("tab_schedule", self.current_lang))
        
        # Tab 1: Duration
        time_frame = ctk.CTkFrame(self.tab_duration, fg_color="transparent")
        time_frame.pack(pady=20)
        
        self.hour_entry = ctk.CTkEntry(time_frame, width=60, placeholder_text="0")
        self.hour_entry.pack(side="left", padx=5)
        ctk.CTkLabel(time_frame, text=languages.get_text("hours", self.current_lang)).pack(side="left")
        
        self.min_entry = ctk.CTkEntry(time_frame, width=60, placeholder_text="0")
        self.min_entry.pack(side="left", padx=5)
        ctk.CTkLabel(time_frame, text=languages.get_text("minutes", self.current_lang)).pack(side="left")

        # Tab 2: Schedule
        schedule_frame = ctk.CTkFrame(self.tab_schedule, fg_color="transparent")
        schedule_frame.pack(pady=20)
        
        self.target_hour_entry = ctk.CTkEntry(schedule_frame, width=60, placeholder_text="24" + languages.get_text("hour", self.current_lang))
        self.target_hour_entry.pack(side="left", padx=5)
        ctk.CTkLabel(schedule_frame, text=languages.get_text("hour", self.current_lang)).pack(side="left")
        
        self.target_min_entry = ctk.CTkEntry(schedule_frame, width=60, placeholder_text=languages.get_text("minute", self.current_lang))
        self.target_min_entry.pack(side="left", padx=5)
        ctk.CTkLabel(schedule_frame, text=languages.get_text("minute", self.current_lang)).pack(side="left")
        
        # Time picker button
        ctk.CTkButton(self.tab_schedule, text=languages.get_text("time_picker", self.current_lang), command=self.open_time_picker, width=150).pack(pady=10)
        
        ctk.CTkLabel(self.tab_schedule, text=languages.get_text("schedule_note", self.current_lang), font=("Arial", 12), text_color="gray").pack()

        # Tab 3: Specific Game
        game_frame = ctk.CTkFrame(self.tab_game, fg_color="transparent")
        game_frame.pack(pady=20)

        self.game_hour_entry = ctk.CTkEntry(game_frame, width=60, placeholder_text="0")
        self.game_hour_entry.pack(side="left", padx=5)
        ctk.CTkLabel(game_frame, text=languages.get_text("hours", self.current_lang)).pack(side="left")

        self.game_min_entry = ctk.CTkEntry(game_frame, width=60, placeholder_text="0")
        self.game_min_entry.pack(side="left", padx=5)
        ctk.CTkLabel(game_frame, text=languages.get_text("minutes", self.current_lang)).pack(side="left")

        ctk.CTkLabel(self.tab_game, text=languages.get_text("game_process_name", self.current_lang), font=("Arial", 12)).pack(pady=(10, 5))
        presets = [
            "Roblox (RobloxPlayerBeta)",
            "Minecraft (javaw)",
            "League of Legends (League of Legends)",
            "Valorant (VALORANT-Win64-Shipping)",
            "Overwatch (Overwatch)",
            "Steam (steam)",
            "Nexon Launcher (NexonLauncher)",
            "MapleStory (maplestory)"
        ]
        self.game_name_combobox = ctk.CTkComboBox(self.tab_game, values=presets, width=250)
        self.game_name_combobox.set("Roblox (RobloxPlayerBeta)")
        self.game_name_combobox.pack(pady=10)
        
        ctk.CTkLabel(self.tab_game, text=languages.get_text("game_note", self.current_lang), font=("Arial", 12), text_color="gray").pack()

        # Daily Limit Section
        daily_frame = ctk.CTkFrame(self.container)
        daily_frame.pack(pady=10, fill="x")

        ctk.CTkLabel(daily_frame, text=languages.get_text("daily_limit", self.current_lang), font=("Arial", 13, "bold")).pack(pady=(5, 2))

        self.daily_limit_var = ctk.BooleanVar(value=utils.load_daily_limit() > 0)
        ctk.CTkCheckBox(daily_frame, text=languages.get_text("daily_limit_enable", self.current_lang),
                        variable=self.daily_limit_var, command=self._on_daily_limit_toggled).pack(pady=2)

        daily_time_frame = ctk.CTkFrame(daily_frame, fg_color="transparent")
        daily_time_frame.pack(pady=5)

        saved_limit = utils.load_daily_limit()
        saved_h = saved_limit // 3600 if saved_limit > 0 else 0
        saved_m = (saved_limit % 3600) // 60 if saved_limit > 0 else 0

        self.daily_h_entry = ctk.CTkEntry(daily_time_frame, width=50, placeholder_text="0")
        self.daily_h_entry.pack(side="left", padx=3)
        if saved_h > 0:
            self.daily_h_entry.insert(0, str(saved_h))
        ctk.CTkLabel(daily_time_frame, text=languages.get_text("daily_limit_hours", self.current_lang)).pack(side="left")

        self.daily_m_entry = ctk.CTkEntry(daily_time_frame, width=50, placeholder_text="0")
        self.daily_m_entry.pack(side="left", padx=3)
        if saved_m > 0:
            self.daily_m_entry.insert(0, str(saved_m))
        ctk.CTkLabel(daily_time_frame, text=languages.get_text("daily_limit_minutes", self.current_lang)).pack(side="left")

        # 오늘 남은 허용 시간 표시
        daily_remaining = utils.get_daily_remaining()
        if daily_remaining >= 0:
            rh, rm = divmod(daily_remaining // 60, 60)
            remaining_str = f"{rh}{languages.get_text('hour', self.current_lang)} {rm}{languages.get_text('minute', self.current_lang)}"
            self.daily_remaining_label = ctk.CTkLabel(daily_frame,
                text=languages.get_text("daily_remaining", self.current_lang).format(time=remaining_str),
                font=("Arial", 12), text_color="#3B8ED0")
            self.daily_remaining_label.pack(pady=2)

        self._apply_daily_limit_state()

        # Action Selection
        ctk.CTkLabel(self.container, text=languages.get_text("action_after_time", self.current_lang)).pack(pady=(10, 5))
        ctk.CTkRadioButton(self.container, text=languages.get_text("shutdown", self.current_lang), variable=self.action_var, value="shutdown").pack(pady=5)
        ctk.CTkRadioButton(self.container, text=languages.get_text("logoff", self.current_lang), variable=self.action_var, value="logoff").pack(pady=5)
        ctk.CTkRadioButton(self.container, text=languages.get_text("lock", self.current_lang), variable=self.action_var, value="lock").pack(pady=5)

        ctk.CTkButton(self.container, text=languages.get_text("start_timer", self.current_lang), command=self.start_timer, fg_color="green").pack(pady=20, fill="x")
        
        ctk.CTkButton(self.container, text=languages.get_text("password_change", self.current_lang), command=self.change_password_dialog, fg_color="gray").pack(pady=5, fill="x")
        ctk.CTkButton(self.container, text=languages.get_text("about", self.current_lang), command=self.show_about_dialog, fg_color="gray").pack(pady=5, fill="x")
        ctk.CTkButton(self.container, text=languages.get_text("statistics", self.current_lang), command=self.show_statistics, fg_color="#3B8ED0").pack(pady=5, fill="x")
        
        # Language Switcher
        lang_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        lang_frame.pack(pady=5, fill="x")
        
        # Language
        ctk.CTkLabel(lang_frame, text="🌐 " + languages.get_text("language", self.current_lang), width=60).pack(side="left", padx=5)
        self.lang_var = ctk.StringVar(value=self.current_lang)
        lang_menu = ctk.CTkOptionMenu(lang_frame, variable=self.lang_var, 
                                      values=["ko", "en"],
                                      command=self.change_language, width=100)
        lang_menu.pack(side="left", padx=5)
        
        # Theme
        ctk.CTkLabel(lang_frame, text="🎨 " + languages.get_text("theme", self.current_lang), width=60).pack(side="left", padx=(20, 5))
        self.theme_var = ctk.StringVar(value=utils.load_theme())
        theme_menu = ctk.CTkOptionMenu(lang_frame, variable=self.theme_var,
                                       values=["Dark", "Light"],
                                       command=self.change_theme, width=100)
        theme_menu.pack(side="left", padx=5)

        self.load_saved_settings()

    def _apply_daily_limit_state(self):
        """일일 제한 체크박스 상태에 따라 입력 필드를 활성화/비활성화합니다."""
        state = "normal" if self.daily_limit_var.get() else "disabled"
        self.daily_h_entry.configure(state=state)
        self.daily_m_entry.configure(state=state)

    def _verify_password(self):
        """비밀번호를 물어 맞으면 True. 틀리면 오류를 표시합니다."""
        dialog = PasswordDialog(self, title=languages.get_text("password_confirm", self.current_lang), text=languages.get_text("password_enter", self.current_lang))
        pw = dialog.get_input()
        if pw and utils.check_password(pw):
            return True
        if pw is not None:
            WarningDialog(self, languages.get_text("password_incorrect", self.current_lang), title_key="error")
        return False

    def _read_daily_limit_entries(self):
        h = int(self.daily_h_entry.get() or 0)
        m = int(self.daily_m_entry.get() or 0)
        return (h * 3600) + (m * 60)

    def _on_daily_limit_toggled(self):
        """일일 제한 켜기/끄기는 비밀번호 확인 후에만 저장합니다."""
        enabled = self.daily_limit_var.get()
        if not self._verify_password():
            self.daily_limit_var.set(not enabled)
            return
        self._apply_daily_limit_state()
        if enabled:
            try:
                total = self._read_daily_limit_entries()
                if total > 0:
                    utils.save_daily_limit(total)
            except ValueError:
                pass
        else:
            utils.save_daily_limit(0)

    def _current_tab_key(self):
        current = self.tab_view.get()
        for key in TAB_KEYS:
            if current == languages.get_text(key, self.current_lang):
                return key
        return "tab_countdown"

    def change_language(self, choice):
        utils.save_language(choice)
        self.current_lang = choice
        self.title(f"{languages.get_text('app_title', self.current_lang)} v{VERSION}")
        self.show_dashboard()

    def change_theme(self, choice):
        utils.save_theme(choice)
        ctk.set_appearance_mode(choice)

    def load_saved_settings(self):
        settings = utils.load_settings()
        if not settings:
            return

        try:
            if "game_h" in settings: 
                self.game_hour_entry.delete(0, "end")
                self.game_hour_entry.insert(0, settings["game_h"])
            if "game_m" in settings: 
                self.game_min_entry.delete(0, "end")
                self.game_min_entry.insert(0, settings["game_m"])
            if "game_name" in settings: 
                self.game_name_combobox.set(settings["game_name"])
                
            if "duration_h" in settings: 
                self.hour_entry.delete(0, "end")
                self.hour_entry.insert(0, settings["duration_h"])
            if "duration_m" in settings: 
                self.min_entry.delete(0, "end")
                self.min_entry.insert(0, settings["duration_m"])
            
            if "schedule_h" in settings: 
                self.target_hour_entry.delete(0, "end")
                self.target_hour_entry.insert(0, settings["schedule_h"])
            if "schedule_m" in settings: 
                self.target_min_entry.delete(0, "end")
                self.target_min_entry.insert(0, settings["schedule_m"])
            
            if "action" in settings: self.action_var.set(settings["action"])
            
            if settings.get("last_tab_key") in TAB_KEYS:
                self.tab_view.set(languages.get_text(settings["last_tab_key"], self.current_lang))
        except Exception as e:
            print(f"Error loading settings: {e}")

    def change_password_dialog(self):
        dialog = PasswordDialog(self, title=languages.get_text("password_change", self.current_lang), text=languages.get_text("current_password", self.current_lang))
        current_pw = dialog.get_input()
        
        if current_pw and utils.check_password(current_pw):
            self.show_setup_password() # Re-use setup screen for new password
        else:
            if current_pw is not None:
                messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("password_mismatch", self.current_lang))

    def show_about_dialog(self):
        about_window = ctk.CTkToplevel(self)
        about_window.title(languages.get_text("about_title", self.current_lang))
        about_window.geometry("300x350")
        about_window.resizable(False, False)
        
        # Center the dialog
        about_window.transient(self)
        about_window.grab_set()
        
        ctk.CTkLabel(about_window, text=f"{languages.get_text('app_title', self.current_lang)} v{VERSION}", font=("Arial", 18, "bold")).pack(pady=(30, 10))
        
        ctk.CTkLabel(about_window, text=languages.get_text("creator", self.current_lang), font=("Arial", 14)).pack(pady=5)
        ctk.CTkLabel(about_window, text=languages.get_text("email", self.current_lang), font=("Arial", 14)).pack(pady=5)
        
        link = ctk.CTkLabel(about_window, text="https://hadesyi.tistory.com/", font=("Arial", 12), text_color="#3B8ED0", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://hadesyi.tistory.com/"))
        
        ctk.CTkButton(about_window, text=languages.get_text("confirm", self.current_lang), command=about_window.destroy, width=100).pack(pady=30)

    def open_time_picker(self):
        # Get current values or defaults
        try:
            initial_hour = int(self.target_hour_entry.get()) if self.target_hour_entry.get() else 12
        except:
            initial_hour = 12
        
        try:
            initial_min = int(self.target_min_entry.get()) if self.target_min_entry.get() else 0
        except:
            initial_min = 0
        
        dialog = TimePickerDialog(self, initial_hour, initial_min)
        result = dialog.get_input()
        
        if result:
            hour, minute = result
            self.target_hour_entry.delete(0, "end")
            self.target_hour_entry.insert(0, str(hour))
            self.target_min_entry.delete(0, "end")
            self.target_min_entry.insert(0, str(minute))

    def show_statistics(self):
        stats_window = ctk.CTkToplevel(self)
        stats_window.title(languages.get_text("stats_title", self.current_lang))
        stats_window.geometry("400x700")
        
        # Center
        stats_window.transient(self)
        stats_window.grab_set()
        
        # Create TabView
        tabview = ctk.CTkTabview(stats_window)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        weekly_tab = tabview.add(languages.get_text("weekly_stats", self.current_lang))
        search_tab = tabview.add(languages.get_text("search_tab", self.current_lang))
        
        # --- 1. WEEKLY STATS TAB ---
        # Today's Total
        today_seconds = utils.get_today_total()
        h, m = divmod(today_seconds // 60, 60)
        today_str = f"{h}{languages.get_text('hour', self.current_lang)} {m}{languages.get_text('minute', self.current_lang)}"
        
        ctk.CTkLabel(weekly_tab, text=languages.get_text("today_total", self.current_lang), font=("Arial", 14, "bold")).pack(pady=(10, 2))
        ctk.CTkLabel(weekly_tab, text=today_str, font=("Arial", 20, "bold"), text_color="#3B8ED0").pack(pady=(0, 10))
        
        # Weekly column chart container
        weekly_frame = ctk.CTkFrame(weekly_tab, height=185, fg_color=("#E2E8F0", "#1E293B"))
        weekly_frame.pack(pady=5, padx=10, fill="x")
        weekly_frame.pack_propagate(False)
        
        weekly_data = utils.get_weekly_stats()
        max_seconds = max([s for _, s in weekly_data]) if any(s for _, s in weekly_data) else 1
        weekly_total_seconds = sum([s for _, s in weekly_data])
        
        day_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        current_weekday = datetime.now().weekday()
        
        for i, (day_name, seconds) in enumerate(weekly_data):
            col_frame = ctk.CTkFrame(weekly_frame, fg_color="transparent", width=46)
            col_frame.pack(side="left", padx=2, fill="y", expand=True)
            col_frame.pack_propagate(False)
            
            # Time text (top)
            h, m = divmod(seconds // 60, 60)
            if seconds > 0:
                time_str = f"{h}h\n{m}m" if h > 0 else f"{m}m"
            else:
                time_str = ""
            time_label = ctk.CTkLabel(col_frame, text=time_str, font=("Arial", 10), height=30, text_color="gray")
            time_label.pack(side="top", fill="x")
            
            # Day label (bottom)
            translated_day = languages.get_text(day_keys[i], self.current_lang)
            if self.current_lang == "en":
                day_abbreviations = ["M", "T", "W", "Th", "F", "S", "Su"]
                day_text = day_abbreviations[i]
            else:
                day_text = translated_day[0]
                
            is_today = (i == current_weekday)
            
            day_label = ctk.CTkLabel(
                col_frame, 
                text=day_text, 
                font=("Arial", 11, "bold" if is_today else "normal"),
                text_color=("#10B981" if is_today else "#1E293B", "#10B981" if is_today else "#94A3B8")
            )
            day_label.pack(side="bottom", fill="x", pady=2)
            
            # Vertical bar (middle, anchored to bottom)
            max_bar_height = 100
            bar_height = int((seconds / max_seconds) * max_bar_height) if max_seconds > 0 else 0
            if seconds > 0 and bar_height < 6:
                bar_height = 6
                
            bar_container = ctk.CTkFrame(col_frame, fg_color="transparent")
            bar_container.pack(side="bottom", fill="both", expand=True)
            
            if is_today:
                bar_color = ("#10B981", "#10B981")
            else:
                bar_color = ("#3B8ED0", "#1F538D")
                
            bar = ctk.CTkFrame(bar_container, width=16, height=bar_height, corner_radius=4, fg_color=bar_color)
            bar.pack(side="bottom", pady=(0, 2))
            bar.pack_propagate(False)
            
        # Weekly Total and Average Summary
        th, tm = divmod(weekly_total_seconds // 60, 60)
        weekly_total_str = f"{th}{languages.get_text('hour', self.current_lang)} {tm}{languages.get_text('minute', self.current_lang)}"
        avg_seconds = weekly_total_seconds // 7
        ah, am = divmod(avg_seconds // 60, 60)
        weekly_avg_str = f"{ah}{languages.get_text('hour', self.current_lang)} {am}{languages.get_text('minute', self.current_lang)}"
        
        summary_text = f"{languages.get_text('weekly_total', self.current_lang)}: {weekly_total_str}   |   {languages.get_text('daily_average', self.current_lang)}: {weekly_avg_str}"
        ctk.CTkLabel(weekly_tab, text=summary_text, font=("Arial", 12, "bold"), text_color="#3B8ED0").pack(pady=10)
        
        # Recent logs list inside Weekly Tab
        ctk.CTkLabel(weekly_tab, text=languages.get_text("recent_logs", self.current_lang), font=("Arial", 12, "bold")).pack(pady=(10, 2), anchor="w", padx=10)
        scroll_frame = ctk.CTkScrollableFrame(weekly_tab, width=340, height=180)
        scroll_frame.pack(pady=5, padx=10, fill="both", expand=True)
        
        logs = utils.load_logs()
        if not logs:
            ctk.CTkLabel(scroll_frame, text=languages.get_text("no_logs", self.current_lang)).pack(pady=20)
        else:
            for log in reversed(logs):
                frame = ctk.CTkFrame(scroll_frame)
                frame.pack(fill="x", pady=2)
                
                ts = log["timestamp"][5:-3] # MM-DD HH:MM
                duration = log["duration"]
                dh, dm = divmod(duration // 60, 60)
                dur_str = f"{dh}{languages.get_text('hour', self.current_lang)} {dm}{languages.get_text('minute', self.current_lang)}" if dh > 0 else f"{dm}{languages.get_text('minute', self.current_lang)}"
                
                type_map = {
                    "game": languages.get_text("type_game", self.current_lang), 
                    "countdown": languages.get_text("type_countdown", self.current_lang), 
                    "schedule": languages.get_text("type_schedule", self.current_lang),
                    "tamper": languages.get_text("type_tamper", self.current_lang)
                }
                type_str = type_map.get(log["type"], log["type"])
                if log.get("target"):
                    type_str += f" ({log['target']})"
                
                ctk.CTkLabel(frame, text=ts, width=80, anchor="w").pack(side="left", padx=5)
                ctk.CTkLabel(frame, text=type_str, anchor="w").pack(side="left", padx=5, expand=True, fill="x")
                ctk.CTkLabel(frame, text=dur_str, width=60, anchor="e").pack(side="right", padx=5)
                
        # --- 2. SEARCH TAB ---
        # Filters Frame
        filter_frame = ctk.CTkFrame(search_tab)
        filter_frame.pack(pady=10, padx=10, fill="x")
        
        # Year combobox
        current_year = datetime.now().year
        years = [str(current_year - 1), str(current_year), str(current_year + 1)]
        year_var = ctk.StringVar(value=str(current_year))
        year_menu = ctk.CTkOptionMenu(filter_frame, variable=year_var, values=years, width=80)
        year_menu.pack(side="left", padx=5, pady=5)
        
        # Month combobox
        current_month = f"{datetime.now().month:02d}"
        months = [f"{i:02d}" for i in range(1, 13)]
        month_var = ctk.StringVar(value=current_month)
        month_menu = ctk.CTkOptionMenu(filter_frame, variable=month_var, values=months, width=60)
        month_menu.pack(side="left", padx=5, pady=5)
        
        # Day combobox (All / specific day)
        all_translated = languages.get_text("all", self.current_lang)
        days = [all_translated] + [f"{i:02d}" for i in range(1, 32)]
        day_var = ctk.StringVar(value=all_translated)
        day_menu = ctk.CTkOptionMenu(filter_frame, variable=day_var, values=days, width=80)
        day_menu.pack(side="left", padx=5, pady=5)
        
        # Results area
        result_frame = ctk.CTkFrame(search_tab, fg_color="transparent")
        result_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        def perform_search():
            import calendar
            
            # Clear previous result widgets
            for widget in result_frame.winfo_children():
                widget.destroy()
                
            y = year_var.get()
            m = month_var.get()
            d = day_var.get()
            
            search_logs = utils.load_logs()
            filtered_logs = []
            
            if d == all_translated or d == "All" or d == "전체":
                prefix = f"{y}-{m}-"
                is_month_search = True
            else:
                prefix = f"{y}-{m}-{d}"
                is_month_search = False
                
            total_seconds = 0
            for log in search_logs:
                if log["timestamp"].startswith(prefix):
                    filtered_logs.append(log)
                    total_seconds += log.get("duration", 0)
                    
            th, tm = divmod(total_seconds // 60, 60)
            total_str = f"{th}{languages.get_text('hour', self.current_lang)} {tm}{languages.get_text('minute', self.current_lang)}"
            summary_str = f"{languages.get_text('search_total', self.current_lang)}: {total_str}"
            
            if is_month_search:
                try:
                    num_days = calendar.monthrange(int(y), int(m))[1]
                except:
                    num_days = 30
                avg_sec = total_seconds // num_days
                ah, am = divmod(avg_sec // 60, 60)
                avg_str = f"{ah}{languages.get_text('hour', self.current_lang)} {am}{languages.get_text('minute', self.current_lang)}"
                summary_str += f"\n({languages.get_text('daily_average', self.current_lang)}: {avg_str})"
                
            ctk.CTkLabel(result_frame, text=summary_str, font=("Arial", 13, "bold"), text_color="#3B8ED0").pack(pady=10)
            
            scroll_search = ctk.CTkScrollableFrame(result_frame, width=340, height=300)
            scroll_search.pack(fill="both", expand=True, padx=5, pady=5)
            
            if not filtered_logs:
                ctk.CTkLabel(scroll_search, text=languages.get_text("no_logs", self.current_lang)).pack(pady=20)
            else:
                for log in reversed(filtered_logs):
                    frame = ctk.CTkFrame(scroll_search)
                    frame.pack(fill="x", pady=2)
                    
                    ts = log["timestamp"][5:-3] # MM-DD HH:MM
                    duration = log["duration"]
                    dh, dm = divmod(duration // 60, 60)
                    dur_str = f"{dh}{languages.get_text('hour', self.current_lang)} {dm}{languages.get_text('minute', self.current_lang)}" if dh > 0 else f"{dm}{languages.get_text('minute', self.current_lang)}"
                    
                    type_map = {
                        "game": languages.get_text("type_game", self.current_lang), 
                        "countdown": languages.get_text("type_countdown", self.current_lang), 
                        "schedule": languages.get_text("type_schedule", self.current_lang),
                        "tamper": languages.get_text("type_tamper", self.current_lang)
                    }
                    type_str = type_map.get(log["type"], log["type"])
                    if log.get("target"):
                        type_str += f" ({log['target']})"
                    
                    ctk.CTkLabel(frame, text=ts, width=80, anchor="w").pack(side="left", padx=5)
                    ctk.CTkLabel(frame, text=type_str, anchor="w").pack(side="left", padx=5, expand=True, fill="x")
                    ctk.CTkLabel(frame, text=dur_str, width=60, anchor="e").pack(side="right", padx=5)
                    
        # Search button
        search_btn = ctk.CTkButton(filter_frame, text=languages.get_text("search", self.current_lang), width=60, command=perform_search)
        search_btn.pack(side="left", padx=5, pady=5)
        
        # Trigger initial search for the current month
        perform_search()

    def start_timer(self):
        total_seconds = 0
        process_name = None
        exact = True
        end_at = None

        try:
            tab_key = self._current_tab_key()

            # Save settings first (without losing the paused keys yet)
            settings = {
                "last_tab_key": tab_key,
                "action": self.action_var.get(),
                "game_h": self.game_hour_entry.get(),
                "game_m": self.game_min_entry.get(),
                "game_name": self.game_name_combobox.get(),
                "duration_h": self.hour_entry.get(),
                "duration_m": self.min_entry.get(),
                "schedule_h": self.target_hour_entry.get(),
                "schedule_m": self.target_min_entry.get()
            }

            # Load stored settings to check for paused timer to resume (중지한 날 당일에만 이어서 시작)
            saved_settings = utils.load_settings()
            today = datetime.now().strftime("%Y-%m-%d")
            if saved_settings.get("paused_date") == today:
                paused_remaining = saved_settings.get("paused_remaining", 0)
                paused_type = saved_settings.get("paused_type")
            else:
                paused_remaining, paused_type = 0, None

            if tab_key == "tab_countdown":
                h = int(self.hour_entry.get() or 0)
                m = int(self.min_entry.get() or 0)
                total_seconds = (h * 60 + m) * 60

                if paused_remaining > 0 and paused_type == "countdown":
                    ch, cm = divmod(paused_remaining // 60, 60)
                    if h == ch and m == cm:
                        total_seconds = paused_remaining

            elif tab_key == "tab_game":
                h = int(self.game_hour_entry.get() or 0)
                m = int(self.game_min_entry.get() or 0)
                total_seconds = (h * 60 + m) * 60
                raw_game_name = self.game_name_combobox.get()
                match = re.search(r'\(([^)]+)\)', raw_game_name)
                process_name = match.group(1) if match else raw_game_name.strip()
                exact = bool(match)  # 프리셋은 정확히 일치, 직접 입력은 부분 일치
                if not process_name:
                    messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("enter_game_name", self.current_lang))
                    return

                if paused_remaining > 0 and paused_type == "game":
                    gh, gm = divmod(paused_remaining // 60, 60)
                    if h == gh and m == gm and raw_game_name == saved_settings.get("game_name"):
                        total_seconds = paused_remaining

            else: # 특정 시간
                target_h_str = self.target_hour_entry.get()
                # Remove non-digit characters if any (like "시")
                target_h = int(''.join(filter(str.isdigit, target_h_str)))

                target_m_str = self.target_min_entry.get() or "0"
                target_m = int(''.join(filter(str.isdigit, target_m_str)))

                if not (0 <= target_h <= 23 and 0 <= target_m <= 59):
                    raise ValueError("Invalid time")

                now = datetime.now()
                target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)

                if target <= now:
                    target += timedelta(days=1)

                total_seconds = int((target - now).total_seconds())
                end_at = target.timestamp()

            # 일일 제한 값을 바꿨다면 비밀번호 확인 후 저장
            if self.daily_limit_var.get():
                limit_seconds = self._read_daily_limit_entries()
                if limit_seconds > 0 and limit_seconds != utils.load_daily_limit():
                    if not self._verify_password():
                        return
                    utils.save_daily_limit(limit_seconds)

            # Clear paused keys from the saved dictionary
            for key in ("paused_remaining", "paused_type", "paused_date", "last_tab"):
                saved_settings.pop(key, None)

            # Merge and save
            saved_settings.update(settings)
            utils.save_settings(saved_settings)

        except ValueError:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("enter_valid_time", self.current_lang))
            return

        if total_seconds <= 0:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("min_time_1min", self.current_lang))
            return

        # 일일 제한 체크 ("특정 시간"은 종료 예약이므로 사용 시간 제한을 적용하지 않음)
        daily_remaining = utils.get_daily_remaining() if tab_key != "tab_schedule" else -1
        if daily_remaining == 0:
            messagebox.showerror(
                languages.get_text("error", self.current_lang),
                languages.get_text("daily_limit_exceeded", self.current_lang)
            )
            return
        elif daily_remaining > 0 and total_seconds > daily_remaining:
            # 일일 제한에 맞게 조정
            total_seconds = daily_remaining
            rh, rm = divmod(total_seconds // 60, 60)
            cap_str = f"{rh}{languages.get_text('hour', self.current_lang)} {rm}{languages.get_text('minute', self.current_lang)}"
            messagebox.showinfo(
                languages.get_text("daily_limit", self.current_lang),
                languages.get_text("daily_limit_capped", self.current_lang).format(time=cap_str)
            )

        self.initial_duration = total_seconds
        self.timer_type = "game" if process_name else ("schedule" if tab_key == "tab_schedule" else "countdown")
        self.timer_target = process_name
        self.timer_end_at = end_at
        self.timer_exact = exact
        self._timer_action = self.action_var.get()
        self._stop_enforcement()

        self.timer = self._create_timer(total_seconds, process_name, end_at, exact)
        self.timer.start()

        # 타이머 상태 저장 (작업 관리자 강제 종료/재부팅 대응)
        self._save_timer_state(total_seconds)
        self._tick_count = 0

        self.show_timer_screen()

    def _save_timer_state(self, remaining):
        utils.save_timer_state(
            remaining, self.timer_type, self.timer_target, self._timer_action,
            self.initial_duration, end_at=self.timer_end_at, exact=self.timer_exact
        )

    def show_timer_screen(self):
        self.clear_container()

        ctk.CTkLabel(self.container, text=languages.get_text("remaining_time", self.current_lang), font=("Arial", 20)).pack(pady=(40, 10))

        self.time_label = ctk.CTkLabel(self.container, text="00:00:00", font=("Arial", 48, "bold"), text_color="#FF5555")
        self.time_label.pack(pady=20)

        ctk.CTkButton(self.container, text=languages.get_text("stop_timer", self.current_lang), command=self.prompt_stop_timer, fg_color="red").pack(pady=40, fill="x")

        # Mini mode hint
        ctk.CTkLabel(self.container, text=languages.get_text("timer_running_note", self.current_lang), font=("Arial", 12), text_color="gray").pack(side="bottom", pady=10)

    def update_timer_display(self, time_str):
        # 타이머 스레드에서 호출되므로 UI 갱신은 메인 스레드로 넘깁니다 (Tkinter는 스레드 안전하지 않음)
        timer = self.timer
        if timer:
            remaining = timer.remaining
            # 10초마다 타이머 상태를 파일에 저장 (강제 종료/전원 끔 대응)
            self._tick_count += 1
            if self._tick_count % 10 == 0:
                self._save_timer_state(remaining)
        try:
            self.after(0, self._set_time_label, time_str)
        except RuntimeError:
            pass  # 앱 종료 중

    def _set_time_label(self, time_str):
        label = getattr(self, "time_label", None)
        if label is not None and label.winfo_exists():
            label.configure(text=time_str)

    def on_warning(self, remaining_seconds):
        # Use after() to schedule the warning dialog in the main thread
        # This prevents blocking the timer thread
        self.after(0, self._show_warning_dialog, remaining_seconds)

    def _show_warning_dialog(self, remaining_seconds):
        # Bring window to front
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.attributes("-topmost", False)

        minutes = remaining_seconds // 60
        msg = languages.get_text("time_warning", self.current_lang).format(minutes=minutes)
        WarningDialog(self, msg)

    def on_timer_finish(self):
        # 타이머 스레드에서 호출됨. 메인 루프가 열린 창 등으로 막혀 있어도
        # 만료 동작이 반드시 실행되도록 여기서 먼저 예약합니다.
        utils.clear_timer_state()
        utils.save_log(self.initial_duration, self.timer_type, self.timer_target)
        self._arm_expire_action(self._timer_action)

        # 유예 경고 표시 (메인 스레드에서 실행)
        self.after(0, self._show_grace_warning)

    def _arm_expire_action(self, action):
        """UI 상태와 관계없이 만료 동작을 예약합니다."""
        self._cancel_fallback()
        self._action_done = False
        if action == "shutdown":
            # Windows 자체 60초 유예 후 종료
            system_control.shutdown_system(languages.get_text("shutdown_reason", self.current_lang))
            self._action_done = True
            return
        # 유예 창이 정상 동작하면 그쪽에서 먼저 실행되고, 아니면 이 백업 타이머가 실행
        self._fallback_timer = threading.Timer(GRACE_SECONDS + 5, self._run_expire_action, args=(action,))
        self._fallback_timer.daemon = True
        self._fallback_timer.start()

    def _cancel_fallback(self):
        if self._fallback_timer:
            self._fallback_timer.cancel()
            self._fallback_timer = None

    def execute_expire_action(self, action):
        """유예 창의 카운트다운이 끝났을 때 호출됩니다."""
        self._cancel_fallback()
        self._run_expire_action(action)

    def _run_expire_action(self, action):
        if self._action_done:
            return
        self._action_done = True
        if action == "logoff":
            system_control.logoff_system()
        elif action == "lock":
            system_control.lock_system()
            self._start_relock()

    def _start_relock(self):
        """잠금 해제 후에도 비밀번호로 타이머를 중지할 때까지 주기적으로 다시 잠급니다."""
        self._stop_relock()
        stop_event = threading.Event()
        self._relock_job = stop_event

        def loop():
            while not stop_event.wait(RELOCK_INTERVAL_MS / 1000):
                system_control.lock_system()

        threading.Thread(target=loop, daemon=True).start()

    def _stop_relock(self):
        if self._relock_job:
            self._relock_job.set()
            self._relock_job = None

    def _stop_enforcement(self):
        """예약된 종료/백업 동작/재잠금/유예 창을 모두 해제합니다."""
        self._cancel_fallback()
        self._stop_relock()
        self._action_done = True
        system_control.cancel_shutdown()  # 예약된 종료가 있으면 취소
        if self.grace_dialog:
            self.grace_dialog.cancel_dialog()
            self.grace_dialog = None

    def _is_enforcing(self):
        return bool((self.timer and self.timer.running) or self.grace_dialog is not None or self._relock_job)

    def _show_grace_warning(self):
        """유예 경고를 표시합니다. (동작 자체는 _arm_expire_action에서 이미 예약됨)"""
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)

        action = self._timer_action

        # Close any existing grace dialog just in case
        if self.grace_dialog:
            try:
                self.grace_dialog.destroy()
            except Exception:
                pass
            self.grace_dialog = None

        if action == "shutdown":
            msg = languages.get_text("grace_period_warning_shutdown", self.current_lang)
            WarningDialog(self, msg)
        else:
            self.grace_dialog = GraceWarningDialog(self, action, GRACE_SECONDS)

    def _stop_timer(self):
        """비밀번호 확인 후 타이머와 만료 동작을 모두 중지합니다."""
        if self.timer and self.timer.running:
            # 만료 전 중지: 사용한 시간 기록, 남은 시간은 당일 이어서 시작할 수 있게 저장
            used_seconds = self.initial_duration - self.timer.remaining
            if used_seconds > 0:
                utils.save_log(used_seconds, self.timer_type, self.timer_target)

            try:
                settings = utils.load_settings()
                if self.timer_type in ("countdown", "game"):
                    rh, rm = divmod(self.timer.remaining // 60, 60)
                    prefix = "duration" if self.timer_type == "countdown" else "game"
                    settings[f"{prefix}_h"] = str(rh)
                    settings[f"{prefix}_m"] = str(rm)
                    settings["paused_remaining"] = self.timer.remaining
                    settings["paused_type"] = self.timer_type
                    settings["paused_date"] = datetime.now().strftime("%Y-%m-%d")
                    utils.save_settings(settings)
            except Exception as e:
                print(f"Error updating settings on stop: {e}")

        if self.timer:
            self.timer.stop()
        self.timer = None
        utils.clear_timer_state()
        self._stop_enforcement()

    def prompt_stop_timer(self):
        if self._verify_password():
            self._stop_timer()
            self.show_dashboard()

    def setup_tray_icon(self):
        try:
            image = create_tray_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem(lambda item: languages.get_text("restore", self.current_lang), self.restore_window, default=True),
                pystray.MenuItem(lambda item: languages.get_text("stop_timer", self.current_lang), self.tray_stop_timer),
                pystray.MenuItem(lambda item: languages.get_text("close", self.current_lang), self.tray_quit_app)
            )
            self.tray_icon = pystray.Icon("TimeParents", image, "TimeParents", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception as e:
            print(f"Error setting up tray icon: {e}")

    def restore_window(self, icon=None, item=None):
        self.after(0, self._restore_window_main_thread)

    def _restore_window_main_thread(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def tray_stop_timer(self, icon=None, item=None):
        self.after(0, self._restore_and_stop_timer)

    def _restore_and_stop_timer(self):
        self._restore_window_main_thread()
        self.prompt_stop_timer()

    def tray_quit_app(self, icon=None, item=None):
        self.after(0, self._restore_and_quit_app)

    def _restore_and_quit_app(self):
        self._restore_window_main_thread()
        if self._is_enforcing():
            self.prompt_stop_and_quit()
        else:
            self.quit_app()

    def prompt_stop_and_quit(self):
        if self._verify_password():
            self._stop_timer()
            self.quit_app()

    def quit_app(self):
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        self.destroy()
        sys.exit(0)

    def on_closing(self):
        if self._is_enforcing():
            self.withdraw()
            try:
                self.tray_icon.notify(
                    languages.get_text("tray_running_msg", self.current_lang),
                    languages.get_text("app_title", self.current_lang)
                )
            except Exception:
                pass
        else:
            self.quit_app()

if __name__ == "__main__":
    app = GameTimerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
