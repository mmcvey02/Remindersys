"""Settings window (Tkinter, bundled with Python - no extra dependencies)."""

from __future__ import annotations

import logging
import sys
import threading

from remindersys import autostart
from remindersys.config import Config

log = logging.getLogger(__name__)

SOURCES = [
    ("Automatic", "auto"),
    ("macOS Calendar & Reminders", "eventkit"),
    ("iCloud (app-specific password)", "caldav"),
    ("Demo data", "demo"),
]
MODES = ["driving", "transit", "walking", "cycling"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def run_setup() -> bool:
    """Show the settings window. Returns True if the user saved."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    config = Config.load()
    saved = {"value": False}

    root = tk.Tk()
    root.title("RemindersSys Settings")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")
    row = 0

    def heading(text):
        nonlocal row
        ttk.Label(frame, text=text, font=("TkDefaultFont", 11, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(12 if row else 0, 4)
        )
        row += 1

    def field(label, widget, hint=None):
        nonlocal row
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=2)
        widget.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1
        if hint:
            ttk.Label(frame, text=hint, foreground="#6e6e73", wraplength=380).grid(
                row=row, column=1, sticky="w"
            )
            row += 1

    # --- Source ----------------------------------------------------------
    heading("Apple Calendar & Reminders")
    source_var = tk.StringVar(value=next(lbl for lbl, key in SOURCES if key == config.source))
    field("Sync with", ttk.Combobox(frame, textvariable=source_var, state="readonly",
                                    values=[lbl for lbl, _ in SOURCES], width=36))
    user_var = tk.StringVar(value=config.icloud_username)
    field("Apple ID", ttk.Entry(frame, textvariable=user_var, width=38))
    pass_var = tk.StringVar(value="")
    has_password = bool(config.icloud_username and config.get_password())
    field(
        "App-specific password",
        ttk.Entry(frame, textvariable=pass_var, show="•", width=38),
        ("Saved in your system keychain. Leave blank to keep it. " if has_password else "")
        + "Create one at appleid.apple.com → Sign-In and Security → App-Specific Passwords. "
        "Only needed on Windows (or when iCloud is chosen on a Mac).",
    )

    # --- Travel ----------------------------------------------------------
    heading("Travel")
    home_var = tk.StringVar(value=config.home_address)
    field("Home address", ttk.Entry(frame, textvariable=home_var, width=38),
          "Used to estimate when you need to leave.")
    mode_var = tk.StringVar(value=config.travel_mode)
    field("Usually travel by", ttk.Combobox(frame, textvariable=mode_var, values=MODES, state="readonly"))
    buffer_var = tk.IntVar(value=config.arrival_buffer_minutes)
    field("Arrive early by (min)", ttk.Spinbox(frame, from_=0, to=120, textvariable=buffer_var, width=6))
    default_var = tk.IntVar(value=config.default_travel_minutes)
    field("Unknown-location travel (min)", ttk.Spinbox(frame, from_=0, to=240, textvariable=default_var, width=6))

    # --- Summaries ---------------------------------------------------------
    heading("Summaries & alerts")
    daily_var = tk.BooleanVar(value=config.daily_summary_on_startup)
    field("", ttk.Checkbutton(frame, text="Daily summary when the computer starts", variable=daily_var))
    weekly_var = tk.BooleanVar(value=config.weekly_summary_enabled)
    field("", ttk.Checkbutton(frame, text="Weekly summary of major tasks", variable=weekly_var))
    weekday_var = tk.StringVar(value=WEEKDAYS[config.weekly_summary_weekday % 7])
    field("Weekly summary on", ttk.Combobox(frame, textvariable=weekday_var, values=WEEKDAYS, state="readonly"))
    browser_var = tk.BooleanVar(value=config.open_summary_in_browser)
    field("", ttk.Checkbutton(frame, text="Open summaries in the browser", variable=browser_var))
    quiet_start_var = tk.StringVar(value=config.quiet_hours_start)
    quiet_end_var = tk.StringVar(value=config.quiet_hours_end)
    quiet = ttk.Frame(frame)
    ttk.Entry(quiet, textvariable=quiet_start_var, width=6).pack(side="left")
    ttk.Label(quiet, text=" to ").pack(side="left")
    ttk.Entry(quiet, textvariable=quiet_end_var, width=6).pack(side="left")
    field("Quiet hours", quiet, "Only critical alerts and 'leave now' alerts break through.")
    login_var = tk.BooleanVar(value=autostart.is_enabled())
    field("", ttk.Checkbutton(frame, text="Start RemindersSys at login", variable=login_var))

    def save():
        source = next(key for lbl, key in SOURCES if lbl == source_var.get())
        if source == "eventkit" and sys.platform != "darwin":
            messagebox.showerror("RemindersSys", "macOS Calendar access is only available on a Mac.")
            return
        config.source = source
        config.icloud_username = user_var.get().strip()
        config.home_address = home_var.get().strip()
        config.travel_mode = mode_var.get()
        try:
            config.arrival_buffer_minutes = int(buffer_var.get())
            config.default_travel_minutes = int(default_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("RemindersSys", "Minutes must be whole numbers.")
            return
        config.daily_summary_on_startup = daily_var.get()
        config.weekly_summary_enabled = weekly_var.get()
        config.weekly_summary_weekday = WEEKDAYS.index(weekday_var.get())
        config.open_summary_in_browser = browser_var.get()
        config.quiet_hours_start = quiet_start_var.get().strip()
        config.quiet_hours_end = quiet_end_var.get().strip()
        config.start_at_login = login_var.get()
        if pass_var.get():
            if not config.icloud_username:
                messagebox.showerror("RemindersSys", "Enter your Apple ID first.")
                return
            try:
                config.set_password(pass_var.get().strip())
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("RemindersSys", f"Could not save password to keychain:\n{exc}")
                return
        config.save()
        try:
            autostart.enable() if config.start_at_login else autostart.disable()
        except Exception as exc:  # noqa: BLE001
            log.error("Autostart change failed: %s", exc)
        saved["value"] = True
        root.destroy()

    def test_connection():
        from remindersys.sources.caldav_source import CalDAVSource

        password = pass_var.get().strip() or config.get_password() or ""
        status.set("Connecting…")

        def work():
            from datetime import datetime, timedelta

            try:
                src = CalDAVSource(config.caldav_url, user_var.get().strip(), password)
                now = datetime.now().astimezone()
                n = len(src.fetch(now, now + timedelta(days=7)))
                msg = f"Connected: {n} items in the next 7 days."
            except Exception as exc:  # noqa: BLE001
                msg = f"Failed: {exc}"
            root.after(0, lambda: status.set(msg))

        threading.Thread(target=work, daemon=True).start()

    status = tk.StringVar(value="")
    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(16, 0))
    ttk.Label(buttons, textvariable=status, wraplength=260).pack(side="left")
    ttk.Button(buttons, text="Save", command=save).pack(side="right")
    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right", padx=6)
    ttk.Button(buttons, text="Test iCloud", command=test_connection).pack(side="right")

    root.mainloop()
    return saved["value"]
