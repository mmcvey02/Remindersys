"""Start the app automatically at login, so the daily summary arrives at startup."""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from remindersys import APP_NAME

log = logging.getLogger(__name__)

LAUNCH_AGENT_LABEL = "com.remindersys.agent"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> list[str]:
    """The command that starts this app in background mode."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "run"]
    return [sys.executable, "-m", "remindersys", "run"]


def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _linux_desktop() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "remindersys.desktop"


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_plist().exists()
    return _linux_desktop().exists()


def enable() -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import winreg

        value = subprocess.list2cmdline(cmd)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, value)
    elif sys.platform == "darwin":
        path = _mac_plist()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            plistlib.dump(
                {
                    "Label": LAUNCH_AGENT_LABEL,
                    "ProgramArguments": cmd,
                    "RunAtLoad": True,
                    "KeepAlive": False,
                    "ProcessType": "Interactive",
                },
                fh,
            )
    else:
        path = _linux_desktop()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=RemindersSys\n"
            f"Exec={subprocess.list2cmdline(cmd)}\nX-GNOME-Autostart-enabled=true\n",
            encoding="utf-8",
        )
    log.info("Start at login enabled: %s", cmd)


def disable() -> None:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
        except OSError:
            pass
    elif sys.platform == "darwin":
        _mac_plist().unlink(missing_ok=True)
    else:
        _linux_desktop().unlink(missing_ok=True)
    log.info("Start at login disabled")
