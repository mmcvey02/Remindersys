"""System tray / menu bar icon that hosts the background engine."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

from remindersys import autostart
from remindersys.app import App
from remindersys.autostart import launch_command
from remindersys.config import data_dir
from remindersys.icon import draw_icon

log = logging.getLogger(__name__)


def open_path(path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def run_tray(app: App) -> None:
    """Run the engine in a worker thread and the tray on the main thread
    (macOS requires UI on the main thread)."""
    import pystray

    worker = threading.Thread(target=app.run_forever, name="engine", daemon=True)

    def in_background(fn):
        return lambda icon, item: threading.Thread(target=fn, daemon=True).start()

    def show(kind):
        def run():
            if app.last_sync is None:
                app.sync()
            app.deliver_summary(app.build_summary(kind), open_browser=True)

        return run

    def open_settings():
        cmd = launch_command()[:-1] + ["setup"]
        subprocess.Popen(cmd)

    def toggle_autostart(icon, item):
        if autostart.is_enabled():
            autostart.disable()
        else:
            autostart.enable()
        app.config.start_at_login = autostart.is_enabled()
        app.config.save()

    def status_text(item):
        if app.last_error:
            return "⚠ " + app.last_error[:60]
        if app.last_sync:
            return f"Last sync {app.last_sync:%H:%M} · {len(app.planned)} alerts planned"
        return "Syncing…"

    def quit_app(icon, item):
        app.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Today's summary", in_background(show("daily")), default=True),
        pystray.MenuItem("This week", in_background(show("weekly"))),
        pystray.MenuItem("Sync now", lambda icon, item: app.request_sync()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Settings…", lambda icon, item: open_settings()),
        pystray.MenuItem("Start at login", toggle_autostart, checked=lambda item: autostart.is_enabled()),
        pystray.MenuItem("Open log folder", lambda icon, item: open_path(data_dir())),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon("RemindersSys", draw_icon(64), "RemindersSys", menu)
    app.notifier.fallback = lambda title, message: icon.notify(message, title)

    def setup(icon):
        icon.visible = True
        worker.start()

    icon.run(setup=setup)
    app.stop()
