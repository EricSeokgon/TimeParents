import customtkinter as ctk
from tkinter import messagebox
import utils
import system_control
from timer_logic import GameTimer, ProcessTimer
import sys
from datetime import datetime, timedelta
import webbrowser
import languages

VERSION = "1.0.1"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

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
        self.geometry("400x750")
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

    def show_login(self):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text=languages.get_text("login", self.current_lang), font=("Arial", 24, "bold")).pack(pady=40)
        
        self.login_pw_entry = ctk.CTkEntry(self.container, show="*", placeholder_text=languages.get_text("password_input", self.current_lang))
        self.login_pw_entry.pack(pady=20, fill="x")
        self.login_pw_entry.bind("<Return>", lambda e: self.login())

        ctk.CTkButton(self.container, text=languages.get_text("login", self.current_lang), command=self.login).pack(pady=20, fill="x")

    def login(self):
        pw = self.login_pw_entry.get()
        if utils.check_password(pw):
            self.show_dashboard()
        else:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("password_incorrect", self.current_lang))

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
        self.game_name_entry = ctk.CTkEntry(self.tab_game, placeholder_text=languages.get_text("process_name_placeholder", self.current_lang))
        self.game_name_entry.insert(0, "Roblox")
        self.game_name_entry.pack(pady=10)
        
        ctk.CTkLabel(self.tab_game, text=languages.get_text("game_note", self.current_lang), font=("Arial", 12), text_color="gray").pack()

        # Action Selection
        ctk.CTkLabel(self.container, text=languages.get_text("action_after_time", self.current_lang)).pack(pady=(10, 5))
        ctk.CTkRadioButton(self.container, text=languages.get_text("shutdown", self.current_lang), variable=self.action_var, value="shutdown").pack(pady=5)
        ctk.CTkRadioButton(self.container, text=languages.get_text("logoff", self.current_lang), variable=self.action_var, value="logoff").pack(pady=5)

        ctk.CTkButton(self.container, text=languages.get_text("start_timer", self.current_lang), command=self.start_timer, fg_color="green").pack(pady=20, fill="x")
        
        ctk.CTkButton(self.container, text=languages.get_text("password_change", self.current_lang), command=self.change_password_dialog, fg_color="gray").pack(pady=5, fill="x")
        ctk.CTkButton(self.container, text=languages.get_text("about", self.current_lang), command=self.show_about_dialog, fg_color="gray").pack(pady=5, fill="x")
        ctk.CTkButton(self.container, text=languages.get_text("statistics", self.current_lang), command=self.show_statistics, fg_color="#3B8ED0").pack(pady=5, fill="x")
        
        # Language Switcher
        lang_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        lang_frame.pack(pady=5, fill="x")
        
        ctk.CTkLabel(lang_frame, text="🌐 " + languages.get_text("language", self.current_lang), width=60).pack(side="left", padx=5)
        
        self.lang_var = ctk.StringVar(value=self.current_lang)
        lang_menu = ctk.CTkOptionMenu(lang_frame, variable=self.lang_var, 
                                      values=["ko", "en"],
                                      command=self.change_language)
        lang_menu.pack(side="right", padx=5, fill="x", expand=True)

        self.load_saved_settings()

    def change_language(self, choice):
        utils.save_language(choice)
        self.current_lang = choice
        self.title(f"{languages.get_text('app_title', self.current_lang)} v{VERSION}")
        self.show_dashboard()

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
        # Password check (optional, but good for privacy)
        dialog = PasswordDialog(self, title=languages.get_text("admin_confirm", self.current_lang), text=languages.get_text("password_enter", self.current_lang))
        pw = dialog.get_input()
        if not pw or not utils.check_password(pw):
            if pw is not None:
                messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("password_mismatch", self.current_lang))
            return

        stats_window = ctk.CTkToplevel(self)
        stats_window.title(languages.get_text("stats_title", self.current_lang))
        stats_window.geometry("400x650")
        
        # Center
        stats_window.transient(self)
        stats_window.grab_set()
        
        # Today's Total
        today_seconds = utils.get_today_total()
        h, m = divmod(today_seconds // 60, 60)
        today_str = f"{h}{languages.get_text('hour', self.current_lang)} {m}{languages.get_text('minute', self.current_lang)}"
        
        ctk.CTkLabel(stats_window, text=languages.get_text("today_total", self.current_lang), font=("Arial", 16, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(stats_window, text=today_str, font=("Arial", 24, "bold"), text_color="#3B8ED0").pack(pady=(0, 20))
        
        # Weekly Stats
        ctk.CTkLabel(stats_window, text=languages.get_text("weekly_stats", self.current_lang), font=("Arial", 14, "bold")).pack(pady=(10, 5), anchor="w", padx=20)
        
        weekly_frame = ctk.CTkFrame(stats_window)
        weekly_frame.pack(pady=5, padx=20, fill="x")
        
        weekly_data = utils.get_weekly_stats()
        max_seconds = max([s for _, s in weekly_data]) if any(s for _, s in weekly_data) else 1
        
        day_keys = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        
        for i, (day_name, seconds) in enumerate(weekly_data):
            day_frame = ctk.CTkFrame(weekly_frame, fg_color="transparent")
            day_frame.pack(fill="x", pady=2)
            
            # Day name (translated)
            translated_day = languages.get_text(day_keys[i], self.current_lang)
            ctk.CTkLabel(day_frame, text=translated_day, width=60, anchor="w").pack(side="left", padx=5)
            
            # Bar visualization
            bar_width = int((seconds / max_seconds) * 200) if max_seconds > 0 else 0
            bar_frame = ctk.CTkFrame(day_frame, width=bar_width, height=20, fg_color="#3B8ED0")
            bar_frame.pack(side="left", padx=5)
            bar_frame.pack_propagate(False)
            
            # Time display
            h, m = divmod(seconds // 60, 60)
            time_str = f"{h}h {m}m" if h > 0 else f"{m}m"
            ctk.CTkLabel(day_frame, text=time_str, width=60, anchor="w").pack(side="left", padx=5)
        
        # Logs List
        ctk.CTkLabel(stats_window, text=languages.get_text("recent_logs", self.current_lang), font=("Arial", 14)).pack(pady=5, anchor="w", padx=20)
        
        scroll_frame = ctk.CTkScrollableFrame(stats_window, width=360, height=300)
        scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        logs = utils.load_logs()
        if not logs:
            ctk.CTkLabel(scroll_frame, text=languages.get_text("no_logs", self.current_lang)).pack(pady=20)
        else:
            for log in reversed(logs): # Show newest first
                frame = ctk.CTkFrame(scroll_frame)
                frame.pack(fill="x", pady=2)
                
                # Format: [Time] Type (Duration)
                # 2023-11-29 18:00 | Game (Roblox) | 1h 30m
                
                ts = log["timestamp"][5:-3] # MM-DD HH:MM
                duration = log["duration"]
                dh, dm = divmod(duration // 60, 60)
                dur_str = f"{dh}{languages.get_text('hour', self.current_lang)} {dm}{languages.get_text('minute', self.current_lang)}" if dh > 0 else f"{dm}{languages.get_text('minute', self.current_lang)}"
                
                type_map = {
                    "game": languages.get_text("type_game", self.current_lang), 
                    "countdown": languages.get_text("type_countdown", self.current_lang), 
                    "schedule": languages.get_text("type_schedule", self.current_lang)
                }
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
            
            if current_tab == languages.get_text("tab_countdown", self.current_lang):
                h = int(self.hour_entry.get() or 0)
                m = int(self.min_entry.get() or 0)
                total_seconds = (h * 60 + m) * 60

            elif current_tab == languages.get_text("tab_game", self.current_lang):
                h = int(self.game_hour_entry.get() or 0)
                m = int(self.game_min_entry.get() or 0)
                total_seconds = (h * 60 + m) * 60
                process_name = self.game_name_entry.get()
                if not process_name:
                    messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("enter_game_name", self.current_lang))
                    return
                
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

        except ValueError:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("enter_valid_time", self.current_lang))
            return

        if total_seconds <= 0:
            messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("min_time_1min", self.current_lang))
            return

        self.initial_duration = total_seconds
        self.timer_type = "game" if process_name else ("schedule" if current_tab == languages.get_text("tab_schedule", self.current_lang) else "countdown")
        self.timer_target = process_name

        if process_name:
            self.timer = ProcessTimer(total_seconds, process_name, self.update_timer_display, self.on_timer_finish, self.on_warning)
        else:
            self.timer = GameTimer(total_seconds, self.update_timer_display, self.on_timer_finish, self.on_warning)
        self.timer.start()
        self.show_timer_screen()

    def show_timer_screen(self):
        self.clear_container()
        
        ctk.CTkLabel(self.container, text=languages.get_text("remaining_time", self.current_lang), font=("Arial", 20)).pack(pady=(40, 10))
        
        self.time_label = ctk.CTkLabel(self.container, text="00:00:00", font=("Arial", 48, "bold"), text_color="#FF5555")
        self.time_label.pack(pady=20)

        ctk.CTkButton(self.container, text=languages.get_text("stop_timer", self.current_lang), command=self.prompt_stop_timer, fg_color="red").pack(pady=40, fill="x")
        
        # Mini mode hint
        ctk.CTkLabel(self.container, text=languages.get_text("timer_running_note", self.current_lang), font=("Arial", 12), text_color="gray").pack(side="bottom", pady=10)

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
        msg = languages.get_text("time_warning", self.current_lang).format(minutes=minutes)
        messagebox.showwarning(languages.get_text("warning", self.current_lang), msg)

    def on_timer_finish(self):
        # Save log
        utils.save_log(self.initial_duration, self.timer_type, self.timer_target)
        
        action = self.action_var.get()
        if action == "shutdown":
            system_control.shutdown_system()
        elif action == "logoff":
            system_control.logoff_system()

    def prompt_stop_timer(self):
        dialog = PasswordDialog(self, title=languages.get_text("password_confirm", self.current_lang), text=languages.get_text("password_enter", self.current_lang))
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
                messagebox.showerror(languages.get_text("error", self.current_lang), languages.get_text("password_mismatch", self.current_lang))

    def on_closing(self):
        if self.timer and self.timer.running:
            if messagebox.askokcancel(languages.get_text("close", self.current_lang), languages.get_text("timer_running_confirm", self.current_lang)):
                self.prompt_stop_timer()
        else:
            self.destroy()

if __name__ == "__main__":
    app = GameTimerApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
