"""macOS Calendar and Reminders via EventKit (pyobjc).

Reads the same local database the Calendar and Reminders apps use, so anything
synced to the Mac (iCloud, Exchange, Google...) is included. macOS asks the user
for Calendar and Reminders access the first time.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from remindersys.models import Item, ItemKind
from remindersys.sources.base import Source, SourceError

log = logging.getLogger(__name__)

# EKEntityType / EKAuthorizationStatus / EKEventStatus values.
ENTITY_EVENT, ENTITY_REMINDER = 0, 1
STATUS_DENIED, STATUS_RESTRICTED, STATUS_FULL_ACCESS = 2, 1, 3
EVENT_STATUS_CANCELED = 3


def _wait(done: threading.Event, timeout: float) -> bool:
    """Wait for an EventKit completion handler while keeping the run loop alive."""
    from Foundation import NSDate, NSRunLoop

    deadline = time.monotonic() + timeout
    while not done.is_set() and time.monotonic() < deadline:
        if threading.current_thread() is threading.main_thread():
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))
        else:
            done.wait(0.05)
    return done.is_set()


class EventKitSource(Source):
    name = "macOS Calendar & Reminders"

    def __init__(self):
        try:
            import EventKit  # noqa: F401
        except ImportError as exc:
            raise SourceError("pyobjc-framework-EventKit is not installed") from exc
        import EventKit

        self.ek = EventKit
        self.store = EventKit.EKEventStore.alloc().init()
        self.access = {
            ENTITY_EVENT: self._request_access(ENTITY_EVENT),
            ENTITY_REMINDER: self._request_access(ENTITY_REMINDER),
        }
        if not any(self.access.values()):
            raise SourceError(
                "Calendar and Reminders access denied. Enable RemindersSys in System Settings "
                "> Privacy & Security > Calendars / Reminders."
            )

    def _request_access(self, entity: int) -> bool:
        status = self.ek.EKEventStore.authorizationStatusForEntityType_(entity)
        if status == STATUS_FULL_ACCESS:
            return True
        if status in (STATUS_DENIED, STATUS_RESTRICTED):
            return False
        done, result = threading.Event(), {"granted": False}

        def handler(granted, error):
            result["granted"] = bool(granted)
            if error:
                log.warning("EventKit access error: %s", error)
            done.set()

        store = self.store
        if entity == ENTITY_EVENT and hasattr(store, "requestFullAccessToEventsWithCompletion_"):
            store.requestFullAccessToEventsWithCompletion_(handler)  # macOS 14+
        elif entity == ENTITY_REMINDER and hasattr(store, "requestFullAccessToRemindersWithCompletion_"):
            store.requestFullAccessToRemindersWithCompletion_(handler)
        else:
            store.requestAccessToEntityType_completion_(entity, handler)
        _wait(done, 120)
        return result["granted"]

    # --- conversions ------------------------------------------------------
    @staticmethod
    def _to_dt(nsdate) -> datetime | None:
        if nsdate is None:
            return None
        return datetime.fromtimestamp(nsdate.timeIntervalSince1970()).astimezone()

    @staticmethod
    def _to_nsdate(dt: datetime):
        from Foundation import NSDate

        return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())

    @staticmethod
    def _alarms(obj) -> list[int]:
        out = []
        for alarm in obj.alarms() or []:
            if alarm.absoluteDate() is None:
                out.append(max(0, int(-alarm.relativeOffset() // 60)))
        return out

    # --- fetching ---------------------------------------------------------
    def fetch(self, start: datetime, end: datetime) -> list[Item]:
        items: list[Item] = []
        self.store.refreshSourcesIfNecessary()
        if self.access[ENTITY_EVENT]:
            items.extend(self._events(start, end))
        if self.access[ENTITY_REMINDER]:
            items.extend(self._reminders())
        return items

    def _events(self, start: datetime, end: datetime) -> list[Item]:
        pred = self.store.predicateForEventsWithStartDate_endDate_calendars_(
            self._to_nsdate(start), self._to_nsdate(end), None
        )
        out = []
        for ev in self.store.eventsMatchingPredicate_(pred) or []:
            if ev.status() == EVENT_STATUS_CANCELED:
                continue
            url = ev.URL()
            out.append(
                Item(
                    uid=str(ev.calendarItemExternalIdentifier() or ev.eventIdentifier()),
                    kind=ItemKind.EVENT,
                    title=str(ev.title() or "(No title)"),
                    start=self._to_dt(ev.startDate()),
                    end=self._to_dt(ev.endDate()),
                    all_day=bool(ev.isAllDay()),
                    location=str(ev.location()) if ev.location() else None,
                    notes=str(ev.notes()) if ev.notes() else None,
                    url=str(url.absoluteString()) if url else None,
                    calendar=str(ev.calendar().title()) if ev.calendar() else None,
                    attendees=len(ev.attendees() or []),
                    recurring=bool(ev.hasRecurrenceRules()),
                    alarms_minutes=self._alarms(ev),
                )
            )
        return out

    def _reminders(self) -> list[Item]:
        from Foundation import NSCalendar, NSUndefinedDateComponent

        # All reminders (completed ones are filtered below); unlike the
        # "incomplete with due date" predicate this includes undated reminders.
        pred = self.store.predicateForRemindersInCalendars_(None)
        done, box = threading.Event(), {"reminders": []}

        def handler(reminders):
            box["reminders"] = list(reminders or [])
            done.set()

        self.store.fetchRemindersMatchingPredicate_completion_(pred, handler)
        if not _wait(done, 60):
            raise SourceError("Timed out reading Reminders")

        calendar = NSCalendar.currentCalendar()
        out = []
        for r in box["reminders"]:
            if r.isCompleted():
                continue
            due, all_day = None, False
            comps = r.dueDateComponents()
            if comps is not None:
                due = self._to_dt(calendar.dateFromComponents_(comps))
                all_day = comps.hour() == NSUndefinedDateComponent
            url = r.URL()
            out.append(
                Item(
                    uid=str(r.calendarItemExternalIdentifier() or r.calendarItemIdentifier()),
                    kind=ItemKind.REMINDER,
                    title=str(r.title() or "(No title)"),
                    start=due,
                    all_day=all_day,
                    notes=str(r.notes()) if r.notes() else None,
                    url=str(url.absoluteString()) if url else None,
                    calendar=str(r.calendar().title()) if r.calendar() else None,
                    source_priority=int(r.priority() or 0),
                    recurring=bool(r.hasRecurrenceRules()),
                    alarms_minutes=self._alarms(r),
                )
            )
        return out
