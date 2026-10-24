import customtkinter as ctk
import languages
import utils


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
            
        lang = self.parent.current_lang
        msg = languages.get_text("grace_countdown", lang).format(
            seconds=self.remaining, action=languages.get_text(self.action, lang))
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
