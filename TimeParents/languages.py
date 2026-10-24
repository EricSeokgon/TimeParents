# Multi-language support for TimeParents

LANGUAGES = {
    "ko": {
        # App
        "app_title": "타임페어런츠(TimeParents)",
        "version": "v",
        
        # Login & Password
        "login": "로그인",
        "password_setup": "비밀번호 설정",
        "password_setup_msg": "초기 비밀번호를 설정해주세요.",
        "password": "비밀번호",
        "password_confirm": "비밀번호 확인",
        "password_input": "비밀번호 입력",
        "password_enter": "비밀번호를 입력하세요:",
        "password_change": "비밀번호 변경",
        "current_password": "현재 비밀번호를 입력하세요:",
        "setup_complete": "설정 완료",
        
        # Tabs
        "tab_game": "특정 게임",
        "tab_countdown": "카운트다운",
        "tab_schedule": "특정 시간",
        
        # Dashboard
        "game_time_settings": "게임 시간 설정",
        "hours": "시간",
        "minutes": "분",
        "hour": "시",
        "minute": "분",
        "dur_hour": "시간",
        "dur_minute": "분",
        "game_process_name": "게임 프로세스 이름",
        "process_name_placeholder": "프로세스 이름 (예: Roblox)",
        "schedule_note": "* 입력한 시간에 종료됩니다.",
        "game_note": "* 게임이 실행 중일 때만 시간이 차감됩니다.",
        
        # Actions
        "action_after_time": "시간 종료 후 동작",
        "shutdown": "시스템 종료",
        "logoff": "로그오프",
        "lock": "화면 잠금",
        "kill_game": "게임 종료",
        "kill_game_option": "게임만 종료 (특정 게임 모드)",
        "kill_game_needs_game_tab": "'게임만 종료'는 특정 게임 탭에서만 사용할 수 있습니다.",
        "game_blocked": "오늘 {game} 사용 시간이 끝났습니다.\n게임을 다시 실행해도 자동으로 종료됩니다.\n(내일 자동으로 해제됩니다)",
        "start_timer": "타이머 시작",
        "stop_timer": "타이머 중지 / 변경",
        "timer_running_note": "* 창을 닫아도 타이머는 계속 작동합니다.",
        "restore": "창 열기",
        "tray_running_msg": "TimeParents가 백그라운드(시스템 트레이)에서 계속 작동 중입니다.",
        
        # Buttons
        "about": "만든이 소개",
        "statistics": "통계 보기",
        "time_picker": "🕐 시간 선택",
        "confirm": "확인",
        "cancel": "취소",
        "ok": "확인",
        
        # Time Picker
        "time_picker_title": "시간 선택",
        "select_end_time": "종료 시간을 선택하세요",
        
        # Timer
        "remaining_time": "남은 시간",
        
        # Warnings & Errors
        "error": "오류",
        "success": "성공",
        "warning": "시간 경고",
        "time_warning": "게임 시간이 {minutes}분 남았습니다!",
        "password_set_success": "비밀번호가 설정되었습니다.",
        "password_empty": "비밀번호를 입력해주세요.",
        "password_mismatch": "비밀번호가 일치하지 않습니다.",
        "password_incorrect": "비밀번호가 올바르지 않습니다.",
        "enter_valid_time": "올바른 시간을 입력해주세요.",
        "enter_game_name": "게임 이름을 입력해주세요.",
        "min_time_1min": "시간을 1분 이상 설정해주세요.",
        "timer_running_confirm": "타이머가 작동 중입니다. 정말 종료하시겠습니까?\\n(종료하려면 비밀번호가 필요합니다)",
        "close": "종료",
        
        # About Dialog
        "about_title": "만든이 소개",
        "creator": "제작자: HadesYI",
        "email": "Email : leesk55@gmail.com",
        
        # Statistics
        "stats_title": "사용 통계",
        "admin_confirm": "관리자 확인",
        "today_total": "오늘 총 사용 시간",
        "weekly_stats": "이번 주 사용 통계",
        "recent_logs": "최근 사용 기록",
        "no_logs": "기록이 없습니다.",
        "daily_average": "일평균 사용 시간",
        "weekly_total": "이번 주 총 사용",
        "search_total": "검색 기간 총 사용",
        "search_tab": "기록 검색",
        "all": "전체",
        "search": "검색",
        "monday": "월요일",
        "tuesday": "화요일",
        "wednesday": "수요일",
        "thursday": "목요일",
        "friday": "금요일",
        "saturday": "토요일",
        "sunday": "일요일",
        
        # Log types
        "type_game": "게임",
        "type_countdown": "카운트다운",
        "type_schedule": "스케줄",
        
        # Language
        "language": "언어",
        "korean": "한국어",
        "english": "English",
        
        # Theme
        "theme": "테마",
        "dark_mode": "다크 모드",
        "light_mode": "라이트 모드",
        
        # Daily Limit
        "daily_limit": "일일 사용 제한",
        "daily_limit_hours": "시간",
        "daily_limit_minutes": "분",
        "daily_limit_enable": "일일 제한 활성화",
        "daily_remaining": "오늘 남은 허용 시간: {time}",
        "daily_limit_exceeded": "오늘의 일일 제한 시간을 이미 초과했습니다.",
        "daily_limit_capped": "일일 제한에 맞게 타이머가 {time}(으)로 조정되었습니다.",
        "no_limit": "제한 없음",
        
        # Grace Period & Auto-Resume
        "grace_period_warning_shutdown": "⚠️ 시간이 만료되었습니다!\n60초 후에 시스템이 종료됩니다.\n작업을 저장하세요!",
        "grace_period_warning_logoff": "⚠️ 시간이 만료되었습니다!\n60초 후에 로그오프됩니다.\n작업을 저장하세요!",
        "grace_period_warning_lock": "⚠️ 시간이 만료되었습니다!\n60초 후에 화면이 잠깁니다.\n작업을 저장하세요!",
        "grace_period_warning": "⚠️ 시간이 만료되었습니다!\n60초 후에 시스템이 종료됩니다.\n작업을 저장하세요!",
        "timer_resumed": "이전 타이머가 자동으로 재개되었습니다.\n남은 시간: {time}",
        "timer_expired_while_closed": "프로그램이 닫힌 동안 타이머가 만료되었습니다.",
        "tamper_detected": "⚠️ 비밀번호 파일이 삭제된 것이 감지되었습니다.\n통계에 기록이 남았습니다. 비밀번호를 다시 설정하세요.",
        "shutdown_reason": "TimeParents: 시간이 만료되었습니다. 60초 후에 시스템이 종료됩니다.",
        "type_tamper": "⚠️ 변조 감지",
        "grace_countdown": "⚠️ 시간이 만료되었습니다!\n{seconds}초 후에 {action}이(가) 실행됩니다.\n작업을 저장하세요!",
    },
    
    "en": {
        # App
        "app_title": "TimeParents",
        "version": "v",
        
        # Login & Password
        "login": "Login",
        "password_setup": "Password Setup",
        "password_setup_msg": "Please set your initial password.",
        "password": "Password",
        "password_confirm": "Confirm Password",
        "password_input": "Enter Password",
        "password_enter": "Enter password:",
        "password_change": "Change Password",
        "current_password": "Enter current password:",
        "setup_complete": "Setup Complete",
        
        # Tabs
        "tab_game": "Specific Game",
        "tab_countdown": "Countdown",
        "tab_schedule": "Scheduled Time",
        
        # Dashboard
        "game_time_settings": "Game Time Settings",
        "hours": "Hours",
        "minutes": "Minutes",
        "hour": "h",
        "minute": "m",
        "dur_hour": "h",
        "dur_minute": "m",
        "game_process_name": "Game Process Name",
        "process_name_placeholder": "Process name (e.g., Roblox)",
        "schedule_note": "* Will shut down at the specified time.",
        "game_note": "* Time decreases only when the game is running.",
        
        # Actions
        "action_after_time": "Action After Time Expires",
        "shutdown": "Shutdown System",
        "logoff": "Log Off",
        "lock": "Lock Screen",
        "kill_game": "Close Game",
        "kill_game_option": "Close Game Only (Specific Game mode)",
        "kill_game_needs_game_tab": "'Close Game Only' can only be used on the Specific Game tab.",
        "game_blocked": "Time for {game} is up for today.\nThe game will be closed automatically if started again.\n(Unblocked automatically tomorrow)",
        "start_timer": "Start Timer",
        "stop_timer": "Stop / Change Timer",
        "timer_running_note": "* Timer continues running even if window is closed.",
        "restore": "Restore Window",
        "tray_running_msg": "TimeParents is running in the background (system tray).",
        
        # Buttons
        "about": "About",
        "statistics": "Statistics",
        "time_picker": "🕐 Select Time",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "ok": "OK",
        
        # Time Picker
        "time_picker_title": "Select Time",
        "select_end_time": "Select end time",
        
        # Timer
        "remaining_time": "Remaining Time",
        
        # Warnings & Errors
        "error": "Error",
        "success": "Success",
        "warning": "Time Warning",
        "time_warning": "{minutes} minute(s) remaining!",
        "password_set_success": "Password has been set.",
        "password_empty": "Please enter a password.",
        "password_mismatch": "Passwords do not match.",
        "password_incorrect": "Incorrect password.",
        "enter_valid_time": "Please enter a valid time.",
        "enter_game_name": "Please enter a game name.",
        "min_time_1min": "Please set time to at least 1 minute.",
        "timer_running_confirm": "Timer is running. Are you sure you want to exit?\\n(Password required to exit)",
        "close": "Close",
        
        # About Dialog
        "about_title": "About",
        "creator": "Creator: HadesYI",
        "email": "Email: leesk55@gmail.com",
        
        # Statistics
        "stats_title": "Usage Statistics",
        "admin_confirm": "Admin Verification",
        "today_total": "Today's Total Usage",
        "weekly_stats": "This Week's Statistics",
        "recent_logs": "Recent Usage Logs",
        "no_logs": "No logs available.",
        "daily_average": "Daily Average",
        "weekly_total": "Weekly Total",
        "search_total": "Search Period Total",
        "search_tab": "Search Logs",
        "all": "All",
        "search": "Search",
        "monday": "Monday",
        "tuesday": "Tuesday",
        "wednesday": "Wednesday",
        "thursday": "Thursday",
        "friday": "Friday",
        "saturday": "Saturday",
        "sunday": "Sunday",
        
        # Log types
        "type_game": "Game",
        "type_countdown": "Countdown",
        "type_schedule": "Schedule",
        
        # Language
        "language": "Language",
        "korean": "한국어",
        "english": "English",
        
        # Theme
        "theme": "Theme",
        "dark_mode": "Dark Mode",
        "light_mode": "Light Mode",
        
        # Daily Limit
        "daily_limit": "Daily Usage Limit",
        "daily_limit_hours": "Hours",
        "daily_limit_minutes": "Minutes",
        "daily_limit_enable": "Enable Daily Limit",
        "daily_remaining": "Remaining today: {time}",
        "daily_limit_exceeded": "Today's daily limit has already been exceeded.",
        "daily_limit_capped": "Timer has been adjusted to {time} to match the daily limit.",
        "no_limit": "No Limit",
        
        # Grace Period & Auto-Resume
        "grace_period_warning_shutdown": "⚠️ Time's up!\nSystem will shut down in 60 seconds.\nPlease save your work!",
        "grace_period_warning_logoff": "⚠️ Time's up!\nSystem will log off in 60 seconds.\nPlease save your work!",
        "grace_period_warning_lock": "⚠️ Time's up!\nScreen will lock in 60 seconds.\nPlease save your work!",
        "grace_period_warning": "⚠️ Time's up!\nSystem will shut down in 60 seconds.\nPlease save your work!",
        "timer_resumed": "Previous timer has been automatically resumed.\nRemaining: {time}",
        "timer_expired_while_closed": "Timer expired while the program was closed.",
        "tamper_detected": "⚠️ The password file was deleted.\nThis has been recorded in the statistics. Please set the password again.",
        "shutdown_reason": "TimeParents: Time is up. The system will shut down in 60 seconds.",
        "type_tamper": "⚠️ Tampering detected",
        "grace_countdown": "⚠️ Time's up!\n{action} will execute in {seconds} seconds.\nPlease save your work!",
    }
}

def get_text(key, lang="ko"):
    """Get translated text for the given key and language"""
    return LANGUAGES.get(lang, LANGUAGES["ko"]).get(key, key)

def format_hm(seconds, lang="ko", compact=False):
    """초를 'X시간 Y분' 형식으로 변환합니다. compact=True면 0시간일 때 분만 표시합니다."""
    h, m = divmod(int(seconds) // 60, 60)
    hour, minute = get_text("dur_hour", lang), get_text("dur_minute", lang)
    if compact and h == 0:
        return f"{m}{minute}"
    return f"{h}{hour} {m}{minute}"

def get_all_languages():
    """Return list of available languages"""
    return [
        ("ko", "한국어"),
        ("en", "English")
    ]
