"""Common interface for calendar/reminder back-ends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from remindersys.models import Item


class SourceError(Exception):
    """A source could not be read (permissions, credentials, network...)."""


class Source(ABC):
    name: str = "source"

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> list[Item]:
        """Return events overlapping [start, end) and all incomplete reminders.

        Reminders without a due date, and overdue reminders, are included
        regardless of the window.
        """


def filter_calendars(items: list[Item], include: list[str], exclude: list[str]) -> list[Item]:
    inc = {c.lower() for c in include}
    exc = {c.lower() for c in exclude}
    out = []
    for item in items:
        cal = (item.calendar or "").lower()
        if inc and cal not in inc:
            continue
        if cal in exc:
            continue
        out.append(item)
    return out
