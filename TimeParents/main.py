import customtkinter as ctk
from tkinter import messagebox
import utils
import system_control
from timer_logic import GameTimer, ProcessTimer
import sys
from datetime import datetime, timedelta
import webbrowser

VERSION = "1.0.1"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="비밀번호 입력", text="비밀번호를 입력하세요:"):
        super().__init__(parent)
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
        
        ctk.CTkButton(btn_frame, text="확인", command=self.ok_clicked, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="취소", command=self.cancel_clicked, width=100).pack(side="left", padx=5)
    
    def ok_clicked(self):
        self.result = self.pw_entry.get()
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

        self.title(f"타임페어런츠(TimeParents) v{VERSION}")
        self.geometry("400x650")
        self.resizable(False, False)

        self.timer = None
        self.action_var = ctk.StringVar(value="shutdown")

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True, padx=20, pady=20)

        if not utils.is_password_set():
            self.show_setup_password()
        else:
            self.show_login()

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def show_setup_password(self):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text="비밀번호 설정", font=("Arial", 24, "bold")).pack(pady=20)
        ctk.CTkLabel(self.container, text="초기 비밀번호를 설정해주세요.").pack(pady=10)

        self.pw_entry = ctk.CTkEntry(self.container, show="*", placeholder_text="비밀번호")
        self.pw_entry.pack(pady=10, fill="x")
        self.pw_entry.bind("<Return>", lambda e: self.pw_confirm.focus())
        
        self.pw_confirm = ctk.CTkEntry(self.container, show="*", placeholder_text="비밀번호 확인")
        self.pw_confirm.pack(pady=10, fill="x")
        self.pw_confirm.bind("<Return>", lambda e: self.set_password())

        ctk.CTkButton(self.container, text="설정 완료", command=self.set_password).pack(pady=20, fill="x")

    def set_password(self):
        pw = self.pw_entry.get()
        confirm = self.pw_confirm.get()

        if not pw:
            messagebox.showerror("오류", "비밀번호를 입력해주세요.")
            return
        if pw != confirm:
            messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")
            return

        utils.save_password(pw)
        messagebox.showinfo("성공", "비밀번호가 설정되었습니다.")
        self.show_dashboard()

    def show_login(self):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text="로그인", font=("Arial", 24, "bold")).pack(pady=40)
        
        self.login_pw_entry = ctk.CTkEntry(self.container, show="*", placeholder_text="비밀번호 입력")
        self.login_pw_entry.pack(pady=20, fill="x")
        self.login_pw_entry.bind("<Return>", lambda e: self.login())

        ctk.CTkButton(self.container, text="로그인", command=self.login).pack(pady=20, fill="x")

    def login(self):
        pw = self.login_pw_entry.get()
        if utils.check_password(pw):
            self.show_dashboard()
        else:
            messagebox.showerror("오류", "비밀번호가 올바르지 않습니다.")

    def show_dashboard(self):
        self.clear_container()

        ctk.CTkLabel(self.container, text="게임 시간 설정", font=("Arial", 24, "bold")).pack(pady=10)

        # Tab View
        self.tab_view = ctk.CTkTabview(self.container)
        self.tab_view.pack(pady=10, fill="x")
        
        self.tab_game = self.tab_view.add("특정 게임")
        self.tab_duration = self.tab_view.add("카운트다운")
        self.tab_schedule = self.tab_view.add("특정 시간")
        
        # Tab 1: Duration
        time_frame = ctk.CTkFrame(self.tab_duration, fg_color="transparent")
        time_frame.pack(pady=20)
        
        self.hour_entry = ctk.CTkEntry(time_frame, width=60, placeholder_text="0")
        self.hour_entry.pack(side="left", padx=5)
        ctk.CTkLabel(time_frame, text="시간").pack(side="left")
        
        self.min_entry = ctk.CTkEntry(time_frame, width=60, placeholder_text="0")
        self.min_entry.pack(side="left", padx=5)
        ctk.CTkLabel(time_frame, text="분").pack(side="left")

        # Tab 2: Schedule
        schedule_frame = ctk.CTkFrame(self.tab_schedule, fg_color="transparent")
        schedule_frame.pack(pady=20)
        
        self.target_hour_entry = ctk.CTkEntry(schedule_frame, width=60, placeholder_text="24시")
        self.target_hour_entry.pack(side="left", padx=5)
        ctk.CTkLabel(schedule_frame, text="시").pack(side="left")
        
        self.target_min_entry = ctk.CTkEntry(schedule_frame, width=60, placeholder_text="분")
        self.target_min_entry.pack(side="left", padx=5)
        ctk.CTkLabel(schedule_frame, text="분").pack(side="left")
        
        ctk.CTkLabel(self.tab_schedule, text="* 입력한 시간에 종료됩니다.", font=("Arial", 12), text_color="gray").pack()

        # Tab 3: Specific Game
        game_frame = ctk.CTkFrame(self.tab_game, fg_color="transparent")
        game_frame.pack(pady=20)

        self.game_hour_entry = ctk.CTkEntry(game_frame, width=60, placeholder_text="0")
        self.game_hour_entry.pack(side="left", padx=5)
        ctk.CTkLabel(game_frame, text="시간").pack(side="left")

        self.game_min_entry = ctk.CTkEntry(game_frame, width=60, placeholder_text="0")
        self.game_min_entry.pack(side="left", padx=5)
        ctk.CTkLabel(game_frame, text="분").pack(side="left")

        self.game_name_entry = ctk.CTkEntry(self.tab_game, placeholder_text="프로세스 이름 (예: Roblox)")
        self.game_name_entry.insert(0, "Roblox")
        self.game_name_entry.pack(pady=10)
        
        ctk.CTkLabel(self.tab_game, text="* 게임이 실행 중일 때만 시간이 차감됩니다.", font=("Arial", 12), text_color="gray").pack()

        # Action Selection
        ctk.CTkLabel(self.container, text="시간 종료 후 동작").pack(pady=(10, 5))
        ctk.CTkRadioButton(self.container, text="시스템 종료", variable=self.action_var, value="shutdown").pack(pady=5)
        ctk.CTkRadioButton(self.container, text="로그오프", variable=self.action_var, value="logoff").pack(pady=5)

        ctk.CTkButton(self.container, text="타이머 시작", command=self.start_timer, fg_color="green").pack(pady=20, fill="x")
        
        ctk.CTkButton(self.container, text="비밀번호 변경", command=self.change_password_dialog, fg_color="gray").pack(pady=5, fill="x")
        ctk.CTkButton(self.container, text="만든이 소개", command=self.show_about_dialog, fg_color="gray").pack(pady=5, fill="x")
        ctk.CTkButton(self.container, text="통계 보기", command=self.show_statistics, fg_color="#3B8ED0").pack(pady=5, fill="x")

        self.load_saved_settings()

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
                self.game_name_entry.delete(0, "end")
                self.game_name_entry.insert(0, settings["game_name"])
                
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
            
            if "last_tab" in settings:
                self.tab_view.set(settings["last_tab"])
        except Exception as e:
            print(f"Error loading settings: {e}")

    def change_password_dialog(self):
        dialog = PasswordDialog(self, title="비밀번호 변경", text="현재 비밀번호를 입력하세요:")
        current_pw = dialog.get_input()
        
        if current_pw and utils.check_password(current_pw):
            self.show_setup_password() # Re-use setup screen for new password
        else:
            if current_pw is not None:
                messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")

    def show_about_dialog(self):
        about_window = ctk.CTkToplevel(self)
        about_window.title("만든이 소개")
        about_window.geometry("300x350")
        about_window.resizable(False, False)
        
        # Center the dialog
        about_window.transient(self)
        about_window.grab_set()
        
        ctk.CTkLabel(about_window, text=f"타임페어런츠 v{VERSION}", font=("Arial", 18, "bold")).pack(pady=(30, 10))
        
        ctk.CTkLabel(about_window, text="제작자: HadesYI", font=("Arial", 14)).pack(pady=5)
        ctk.CTkLabel(about_window, text="Email : leesk55@gmail.com", font=("Arial", 14)).pack(pady=5)
        
        link = ctk.CTkLabel(about_window, text="https://hadesyi.tistory.com/", font=("Arial", 12), text_color="#3B8ED0", cursor="hand2")
        link.pack(pady=5)
        link.bind("<Button-1>", lambda e: webbrowser.open("https://hadesyi.tistory.com/"))
        
        ctk.CTkButton(about_window, text="확인", command=about_window.destroy, width=100).pack(pady=30)

    def show_statistics(self):
        # Password check (optional, but good for privacy)
        dialog = PasswordDialog(self, title="관리자 확인", text="비밀번호를 입력하세요:")
        pw = dialog.get_input()
        if not pw or not utils.check_password(pw):
            if pw is not None:
                messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")
            return

        stats_window = ctk.CTkToplevel(self)
        stats_window.title("사용 통계")
        stats_window.geometry("400x500")
        
        # Center
        stats_window.transient(self)
        stats_window.grab_set()
        
        # Today's Total
        today_seconds = utils.get_today_total()
        h, m = divmod(today_seconds // 60, 60)
        today_str = f"{h}시간 {m}분"
        
        ctk.CTkLabel(stats_window, text="오늘 총 사용 시간", font=("Arial", 16, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(stats_window, text=today_str, font=("Arial", 24, "bold"), text_color="#3B8ED0").pack(pady=(0, 20))
        
        # Logs List
        ctk.CTkLabel(stats_window, text="최근 사용 기록", font=("Arial", 14)).pack(pady=5, anchor="w", padx=20)
        
        scroll_frame = ctk.CTkScrollableFrame(stats_window, width=360, height=300)
        scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        logs = utils.load_logs()
        if not logs:
            ctk.CTkLabel(scroll_frame, text="기록이 없습니다.").pack(pady=20)
        else:
            for log in reversed(logs): # Show newest first
                frame = ctk.CTkFrame(scroll_frame)
                frame.pack(fill="x", pady=2)
                
                # Format: [Time] Type (Duration)
                # 2023-11-29 18:00 | Game (Roblox) | 1h 30m
                
                ts = log["timestamp"][5:-3] # MM-DD HH:MM
                duration = log["duration"]
                dh, dm = divmod(duration // 60, 60)
                dur_str = f"{dh}시간 {dm}분" if dh > 0 else f"{dm}분"
                
                type_map = {"game": "게임", "countdown": "카운트다운", "schedule": "스케줄"}
                type_str = type_map.get(log["type"], log["type"])
                if log.get("target"):
                    type_str += f" ({log['target']})"
                
                ctk.CTkLabel(frame, text=ts, width=80, anchor="w").pack(side="left", padx=5)
                ctk.CTkLabel(frame, text=type_str, anchor="w").pack(side="left", padx=5, expand=True, fill="x")
                ctk.CTkLabel(frame, text=dur_str, width=60, anchor="e").pack(side="right", padx=5)

    def start_timer(self):
        total_seconds = 0
        process_name = None
        
        try:
            current_tab = self.tab_view.get()
            
            # Save settings
            settings = {
                "last_tab": current_tab,
                "action": self.action_var.get(),
                "game_h": self.game_hour_entry.get(),
                "game_m": self.game_min_entry.get(),
                "game_name": self.game_name_entry.get(),
                "duration_h": self.hour_entry.get(),
                "duration_m": self.min_entry.get(),
                "schedule_h": self.target_hour_entry.get(),
                "schedule_m": self.target_min_entry.get()
            }
            utils.save_settings(settings)
            
            if current_tab == "카운트다운":
                h = int(self.hour_entry.get() or 0)
                m = int(self.min_entry.get() or 0)
                total_seconds = (h * 60 + m) * 60

            elif current_tab == "특정 게임":
                h = int(self.game_hour_entry.get() or 0)
                m = int(self.game_min_entry.get() or 0)
                total_seconds = (h * 60 + m) * 60
                process_name = self.game_name_entry.get()
                if not process_name:
                    messagebox.showerror("오류", "게임 이름을 입력해주세요.")
                    return
                
            else: # 특정 시간
                target_h = int(self.target_hour_entry.get())
                target_m = int(self.target_min_entry.get() or 0)
                
                if not (0 <= target_h <= 23 and 0 <= target_m <= 59):
                    raise ValueError("올바른 시간을 입력해주세요.")
                
                now = datetime.now()
                target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
                
                if target <= now:
                    target += timedelta(days=1)
                    
                total_seconds = int((target - now).total_seconds())

        except ValueError:
            messagebox.showerror("오류", "올바른 시간을 입력해주세요.")
            return

        if total_seconds <= 0:
            messagebox.showerror("오류", "시간을 1분 이상 설정해주세요.")
            return

        self.initial_duration = total_seconds
        self.timer_type = "game" if process_name else ("schedule" if current_tab == "특정 시간" else "countdown")
        self.timer_target = process_name

        if process_name:
            self.timer = ProcessTimer(total_seconds, process_name, self.update_timer_display, self.on_timer_finish, self.on_warning)
        else:
            self.timer = GameTimer(total_seconds, self.update_timer_display, self.on_timer_finish, self.on_warning)
        self.timer.start()
        self.show_timer_screen()

    def show_timer_screen(self):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text="남은 시간", font=("Arial", 20)).pack(pady=(40, 10))
        
        self.time_label = ctk.CTkLabel(self.container, text="00:00:00", font=("Arial", 48, "bold"), text_color="#FF5555")
        self.time_label.pack(pady=20)

        ctk.CTkButton(self.container, text="타이머 중지 / 변경", command=self.prompt_stop_timer, fg_color="red").pack(pady=40, fill="x")
        
        # Mini mode hint
        ctk.CTkLabel(self.container, text="* 창을 닫아도 타이머는 계속 작동합니다.", font=("Arial", 12), text_color="gray").pack(side="bottom", pady=10)

    def update_timer_display(self, time_str):
        self.time_label.configure(text=time_str)

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
        messagebox.showwarning("시간 경고", f"게임 시간이 {minutes}분 남았습니다!")

    def on_timer_finish(self):
        # Save log
        utils.save_log(self.initial_duration, self.timer_type, self.timer_target)
        
        action = self.action_var.get()
        if action == "shutdown":
            system_control.shutdown_system()
        elif action == "logoff":
            system_control.logoff_system()

    def prompt_stop_timer(self):
        dialog = PasswordDialog(self, title="비밀번호 확인", text="비밀번호를 입력하세요:")
        pw = dialog.get_input()
        
        if pw and utils.check_password(pw):
            if self.timer:
                # Calculate used time
                used_seconds = self.initial_duration - self.timer.remaining
                if used_seconds > 0:
                    utils.save_log(used_seconds, self.timer_type, self.timer_target)
                
                self.timer.stop()
            self.show_dashboard()
        else:
            if pw is not None: # Cancel returns None
                messagebox.showerror("오류", "비밀번호가 일치하지 않습니다.")

    def on_closing(self):
        if self.timer and self.timer.running:
            if messagebox.askokcancel("종료", "타이머가 작동 중입니다. 정말 종료하시겠습니까?\n(종료하려면 비밀번호가 필요합니다)"):
                self.prompt_stop_timer()
        else:
            self.destroy()

if __name__ == "__main__":
    app = GameTimerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
