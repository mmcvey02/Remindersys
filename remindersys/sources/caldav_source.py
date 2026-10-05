"""iCloud Calendar/Reminders over CalDAV - the cross-platform (Windows) path.

Requires an Apple ID *app-specific password* (appleid.apple.com -> Sign-In and
Security -> App-Specific Passwords). Note: Apple only exposes Reminders lists
over CalDAV if they have not been "upgraded" to the new Reminders format; on
most modern accounts calendars sync fully but reminders may be missing. Events
and reminders are both fully supported on macOS through EventKit.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from remindersys.models import Item, ItemKind
from remindersys.sources.base import Source, SourceError

log = logging.getLogger(__name__)


def to_local(value) -> tuple[datetime | None, bool]:
    """Convert an iCalendar date/datetime to (aware local datetime, is_all_day)."""
    if value is None:
        return None, False
    if hasattr(value, "dt"):
        value = value.dt
    if isinstance(value, datetime):
        if value.tzinfo is None:  # "floating" time = local wall-clock time
            return value.astimezone(), False
        return value.astimezone(), False
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).astimezone(), True
    return None, False


def _text(component, name: str) -> str | None:
    value = component.get(name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _alarm_minutes(component) -> list[int]:
    minutes = []
    for alarm in component.walk("VALARM"):
        trigger = alarm.get("TRIGGER")
        if trigger is not None and isinstance(trigger.dt, timedelta):
            minutes.append(max(0, int(-trigger.dt.total_seconds() // 60)))
    return minutes


def _attendee_count(component) -> int:
    attendees = component.get("ATTENDEE")
    if attendees is None:
        return 0
    return len(attendees) if isinstance(attendees, list) else 1


def parse_vevent(component, calendar_name: str | None) -> Item | None:
    if _text(component, "STATUS") == "CANCELLED":
        return None
    start, all_day = to_local(component.get("DTSTART"))
    if start is None:
        return None
    end, _ = to_local(component.get("DTEND"))
    if end is None and component.get("DURATION") is not None:
        end = start + component.get("DURATION").dt
    uid = _text(component, "UID") or f"{calendar_name}:{start.isoformat()}"
    return Item(
        uid=uid,
        kind=ItemKind.EVENT,
        title=_text(component, "SUMMARY") or "(No title)",
        start=start,
        end=end,
        all_day=all_day,
        location=_text(component, "LOCATION"),
        notes=_text(component, "DESCRIPTION"),
        url=_text(component, "URL"),
        calendar=calendar_name,
        attendees=_attendee_count(component),
        recurring=component.get("RRULE") is not None or component.get("RECURRENCE-ID") is not None,
        alarms_minutes=_alarm_minutes(component),
    )


def parse_vtodo(component, calendar_name: str | None) -> Item | None:
    status = _text(component, "STATUS")
    if status in ("COMPLETED", "CANCELLED") or component.get("COMPLETED") is not None:
        return None
    due, all_day = to_local(component.get("DUE") or component.get("DTSTART"))
    try:
        priority = int(component.get("PRIORITY", 0))
    except (TypeError, ValueError):
        priority = 0
    return Item(
        uid=_text(component, "UID") or _text(component, "SUMMARY") or "todo",
        kind=ItemKind.REMINDER,
        title=_text(component, "SUMMARY") or "(No title)",
        start=due,
        all_day=all_day,
        location=_text(component, "LOCATION"),
        notes=_text(component, "DESCRIPTION"),
        url=_text(component, "URL"),
        calendar=calendar_name,
        source_priority=priority,
        recurring=component.get("RRULE") is not None,
        alarms_minutes=_alarm_minutes(component),
    )


class CalDAVSource(Source):
    name = "iCloud (CalDAV)"

    def __init__(self, url: str, username: str, password: str):
        self.url, self.username, self.password = url, username, password

    def fetch(self, start: datetime, end: datetime) -> list[Item]:
        try:
            import caldav
        except ImportError as exc:
            raise SourceError("The 'caldav' package is not installed") from exc
        try:
            client = caldav.DAVClient(url=self.url, username=self.username, password=self.password)
            calendars = client.principal().calendars()
        except Exception as exc:  # noqa: BLE001 - caldav raises a variety of errors
            raise SourceError(f"Could not connect to iCloud: {exc}") from exc

        items: list[Item] = []
        for cal in calendars:
            try:
                name = cal.get_display_name()
            except Exception:  # noqa: BLE001
                name = None
            try:
                components = cal.get_supported_components()
            except Exception:  # noqa: BLE001
                components = ["VEVENT", "VTODO"]
            try:
                if "VEVENT" in components:
                    for obj in cal.search(start=start, end=end, event=True, expand=True):
                        for comp in obj.icalendar_instance.walk("VEVENT"):
                            item = parse_vevent(comp, name)
                            if item:
                                items.append(item)
                if "VTODO" in components:
                    for obj in cal.search(todo=True, include_completed=False):
                        for comp in obj.icalendar_instance.walk("VTODO"):
                            item = parse_vtodo(comp, name)
                            if item:
                                items.append(item)
            except Exception as exc:  # noqa: BLE001 - keep going with other calendars
                log.warning("Skipping calendar %r: %s", name, exc)
        return items
