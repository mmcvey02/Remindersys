"""Source selection."""

from __future__ import annotations

import sys

from remindersys.config import Config
from remindersys.sources.base import Source, SourceError, filter_calendars

__all__ = ["Source", "SourceError", "create_source", "filter_calendars", "needs_setup"]


def needs_setup(config: Config) -> bool:
    """True if the configured source can't work without more user input."""
    kind = _resolve_kind(config)
    return kind == "caldav" and not (config.icloud_username and config.get_password())


def _resolve_kind(config: Config) -> str:
    if config.source != "auto":
        return config.source
    return "eventkit" if sys.platform == "darwin" else "caldav"


def create_source(config: Config) -> Source:
    kind = _resolve_kind(config)
    if kind == "demo":
        from remindersys.sources.demo import DemoSource

        return DemoSource()
    if kind == "eventkit":
        if sys.platform != "darwin":
            raise SourceError("EventKit is only available on macOS; use the iCloud (CalDAV) source.")
        from remindersys.sources.eventkit import EventKitSource

        return EventKitSource()
    if kind == "caldav":
        from remindersys.sources.caldav_source import CalDAVSource

        password = config.get_password()
        if not (config.icloud_username and password):
            raise SourceError("iCloud username/app-specific password not set. Open Settings.")
        return CalDAVSource(config.caldav_url, config.icloud_username, password)
    raise SourceError(f"Unknown source {config.source!r}")
