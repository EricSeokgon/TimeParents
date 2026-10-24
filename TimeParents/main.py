import customtkinter as ctk
from tkinter import messagebox
import utils
import system_control
import timer_logic
from timer_logic import GameTimer, ProcessTimer
import sys
from datetime import datetime, timedelta
import webbrowser
import languages
import stats_window
from dialogs import close_window, WarningDialog, GraceWarningDialog, PasswordDialog, TimePickerDialog
import pystray
from PIL import Image, ImageDraw
import threading
import re
import time

VERSION = "1.9.0"

GRACE_SECONDS = 60
RELOCK_INTERVAL_MS = 60 * 1000  # 잠금 동작 후 비밀번호로 중지할 때까지 재잠금 주기
TAB_KEYS = ("tab_game", "tab_countdown", "tab_schedule")
GAME_BLOCK_INTERVAL = 3  # 게임 차단 중 프로세스 확인 주기 (초)
CURFEW_CHECK_MS = 15 * 1000  # 사용 금지 시간대 확인 주기
CURFEW_FIRST_CHECK_MS = 3 * 1000
CURFEW_WARNINGS = (600, 300, 60)  # 금지 시간 시작 전 경고 (10분, 5분, 1분 전)
WINDOW_HEIGHT = 580  # 메인·설정 화면이 스크롤 없이 들어가는 높이
CARD_COLOR = ("white", "gray20")  # 바탕과 구분되는 카드 배경 (라이트, 다크)
# 시간 종료 후 동작: (저장 값, 표시 문구 키)
ACTIONS = (("shutdown", "shutdown"), ("logoff", "logoff"), ("lock", "lock"), ("kill_game", "kill_game_option"))

# Load theme before creating app
current_theme = utils.load_theme()
ctk.set_appearance_mode(current_theme)
ctk.set_default_color_theme("blue")

def create_tray_icon_image():
    """시스템 트레이 아이콘 이미지. 앱 아이콘 파일이 없으면 64x64 시계 모양을 직접 그립니다."""
    try:
        return Image.open(utils.ICON_PNG).resize((64, 64), Image.LANCZOS)
    except Exception:
        pass
    try:
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

class GameTimerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.current_lang = utils.load_language()
        self.title(f"{languages.get_text('app_title', self.current_lang)} v{VERSION}")
        try:
            # default로 지정하면 대화상자·통계 창에도 같은 아이콘이 적용됩니다.
            self.iconbitmap(utils.ICON_ICO, default=utils.ICON_ICO)
        except Exception:
            pass
        # 작은 화면(768p 노트북 등)에서는 창 높이를 줄이고 내용은 스크롤로 봅니다.
        height = min(WINDOW_HEIGHT, self.winfo_screenheight() - 100)
        self.geometry(f"420x{height}")
        self.resizable(False, True)

        self.timer = None
        self.grace_dialog = None
        self.action_var = ctk.StringVar(value="shutdown")
        self._fallback_timer = None  # UI가 막혀도 만료 동작을 실행하기 위한 백업 타이머
        self._relock_job = None
        self._game_block_job = None
        self._curfew_enforced_start = None  # 이미 동작을 실행한 금지 구간의 시작 시각
        self._curfew_override_until = None  # 비밀번호로 중지한 경우 이 시각까지 금지 해제
        self._curfew_warned = set()
        self._action_done = False
        self._timer_action = "shutdown"
        self.timer_type = None
        self.timer_target = None
        self.timer_end_at = None
        self.timer_exact = True
        self.initial_duration = 0

        self.container = ctk.CTkScrollableFrame(self, fg_color="transparent")
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
            # 오늘 게임 차단 중이었으면 재시작/재부팅 후에도 이어서 차단
            game_block = utils.load_game_block()
            saved_state = utils.load_timer_state()
            if game_block:
                self.timer_target = game_block["target"]
                self.timer_exact = game_block.get("exact", True)
                self._start_game_block(self.timer_target, self.timer_exact)
            # 저장된 타이머 상태가 있으면 자동 복원
            elif saved_state:
                self._resume_timer(saved_state)
            else:
                self.show_dashboard()

        # 사용 금지 시간대 감시 (타이머 실행 여부와 관계없이 동작)
        self.after(CURFEW_FIRST_CHECK_MS, self._check_curfew)

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

        # 상단: 제목 + 통계/설정 아이콘 버튼
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(header, text=languages.get_text("game_time_settings", self.current_lang),
                     font=("Arial", 20, "bold")).pack(side="left")
        self._icon_button(header, "⚙", self._open_settings).pack(side="right")
        self._icon_button(header, "📊", self.show_statistics).pack(side="right", padx=(0, 6))

        self._build_status_card()

        # 모드 탭 (기본 높이 250은 너무 커서 내용에 맞게 줄임)
        self.tab_view = ctk.CTkTabview(self.container, height=168, fg_color=CARD_COLOR)
        self.tab_view.pack(fill="x", pady=(4, 0))

        self.tab_game = self.tab_view.add(languages.get_text("tab_game", self.current_lang))
        self.tab_duration = self.tab_view.add(languages.get_text("tab_countdown", self.current_lang))
        self.tab_schedule = self.tab_view.add(languages.get_text("tab_schedule", self.current_lang))

        # 카운트다운
        self.hour_entry, self.min_entry = self._make_hm_row(self.tab_duration, "hours", "minutes", "0", "0")
        self.hour_entry.master.pack(pady=(24, 0))

        # 특정 시간
        self.target_hour_entry, self.target_min_entry = self._make_hm_row(
            self.tab_schedule, "hour", "minute", "22", languages.get_text("minute", self.current_lang))
        schedule_row = self.target_hour_entry.master
        schedule_row.pack(pady=(10, 0))
        ctk.CTkButton(schedule_row, text="🕐", width=36, command=self.open_time_picker).pack(side="left", padx=(10, 0))
        ctk.CTkLabel(self.tab_schedule, text=languages.get_text("schedule_note", self.current_lang),
                     font=("Arial", 12), text_color="gray").pack(pady=(8, 0))

        # 특정 게임
        self.game_hour_entry, self.game_min_entry = self._make_hm_row(self.tab_game, "hours", "minutes", "0", "0")
        self.game_hour_entry.master.pack(pady=(6, 0))
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
        self.game_name_combobox = ctk.CTkComboBox(self.tab_game, values=presets, width=280)
        self.game_name_combobox.set("Roblox (RobloxPlayerBeta)")
        self.game_name_combobox.pack(pady=(8, 0))
        ctk.CTkLabel(self.tab_game, text=languages.get_text("game_note", self.current_lang),
                     font=("Arial", 12), text_color="gray").pack(pady=(4, 0))

        # 시간 종료 후 동작: 라디오 4개 대신 한 줄 드롭다운
        action_row = ctk.CTkFrame(self.container, fg_color="transparent")
        action_row.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(action_row, text=languages.get_text("action_after_time", self.current_lang)).pack(side="left")
        self._action_labels = {key: languages.get_text(label_key, self.current_lang) for key, label_key in ACTIONS}
        self.action_menu = ctk.CTkOptionMenu(action_row, values=list(self._action_labels.values()), width=190,
                                             command=self._on_action_selected)
        self.action_menu.pack(side="right")
        self._sync_action_menu()

        ctk.CTkButton(self.container, text=languages.get_text("start_timer", self.current_lang), command=self.start_timer,
                      fg_color="green", hover_color="#1E7B34", height=46, font=("Arial", 16, "bold")).pack(pady=(18, 0), fill="x")

        self.load_saved_settings()

    def _icon_button(self, parent, text, command):
        return ctk.CTkButton(parent, text=text, width=36, height=32, font=("Arial", 16), command=command,
                             fg_color="transparent", hover_color=("gray80", "gray30"), text_color=("gray10", "gray90"))

    def _make_hm_row(self, parent, h_key, m_key, h_placeholder, m_placeholder):
        """[시] 시간 [분] 분 입력 줄을 만들고 두 입력칸을 반환합니다 (줄 배치는 호출하는 쪽에서)."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        h_entry = ctk.CTkEntry(row, width=60, placeholder_text=h_placeholder)
        h_entry.pack(side="left", padx=5)
        ctk.CTkLabel(row, text=languages.get_text(h_key, self.current_lang)).pack(side="left")
        m_entry = ctk.CTkEntry(row, width=60, placeholder_text=m_placeholder)
        m_entry.pack(side="left", padx=5)
        ctk.CTkLabel(row, text=languages.get_text(m_key, self.current_lang)).pack(side="left")
        return h_entry, m_entry

    def _build_status_card(self):
        """오늘 남은 허용 시간과 사용 금지 시간대를 한눈에 보여 주는 요약."""
        card = ctk.CTkFrame(self.container, corner_radius=10, fg_color=CARD_COLOR)
        card.pack(fill="x", pady=(0, 4))
        daily_remaining = utils.get_daily_remaining()
        if daily_remaining >= 0:
            text = languages.get_text("daily_remaining", self.current_lang).format(
                time=languages.format_hm(daily_remaining, self.current_lang))
            color = "#3B8ED0" if daily_remaining > 0 else "#FF5555"
        else:
            text, color = languages.get_text("status_no_limit", self.current_lang), "gray"
        self.daily_remaining_label = ctk.CTkLabel(card, text="⏱  " + text, text_color=color, font=("Arial", 13, "bold"))
        self.daily_remaining_label.pack(anchor="w", padx=12, pady=8)
        curfew = utils.load_curfew()
        if curfew["enabled"]:
            self.daily_remaining_label.pack_configure(pady=(8, 0))
            ctk.CTkLabel(card, text="🌙  " + languages.get_text("status_curfew", self.current_lang).format(
                start=curfew["start"], end=curfew["end"]), font=("Arial", 12), text_color="gray").pack(anchor="w", padx=12, pady=(0, 8))

    def _on_action_selected(self, label):
        for key, text in self._action_labels.items():
            if text == label:
                self.action_var.set(key)

    def _sync_action_menu(self):
        menu = getattr(self, "action_menu", None)
        if menu is not None and menu.winfo_exists():
            menu.set(self._action_labels.get(self.action_var.get(), self._action_labels["shutdown"]))

    def show_settings(self):
        """사용 제한·금지 시간대·일반 설정 화면. 값 변경은 각각 비밀번호 확인 후 저장됩니다."""
        self.clear_container()

        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        self._icon_button(header, "←", self.show_dashboard).pack(side="left")
        ctk.CTkLabel(header, text=languages.get_text("settings", self.current_lang), font=("Arial", 20, "bold")).pack(side="left", padx=6)

        # 일일 사용 제한
        daily_frame = self._section(languages.get_text("daily_limit", self.current_lang))
        self.daily_limit_var = ctk.BooleanVar(value=utils.load_daily_limit() > 0)
        ctk.CTkCheckBox(daily_frame, text=languages.get_text("daily_limit_enable", self.current_lang),
                        variable=self.daily_limit_var, command=self._on_daily_limit_toggled).pack(anchor="w", padx=12, pady=2)
        weekend_limit = utils.load_weekend_limit()
        self.weekday_label, self.daily_h_entry, self.daily_m_entry = self._make_limit_row(daily_frame, utils.load_daily_limit())
        self.weekend_var = ctk.BooleanVar(value=weekend_limit > 0)
        self.weekend_checkbox = ctk.CTkCheckBox(daily_frame, text=languages.get_text("weekend_separate", self.current_lang),
                                                variable=self.weekend_var, command=self._on_weekend_toggled)
        self.weekend_checkbox.pack(anchor="w", padx=12, pady=2)
        self.weekend_label, self.weekend_h_entry, self.weekend_m_entry = self._make_limit_row(daily_frame, weekend_limit)
        self.weekend_label.configure(text=languages.get_text("weekend", self.current_lang))
        self.limit_save_btn = ctk.CTkButton(daily_frame, text=languages.get_text("save", self.current_lang), width=70,
                                            command=self._on_limit_save)
        self.limit_save_btn.pack(anchor="e", padx=12, pady=(2, 10))
        self._apply_daily_limit_state()

        # 사용 금지 시간대
        curfew = utils.load_curfew()
        curfew_frame = self._section(languages.get_text("curfew", self.current_lang))
        self.curfew_var = ctk.BooleanVar(value=curfew["enabled"])
        ctk.CTkCheckBox(curfew_frame, text=languages.get_text("curfew_enable", self.current_lang),
                        variable=self.curfew_var, command=self._on_curfew_toggled).pack(anchor="w", padx=12, pady=2)
        curfew_row = ctk.CTkFrame(curfew_frame, fg_color="transparent")
        curfew_row.pack(fill="x", padx=12, pady=5)
        self.curfew_start_entry = ctk.CTkEntry(curfew_row, width=70, placeholder_text="21:00")
        self.curfew_start_entry.insert(0, curfew["start"])
        self.curfew_start_entry.pack(side="left")
        ctk.CTkLabel(curfew_row, text="~").pack(side="left", padx=6)
        self.curfew_end_entry = ctk.CTkEntry(curfew_row, width=70, placeholder_text="07:00")
        self.curfew_end_entry.insert(0, curfew["end"])
        self.curfew_end_entry.pack(side="left")
        self.curfew_save_btn = ctk.CTkButton(curfew_row, text=languages.get_text("save", self.current_lang), width=70, command=self._on_curfew_save)
        self.curfew_save_btn.pack(side="right")
        ctk.CTkLabel(curfew_frame, text=languages.get_text("curfew_note", self.current_lang), font=("Arial", 11),
                     text_color="gray", wraplength=330, justify="left").pack(anchor="w", padx=12, pady=(0, 10))
        self._apply_curfew_state()

        # 일반: 언어·테마, 비밀번호 변경, 만든이 소개
        general = self._section(languages.get_text("general", self.current_lang))
        prefs = ctk.CTkFrame(general, fg_color="transparent")
        prefs.pack(fill="x", padx=12, pady=(2, 6))
        ctk.CTkLabel(prefs, text="🌐").pack(side="left")
        self.lang_var = ctk.StringVar(value=self.current_lang)
        ctk.CTkOptionMenu(prefs, variable=self.lang_var, values=["ko", "en"], command=self.change_language, width=80).pack(side="left", padx=(4, 16))
        ctk.CTkLabel(prefs, text="🎨").pack(side="left")
        self.theme_var = ctk.StringVar(value=utils.load_theme())
        ctk.CTkOptionMenu(prefs, variable=self.theme_var, values=["Dark", "Light"], command=self.change_theme, width=90).pack(side="left", padx=4)
        buttons = ctk.CTkFrame(general, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(buttons, text=languages.get_text("password_change", self.current_lang), command=self.change_password_dialog,
                      fg_color="gray").pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(buttons, text=languages.get_text("about", self.current_lang), command=self.show_about_dialog,
                      fg_color="gray").pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _section(self, title):
        frame = ctk.CTkFrame(self.container, corner_radius=10, fg_color=CARD_COLOR)
        frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=("Arial", 13, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        return frame

    def _make_limit_row(self, parent, seconds):
        """[라벨] [시간] 시간 [분] 분 형태의 입력 줄을 만들고 (라벨, 시간 입력, 분 입력)을 반환합니다."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", padx=12, pady=3)
        label = ctk.CTkLabel(row, text="", width=40)
        label.pack(side="left", padx=(0, 5))
        h, m = divmod(seconds // 60, 60) if seconds > 0 else (0, 0)
        entries = []
        for value, unit_key in ((h, "daily_limit_hours"), (m, "daily_limit_minutes")):
            entry = ctk.CTkEntry(row, width=50, placeholder_text="0")
            entry.pack(side="left", padx=3)
            if value > 0:
                entry.insert(0, str(value))
            ctk.CTkLabel(row, text=languages.get_text(unit_key, self.current_lang)).pack(side="left")
            entries.append(entry)
        return label, entries[0], entries[1]

    def _apply_daily_limit_state(self):
        """일일 제한/주말 체크박스 상태에 따라 입력 필드를 활성화/비활성화합니다."""
        enabled = self.daily_limit_var.get()
        weekend = enabled and self.weekend_var.get()
        state = "normal" if enabled else "disabled"
        self.daily_h_entry.configure(state=state)
        self.daily_m_entry.configure(state=state)
        self.weekend_checkbox.configure(state=state)
        weekend_state = "normal" if weekend else "disabled"
        self.weekend_h_entry.configure(state=weekend_state)
        self.weekend_m_entry.configure(state=weekend_state)
        self.limit_save_btn.configure(state=state)
        # 주말을 따로 설정할 때만 첫 줄에 '평일' 표시
        self.weekday_label.configure(text=languages.get_text("weekday", self.current_lang) if weekend else "")

    def _verify_password(self):
        """비밀번호를 물어 맞으면 True. 틀리면 오류를 표시합니다."""
        dialog = PasswordDialog(self, title=languages.get_text("password_confirm", self.current_lang), text=languages.get_text("password_enter", self.current_lang))
        pw = dialog.get_input()
        if pw and utils.check_password(pw):
            return True
        if pw is not None:
            WarningDialog(self, languages.get_text("password_incorrect", self.current_lang), title_key="error")
        return False

    def _apply_curfew_state(self):
        state = "normal" if self.curfew_var.get() else "disabled"
        for widget in (self.curfew_start_entry, self.curfew_end_entry, self.curfew_save_btn):
            widget.configure(state=state)

    def _read_curfew_entries(self):
        """입력한 시작/끝 시각을 'HH:MM'으로 정규화합니다. 잘못되었으면 오류 표시 후 None."""
        try:
            times = [utils.parse_hhmm(entry.get()) for entry in (self.curfew_start_entry, self.curfew_end_entry)]
        except ValueError:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("enter_valid_time", self.current_lang))
            return None
        if times[0] == times[1]:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("curfew_same_time", self.current_lang))
            return None
        return tuple(f"{h:02d}:{m:02d}" for h, m in times)

    def _on_curfew_toggled(self):
        """사용 금지 시간대 켜기/끄기는 비밀번호 확인 후에만 저장합니다."""
        enabled = self.curfew_var.get()
        times = self._read_curfew_entries() if enabled else (self.curfew_start_entry.get(), self.curfew_end_entry.get())
        if times is None or not self._verify_password():
            self.curfew_var.set(not enabled)
            return
        utils.save_curfew(enabled, *times)
        self._apply_curfew_state()

    def _on_curfew_save(self):
        times = self._read_curfew_entries()
        if times and self._verify_password():
            utils.save_curfew(True, *times)
            WarningDialog(self, languages.get_text("curfew_saved", self.current_lang).format(start=times[0], end=times[1]),
                          title_key="curfew", color="#3B8ED0")

    @staticmethod
    def _read_limit_entries(h_entry, m_entry):
        h = int(h_entry.get() or 0)
        m = int(m_entry.get() or 0)
        return (h * 3600) + (m * 60)

    def _read_daily_limit_entries(self):
        return self._read_limit_entries(self.daily_h_entry, self.daily_m_entry)

    def _on_weekend_toggled(self):
        """주말 별도 제한 켜기/끄기도 비밀번호 확인 후에만 저장합니다."""
        enabled = self.weekend_var.get()
        if not self._verify_password():
            self.weekend_var.set(not enabled)
            return
        self._apply_daily_limit_state()
        if enabled:
            try:
                total = self._read_limit_entries(self.weekend_h_entry, self.weekend_m_entry)
                if total > 0:
                    utils.save_weekend_limit(total)
            except ValueError:
                pass
        else:
            utils.save_weekend_limit(0)

    def _on_limit_save(self):
        """바꾼 평일/주말 제한 시간을 비밀번호 한 번 확인 후 저장합니다."""
        try:
            changes = []
            limit_seconds = self._read_daily_limit_entries()
            if limit_seconds > 0 and limit_seconds != utils.load_daily_limit():
                changes.append((utils.save_daily_limit, limit_seconds))
            if self.weekend_var.get():
                weekend_seconds = self._read_limit_entries(self.weekend_h_entry, self.weekend_m_entry)
                if weekend_seconds > 0 and weekend_seconds != utils.load_weekend_limit():
                    changes.append((utils.save_weekend_limit, weekend_seconds))
        except ValueError:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("enter_valid_time", self.current_lang))
            return
        if not changes or not self._verify_password():
            return
        for save, seconds in changes:
            save(seconds)
        WarningDialog(self, languages.get_text("limit_saved", self.current_lang), title_key="daily_limit", color="#3B8ED0")

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
        self.show_settings()

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
            
            if "action" in settings:
                self.action_var.set(settings["action"])
                self._sync_action_menu()
            
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
        stats_window.open_statistics(self)

    def _form_settings(self):
        """메인 화면에 입력한 값 (다시 그려도 유지되도록 설정 파일에 저장하는 항목)."""
        return {
            "last_tab_key": self._current_tab_key(),
            "action": self.action_var.get(),
            "game_h": self.game_hour_entry.get(),
            "game_m": self.game_min_entry.get(),
            "game_name": self.game_name_combobox.get(),
            "duration_h": self.hour_entry.get(),
            "duration_m": self.min_entry.get(),
            "schedule_h": self.target_hour_entry.get(),
            "schedule_m": self.target_min_entry.get()
        }

    def _open_settings(self):
        # 설정 화면에서 돌아오면 메인 화면을 다시 그리므로 입력하던 값을 먼저 저장
        utils.save_settings(dict(utils.load_settings(), **self._form_settings()))
        self.show_settings()

    def start_timer(self):
        total_seconds = 0
        process_name = None
        exact = True
        end_at = None

        try:
            tab_key = self._current_tab_key()

            # Save settings first (without losing the paused keys yet)
            settings = self._form_settings()

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

        window = utils.curfew_window()
        if window and not (self._curfew_override_until and datetime.now() < self._curfew_override_until):
            curfew = utils.load_curfew()
            messagebox.showerror(languages.get_text("error", self.current_lang),
                                 languages.get_text("curfew_now", self.current_lang).format(start=curfew["start"], end=curfew["end"]))
            return

        if self.action_var.get() == "kill_game" and not process_name:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("kill_game_needs_game_tab", self.current_lang))
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
            cap_str = languages.format_hm(total_seconds, self.current_lang)
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
        elif action == "kill_game":
            utils.save_game_block(self.timer_target, self.timer_exact)
            self._start_game_block(self.timer_target, self.timer_exact)

    def _start_game_block(self, target, exact):
        """게임을 종료하고, 그날은 다시 실행해도 비밀번호로 중지할 때까지 계속 종료합니다."""
        self._stop_game_block()
        stop_event = threading.Event()
        self._game_block_job = stop_event
        block_date = datetime.now().date()

        def loop():
            while not stop_event.is_set():
                if datetime.now().date() != block_date:
                    # 날짜가 바뀌면 차단 해제
                    utils.clear_game_block()
                    stop_event.set()
                    self.after(0, self._on_game_block_expired, stop_event)
                    return
                timer_logic.kill_process(target, exact)
                stop_event.wait(GAME_BLOCK_INTERVAL)

        threading.Thread(target=loop, daemon=True).start()
        self.after(0, self.show_blocked_screen, target)

    def _stop_game_block(self):
        if self._game_block_job:
            self._game_block_job.set()
            self._game_block_job = None

    def _on_game_block_expired(self, job):
        if self._game_block_job is job:
            self._game_block_job = None
            self.show_dashboard()

    def _check_curfew(self):
        try:
            self._curfew_tick()
        except Exception as e:
            print(f"Error checking curfew: {e}")
        finally:
            self.after(CURFEW_CHECK_MS, self._check_curfew)

    def _curfew_tick(self, now=None):
        if not utils.is_password_set():
            return
        now = now or datetime.now()
        curfew = utils.load_curfew()
        window = utils.curfew_window(curfew, now)
        if window is None:
            self._warn_before_curfew(curfew, now)
            return
        start, end = window
        if self._curfew_override_until and now < self._curfew_override_until:
            return
        if self._curfew_enforced_start == start:
            return  # 이번 구간은 이미 동작 실행됨 (재잠금 등은 계속 진행 중)
        self._curfew_enforced_start = start
        self._enforce_curfew(curfew)

    def _warn_before_curfew(self, curfew, now):
        next_start = utils.next_curfew_start(curfew, now)
        if next_start is None:
            return
        until = (next_start - now).total_seconds()
        due = [t for t in CURFEW_WARNINGS if until <= t and (next_start, t) not in self._curfew_warned]
        if not due:
            return
        # 앱을 늦게 켠 경우 지나간 경고를 한꺼번에 띄우지 않고 가장 가까운 것 하나만 표시
        for t in CURFEW_WARNINGS:
            if until <= t:
                self._curfew_warned.add((next_start, t))
        minutes = max(1, round(until / 60))
        self._restore_window_main_thread()
        WarningDialog(self, languages.get_text("curfew_warning", self.current_lang).format(
            minutes=minutes, start=curfew["start"]))

    def _enforce_curfew(self, curfew):
        """사용 금지 시간대가 시작됨: 실행 중인 타이머를 멈추고 유예 경고 후 종료 동작을 실행합니다."""
        if self.timer and self.timer.running:
            used_seconds = self.initial_duration - self.timer.remaining
            if used_seconds > 0:
                utils.save_log(used_seconds, self.timer_type, self.timer_target)
            self.timer.stop()
        self.timer = None
        utils.clear_timer_state()

        action = utils.load_settings().get("action", self.action_var.get())
        if action == "kill_game":
            action = "lock"  # 금지 시간대는 게임이 아니라 PC 사용 자체를 막음
        self._timer_action = action
        self.show_curfew_screen(curfew)
        self._arm_expire_action(action)
        self._show_grace_warning()

    def show_curfew_screen(self, curfew):
        self.clear_container()
        ctk.CTkLabel(self.container, text="🌙", font=("Arial", 48)).pack(pady=(40, 10))
        ctk.CTkLabel(self.container, text=languages.get_text("curfew_active", self.current_lang).format(
            start=curfew["start"], end=curfew["end"]),
            font=("Arial", 16, "bold"), text_color="#FF5555", wraplength=320).pack(pady=20)
        ctk.CTkButton(self.container, text=languages.get_text("stop_timer", self.current_lang), command=self.prompt_stop_timer, fg_color="red").pack(pady=40, fill="x")

    def show_blocked_screen(self, target):
        self.clear_container()
        ctk.CTkLabel(self.container, text="🚫", font=("Arial", 48)).pack(pady=(40, 10))
        ctk.CTkLabel(self.container, text=languages.get_text("game_blocked", self.current_lang).format(game=target),
                     font=("Arial", 16, "bold"), text_color="#FF5555", wraplength=320).pack(pady=20)
        ctk.CTkButton(self.container, text=languages.get_text("stop_timer", self.current_lang), command=self.prompt_stop_timer, fg_color="red").pack(pady=40, fill="x")

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
        if self._game_block_job:
            self._stop_game_block()
            utils.clear_game_block()
        self._action_done = True
        system_control.cancel_shutdown()  # 예약된 종료가 있으면 취소
        if self.grace_dialog:
            self.grace_dialog.cancel_dialog()
            self.grace_dialog = None

    def _is_enforcing(self):
        return bool((self.timer and self.timer.running) or self.grace_dialog is not None
                    or self._relock_job or self._game_block_job)

    def _quit_needs_password(self):
        # 금지 시간대는 앱이 켜져 있어야 적용되므로, 켜져 있으면 타이머가 없어도 종료를 막음
        return self._is_enforcing() or utils.load_curfew().get("enabled", False)

    def _show_grace_warning(self):
        """유예 경고를 표시합니다. (동작 자체는 _arm_expire_action에서 이미 예약됨)"""
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)

        action = self._timer_action

        # Close any existing grace dialog just in case
        if self.grace_dialog:
            try:
                close_window(self.grace_dialog)
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

        # 금지 시간대 중에 비밀번호로 중지했다면 이번 구간이 끝날 때까지는 다시 막지 않음
        window = utils.curfew_window()
        if window:
            self._curfew_override_until = window[1]

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
        if self._quit_needs_password():
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
        if self._quit_needs_password():
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
