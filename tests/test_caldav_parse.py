from datetime import date, datetime

from icalendar import Calendar

from remindersys.models import ItemKind
from remindersys.sources.caldav_source import parse_vevent, parse_vtodo, to_local

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:ev-1
DTSTART:20261006T160000Z
DTEND:20261006T170000Z
SUMMARY:Dentist
LOCATION:123 Main St\\nSpringfield
ATTENDEE:mailto:a@example.com
ATTENDEE:mailto:b@example.com
BEGIN:VALARM
TRIGGER:-PT30M
ACTION:DISPLAY
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:ev-2
DTSTART;VALUE=DATE:20261012
SUMMARY:Holiday
END:VEVENT
BEGIN:VEVENT
UID:ev-3
DTSTART:20261006T090000
SUMMARY:Cancelled thing
STATUS:CANCELLED
END:VEVENT
BEGIN:VTODO
UID:todo-1
SUMMARY:Pay rent
DUE:20261007T170000Z
PRIORITY:1
END:VTODO
BEGIN:VTODO
UID:todo-2
SUMMARY:Done already
STATUS:COMPLETED
END:VTODO
BEGIN:VTODO
UID:todo-3
SUMMARY:Someday
END:VTODO
END:VCALENDAR
"""


def components(kind):
    return list(Calendar.from_ical(ICS).walk(kind))


def test_parse_events():
    ev1, ev2, ev3 = [parse_vevent(c, "Home") for c in components("VEVENT")]
    assert ev1.kind == ItemKind.EVENT and ev1.title == "Dentist"
    assert ev1.start == datetime(2026, 10, 6, 16, 0).replace(tzinfo=__import__("datetime").timezone.utc)
    assert ev1.start.tzinfo is not None
    assert ev1.attendees == 2 and ev1.alarms_minutes == [30]
    assert "Springfield" in ev1.location
    assert ev1.calendar == "Home"
    assert ev2.all_day and ev2.start.date() == date(2026, 10, 12)
    assert ev3 is None


def test_parse_todos():
    todos = [parse_vtodo(c, "Reminders") for c in components("VTODO")]
    rent, done, someday = todos
    assert rent.kind == ItemKind.REMINDER and rent.source_priority == 1 and not rent.all_day
    assert done is None
    assert someday.start is None


def test_floating_time_is_local():
    dt, all_day = to_local(datetime(2026, 1, 1, 9, 0))
    assert dt.tzinfo is not None and dt.hour == 9 and not all_day
