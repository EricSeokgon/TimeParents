import calendar
from datetime import datetime

import customtkinter as ctk
import languages
import utils

DAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EN_DAY_ABBREVIATIONS = ["M", "T", "W", "Th", "F", "S", "Su"]
LOG_TYPE_KEYS = {
    "game": "type_game",
    "countdown": "type_countdown",
    "schedule": "type_schedule",
    "tamper": "type_tamper",
}


def _render_log_rows(parent, logs, lang):
    """기록 목록을 최신순으로 그립니다."""
    if not logs:
        ctk.CTkLabel(parent, text=languages.get_text("no_logs", lang)).pack(pady=20)
        return
    for log in reversed(logs):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=2)

        ts = log["timestamp"][5:-3]  # MM-DD HH:MM
        dur_str = languages.format_hm(log["duration"], lang, compact=True)
        type_key = LOG_TYPE_KEYS.get(log["type"])
        type_str = languages.get_text(type_key, lang) if type_key else log["type"]
        if log.get("target"):
            type_str += f" ({log['target']})"

        ctk.CTkLabel(frame, text=ts, width=80, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(frame, text=type_str, anchor="w").pack(side="left", padx=5, expand=True, fill="x")
        ctk.CTkLabel(frame, text=dur_str, width=60, anchor="e").pack(side="right", padx=5)


def _build_weekly_tab(tab, lang):
    # Today's Total
    today_str = languages.format_hm(utils.get_today_total(), lang)
    ctk.CTkLabel(tab, text=languages.get_text("today_total", lang), font=("Arial", 14, "bold")).pack(pady=(10, 2))
    ctk.CTkLabel(tab, text=today_str, font=("Arial", 20, "bold"), text_color="#3B8ED0").pack(pady=(0, 10))

    # Weekly column chart container
    weekly_frame = ctk.CTkFrame(tab, height=185, fg_color=("#E2E8F0", "#1E293B"))
    weekly_frame.pack(pady=5, padx=10, fill="x")
    weekly_frame.pack_propagate(False)

    weekly_data = utils.get_weekly_stats()
    max_seconds = max(s for _, s in weekly_data) or 1
    weekly_total_seconds = sum(s for _, s in weekly_data)
    current_weekday = datetime.now().weekday()

    for i, (_, seconds) in enumerate(weekly_data):
        col_frame = ctk.CTkFrame(weekly_frame, fg_color="transparent", width=46)
        col_frame.pack(side="left", padx=2, fill="y", expand=True)
        col_frame.pack_propagate(False)

        # Time text (top)
        h, m = divmod(seconds // 60, 60)
        if seconds > 0:
            time_str = f"{h}h\n{m}m" if h > 0 else f"{m}m"
        else:
            time_str = ""
        ctk.CTkLabel(col_frame, text=time_str, font=("Arial", 10), height=30, text_color="gray").pack(side="top", fill="x")

        # Day label (bottom)
        if lang == "en":
            day_text = EN_DAY_ABBREVIATIONS[i]
        else:
            day_text = languages.get_text(DAY_KEYS[i], lang)[0]
        is_today = (i == current_weekday)
        ctk.CTkLabel(
            col_frame,
            text=day_text,
            font=("Arial", 11, "bold" if is_today else "normal"),
            text_color=("#10B981" if is_today else "#1E293B", "#10B981" if is_today else "#94A3B8")
        ).pack(side="bottom", fill="x", pady=2)

        # Vertical bar (middle, anchored to bottom)
        bar_height = int((seconds / max_seconds) * 100)
        if seconds > 0 and bar_height < 6:
            bar_height = 6

        bar_container = ctk.CTkFrame(col_frame, fg_color="transparent")
        bar_container.pack(side="bottom", fill="both", expand=True)

        bar_color = ("#10B981", "#10B981") if is_today else ("#3B8ED0", "#1F538D")
        bar = ctk.CTkFrame(bar_container, width=16, height=bar_height, corner_radius=4, fg_color=bar_color)
        bar.pack(side="bottom", pady=(0, 2))
        bar.pack_propagate(False)

    # Weekly Total and Average Summary
    summary_text = (f"{languages.get_text('weekly_total', lang)}: {languages.format_hm(weekly_total_seconds, lang)}   |   "
                    f"{languages.get_text('daily_average', lang)}: {languages.format_hm(weekly_total_seconds // 7, lang)}")
    ctk.CTkLabel(tab, text=summary_text, font=("Arial", 12, "bold"), text_color="#3B8ED0").pack(pady=10)

    # Recent logs list inside Weekly Tab
    ctk.CTkLabel(tab, text=languages.get_text("recent_logs", lang), font=("Arial", 12, "bold")).pack(pady=(10, 2), anchor="w", padx=10)
    scroll_frame = ctk.CTkScrollableFrame(tab, width=340, height=180)
    scroll_frame.pack(pady=5, padx=10, fill="both", expand=True)
    _render_log_rows(scroll_frame, utils.load_logs(), lang)


def _build_search_tab(tab, lang):
    # Filters Frame
    filter_frame = ctk.CTkFrame(tab)
    filter_frame.pack(pady=10, padx=10, fill="x")

    now = datetime.now()
    years = [str(now.year - 1), str(now.year), str(now.year + 1)]
    year_var = ctk.StringVar(value=str(now.year))
    ctk.CTkOptionMenu(filter_frame, variable=year_var, values=years, width=80).pack(side="left", padx=5, pady=5)

    month_var = ctk.StringVar(value=f"{now.month:02d}")
    months = [f"{i:02d}" for i in range(1, 13)]
    ctk.CTkOptionMenu(filter_frame, variable=month_var, values=months, width=60).pack(side="left", padx=5, pady=5)

    # Day combobox (All / specific day)
    all_translated = languages.get_text("all", lang)
    day_var = ctk.StringVar(value=all_translated)
    days = [all_translated] + [f"{i:02d}" for i in range(1, 32)]
    ctk.CTkOptionMenu(filter_frame, variable=day_var, values=days, width=80).pack(side="left", padx=5, pady=5)

    # Results area
    result_frame = ctk.CTkFrame(tab, fg_color="transparent")
    result_frame.pack(fill="both", expand=True, padx=5, pady=5)

    def perform_search():
        for widget in result_frame.winfo_children():
            widget.destroy()

        y, m, d = year_var.get(), month_var.get(), day_var.get()
        is_month_search = d == all_translated
        prefix = f"{y}-{m}-" if is_month_search else f"{y}-{m}-{d}"

        filtered_logs = [log for log in utils.load_logs() if log["timestamp"].startswith(prefix)]
        total_seconds = sum(log.get("duration", 0) for log in filtered_logs)
        summary_str = f"{languages.get_text('search_total', lang)}: {languages.format_hm(total_seconds, lang)}"

        if is_month_search:
            try:
                num_days = calendar.monthrange(int(y), int(m))[1]
            except ValueError:
                num_days = 30
            avg_str = languages.format_hm(total_seconds // num_days, lang)
            summary_str += f"\n({languages.get_text('daily_average', lang)}: {avg_str})"

        ctk.CTkLabel(result_frame, text=summary_str, font=("Arial", 13, "bold"), text_color="#3B8ED0").pack(pady=10)

        scroll_search = ctk.CTkScrollableFrame(result_frame, width=340, height=300)
        scroll_search.pack(fill="both", expand=True, padx=5, pady=5)
        _render_log_rows(scroll_search, filtered_logs, lang)

    ctk.CTkButton(filter_frame, text=languages.get_text("search", lang), width=60, command=perform_search).pack(side="left", padx=5, pady=5)

    # Trigger initial search for the current month
    perform_search()


def open_statistics(app):
    """사용 통계 창을 엽니다."""
    lang = app.current_lang
    stats_window = ctk.CTkToplevel(app)
    stats_window.title(languages.get_text("stats_title", lang))
    stats_window.geometry("400x700")

    # Center
    stats_window.transient(app)
    stats_window.grab_set()

    tabview = ctk.CTkTabview(stats_window)
    tabview.pack(fill="both", expand=True, padx=10, pady=10)

    _build_weekly_tab(tabview.add(languages.get_text("weekly_stats", lang)), lang)
    _build_search_tab(tabview.add(languages.get_text("search_tab", lang)), lang)
    return stats_window
