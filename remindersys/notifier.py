"""Native desktop notifications without heavy dependencies.

* Windows 10/11: a WinRT toast raised through the built-in Windows PowerShell.
  Urgent toasts use the "reminder" scenario so they stay on screen.
* macOS: Notification Center via ``osascript``; urgent ones also show an alert
  dialog that stays up until dismissed (or 10 minutes pass).
* Linux: ``notify-send``.
Everything is also written to the log.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

APP_ID = "RemindersSys"
# Windows needs a registered AppUserModelID to show toasts; PowerShell's is always present.
POWERSHELL_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

WINDOWS_TOAST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:RS_TOAST_XML)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:RS_APP_ID).Show($toast)
"""


def _applescript_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def windows_toast_xml(title: str, message: str, urgent: bool) -> str:
    scenario = ' scenario="reminder"' if urgent else ""
    # The reminder scenario is ignored unless the toast has at least one button.
    actions = (
        '<actions><action content="Dismiss" arguments="dismiss" activationType="system"/></actions>'
        if urgent
        else ""
    )
    audio = '<audio src="ms-winsoundevent:Notification.Reminder"/>' if urgent else ""
    return (
        f"<toast{scenario}><visual><binding template=\"ToastGeneric\">"
        f"<text>{escape(title)}</text><text>{escape(message)}</text>"
        f"</binding></visual>{actions}{audio}</toast>"
    )


class Notifier:
    def __init__(self, modal_for_urgent: bool = True):
        self.modal_for_urgent = modal_for_urgent
        self.fallback = None  # optional callable(title, message), e.g. the tray icon

    def notify(self, title: str, message: str, urgent: bool = False) -> bool:
        log.info("NOTIFY%s %s: %s", " [urgent]" if urgent else "", title, message)
        try:
            if sys.platform == "win32":
                ok = self._windows(title, message, urgent)
            elif sys.platform == "darwin":
                ok = self._macos(title, message, urgent)
            else:
                ok = self._linux(title, message, urgent)
        except Exception as exc:  # noqa: BLE001 - never crash on a notification
            log.error("Notification failed: %s", exc)
            ok = False
        if not ok and self.fallback:
            try:
                self.fallback(title, message)
                ok = True
            except Exception as exc:  # noqa: BLE001
                log.error("Fallback notification failed: %s", exc)
        return ok

    def _windows(self, title: str, message: str, urgent: bool) -> bool:
        env = dict(os.environ)
        env["RS_TOAST_XML"] = windows_toast_xml(title, message, urgent)
        env["RS_APP_ID"] = POWERSHELL_APP_ID
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-Command", WINDOWS_TOAST_SCRIPT],
            env=env,
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            log.warning("Toast failed: %s", result.stderr.decode(errors="replace").strip())
        return result.returncode == 0

    def _macos(self, title: str, message: str, urgent: bool) -> bool:
        sound = "Glass" if urgent else "default"
        script = (
            f"display notification {_applescript_str(message)} with title {_applescript_str(APP_ID)} "
            f"subtitle {_applescript_str(title)} sound name {_applescript_str(sound)}"
        )
        result = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30)
        if urgent and self.modal_for_urgent:
            alert = (
                f"display alert {_applescript_str(title)} message {_applescript_str(message)} "
                f"as critical giving up after 600"
            )
            # Non-blocking: the dialog stays up while the app keeps running.
            subprocess.Popen(["osascript", "-e", alert], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0

    def _linux(self, title: str, message: str, urgent: bool) -> bool:
        if not shutil.which("notify-send"):
            return False
        args = ["notify-send", "-a", APP_ID]
        if urgent:
            args += ["-u", "critical"]
        result = subprocess.run(args + [title, message], capture_output=True, timeout=30)
        return result.returncode == 0
