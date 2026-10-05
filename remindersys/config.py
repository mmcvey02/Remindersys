"""User configuration, stored as JSON in the per-user application data folder."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from remindersys import APP_NAME

log = logging.getLogger(__name__)

KEYRING_SERVICE = "RemindersSys-iCloud"


def data_dir() -> Path:
    """Per-user folder for config, state, logs and summaries."""
    override = os.environ.get("REMINDERSYS_HOME")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME.lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Config:
    # --- Data source -------------------------------------------------------
    # "auto": EventKit on macOS, iCloud CalDAV elsewhere.
    # "eventkit": macOS Calendar/Reminders database (no password needed).
    # "caldav": iCloud over CalDAV (works on Windows; needs an app-specific password).
    # "demo": generated sample data, for trying the app out.
    source: str = "auto"
    icloud_username: str = ""
    caldav_url: str = "https://caldav.icloud.com/"
    calendars_include: list[str] = field(default_factory=list)  # empty = all
    calendars_exclude: list[str] = field(default_factory=list)

    # --- Travel ------------------------------------------------------------
    home_address: str = ""
    travel_mode: str = "driving"  # driving | walking | cycling | transit
    use_online_routing: bool = True
    default_travel_minutes: int = 20  # used when a location can't be resolved
    arrival_buffer_minutes: int = 10  # aim to arrive this early
    parking_minutes: int = 5  # added to driving trips

    # --- Notifications -----------------------------------------------------
    sync_interval_minutes: int = 5
    lookahead_days: int = 14
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "07:00"
    modal_alert_for_critical: bool = True

    # --- Summaries ---------------------------------------------------------
    daily_summary_on_startup: bool = True
    # If the computer stays on overnight, send the daily summary at this time.
    daily_summary_fallback_time: str = "08:00"
    weekly_summary_enabled: bool = True
    weekly_summary_weekday: int = 0  # 0 = Monday
    open_summary_in_browser: bool = True

    # --- Priority tuning ---------------------------------------------------
    extra_high_priority_keywords: list[str] = field(default_factory=list)
    extra_low_priority_keywords: list[str] = field(default_factory=list)
    # Score adjustment per calendar/list name, e.g. {"Work": 10, "Family": 5}.
    calendar_weights: dict[str, int] = field(default_factory=dict)

    # --- Misc --------------------------------------------------------------
    start_at_login: bool = True

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        path = cls.path()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Could not read %s (%s); using defaults", path, exc)
            return cls()
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            log.warning("Ignoring unknown config keys: %s", ", ".join(sorted(unknown)))
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        path = self.path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def exists(cls) -> bool:
        return cls.path().exists()

    # --- Credentials (kept in the OS keychain, never in config.json) -------
    def get_password(self) -> str | None:
        env = os.environ.get("REMINDERSYS_ICLOUD_PASSWORD")
        if env:
            return env
        if not self.icloud_username:
            return None
        try:
            import keyring

            return keyring.get_password(KEYRING_SERVICE, self.icloud_username)
        except Exception as exc:  # noqa: BLE001 - keyring backends raise many types
            log.error("Could not read password from the system keychain: %s", exc)
            return None

    def set_password(self, password: str) -> None:
        import keyring

        keyring.set_password(KEYRING_SERVICE, self.icloud_username, password)
