"""Core data types shared by every part of the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ItemKind(str, Enum):
    EVENT = "event"
    REMINDER = "reminder"


class Tier(int, Enum):
    """Priority tiers, ordered so that comparisons like ``tier >= Tier.HIGH`` work."""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return self.name.capitalize()


@dataclass
class Item:
    """A calendar event or a reminder, normalised from any source.

    All datetimes are timezone-aware in the local timezone. For reminders,
    ``start`` is the due date (``None`` when the reminder has no due date).
    """

    uid: str
    kind: ItemKind
    title: str
    start: datetime | None
    end: datetime | None = None
    all_day: bool = False
    location: str | None = None
    notes: str | None = None
    url: str | None = None
    calendar: str | None = None
    # iCalendar PRIORITY semantics: 0 = undefined, 1 = highest ... 9 = lowest.
    source_priority: int = 0
    flagged: bool = False
    attendees: int = 0
    recurring: bool = False
    completed: bool = False
    # User-defined alarms, in minutes before ``start``.
    alarms_minutes: list[int] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Unique per occurrence (recurring events share a uid)."""
        when = self.start.isoformat() if self.start else "undated"
        return f"{self.kind.value}:{self.uid}:{when}"

    @property
    def is_timed(self) -> bool:
        return self.start is not None and not self.all_day

    @property
    def duration(self) -> timedelta | None:
        if self.start and self.end:
            return self.end - self.start
        return None


@dataclass
class TravelEstimate:
    minutes: int
    method: str  # "virtual", "onsite", "route", "distance", "default", "none"
    distance_km: float | None = None
    origin: str | None = None

    @property
    def needs_travel(self) -> bool:
        return self.minutes > 0


@dataclass
class PriorityResult:
    score: int
    tier: Tier
    reasons: list[str] = field(default_factory=list)


@dataclass
class AnalyzedItem:
    """An item together with everything the app has worked out about it."""

    item: Item
    priority: PriorityResult
    travel: TravelEstimate | None = None

    @property
    def leave_at(self) -> datetime | None:
        if not self.item.is_timed or self.travel is None:
            return None
        return self.item.start - timedelta(minutes=self.travel.minutes)


@dataclass
class PlannedNotification:
    key: str
    item_key: str
    fire_at: datetime
    expires_at: datetime
    title: str
    message: str
    tier: Tier
    urgent: bool = False
