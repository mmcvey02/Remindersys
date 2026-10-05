"""Sample data relative to "now", for trying the app without an Apple account."""

from __future__ import annotations

from datetime import datetime, timedelta

from remindersys.models import Item, ItemKind
from remindersys.sources.base import Source


class DemoSource(Source):
    name = "demo"

    def fetch(self, start: datetime, end: datetime) -> list[Item]:
        now = datetime.now().astimezone().replace(second=0, microsecond=0)
        today = now.replace(hour=0, minute=0)

        def at(days: int, hour: int, minute: int = 0) -> datetime:
            return today + timedelta(days=days, hours=hour, minutes=minute)

        items = [
            Item("demo-1", ItemKind.EVENT, "Dentist appointment", now + timedelta(minutes=75),
                 now + timedelta(minutes=135), location="Apple Park Visitor Center, Cupertino, CA",
                 calendar="Personal", alarms_minutes=[60]),
            Item("demo-2", ItemKind.EVENT, "Team standup", now + timedelta(minutes=20),
                 now + timedelta(minutes=35), location="https://zoom.us/j/123456789",
                 calendar="Work", recurring=True, attendees=6),
            Item("demo-3", ItemKind.EVENT, "Flight to Chicago (UA 1234)", at(1, 9, 30), at(1, 13, 45),
                 location="San Francisco International Airport", calendar="Travel"),
            Item("demo-4", ItemKind.EVENT, "Lunch with Sam", at(2, 12, 30), at(2, 13, 30),
                 location="Philz Coffee, Palo Alto", calendar="Personal"),
            Item("demo-5", ItemKind.EVENT, "Quarterly board presentation", at(4, 14), at(4, 15, 30),
                 location="Conference Room A", calendar="Work", attendees=9),
            Item("demo-6", ItemKind.EVENT, "Columbus Day", at(0, 0), at(1, 0), all_day=True,
                 calendar="US Holidays"),
            Item("demo-7", ItemKind.REMINDER, "Pay rent", at(0, 17), calendar="Reminders",
                 source_priority=1),
            Item("demo-8", ItemKind.REMINDER, "Buy groceries", at(0, 18), calendar="Reminders"),
            Item("demo-9", ItemKind.REMINDER, "Do laundry", None, calendar="Reminders"),
            Item("demo-10", ItemKind.REMINDER, "Submit expense report", at(-1, 17), calendar="Work"),
            Item("demo-11", ItemKind.REMINDER, "File taxes - deadline", at(5, 23, 59), calendar="Reminders",
                 source_priority=1),
            Item("demo-12", ItemKind.REMINDER, "Renew passport", None, calendar="Reminders",
                 source_priority=5),
        ]
        return [i for i in items if i.start is None or i.kind == ItemKind.REMINDER or start <= i.start < end]
