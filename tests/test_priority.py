from datetime import timedelta

from remindersys.models import Tier
from remindersys.priority import PriorityEngine
from tests.conftest import event, reminder


def tier(config, item, now):
    return PriorityEngine(config).score(item, now).tier


def test_high_stakes_events_are_critical(config, now):
    flight = event("Flight to Denver", now + timedelta(days=1), location="SFO Airport")
    interview = event("Job interview at Acme", now + timedelta(hours=5), location="100 Main St, Springfield")
    assert tier(config, flight, now) == Tier.CRITICAL
    assert tier(config, interview, now) == Tier.CRITICAL


def test_chores_are_low(config, now):
    assert tier(config, reminder("Do laundry"), now) == Tier.LOW
    assert tier(config, reminder("Buy groceries", now + timedelta(hours=8)), now) == Tier.LOW


def test_explicit_priority_wins(config, now):
    plain = reminder("Call the bank", now + timedelta(days=2))
    flagged = reminder("Call the bank", now + timedelta(days=2), source_priority=1)
    assert tier(config, plain, now) < tier(config, flagged, now)
    assert tier(config, flagged, now) >= Tier.HIGH


def test_holiday_calendar_and_recurrence_lower_priority(config, now):
    holiday = event("Columbus Day", now, all_day=True, calendar="US Holidays")
    standup = event("Standup", now + timedelta(hours=1), recurring=True, location="https://zoom.us/j/1")
    assert tier(config, holiday, now) == Tier.LOW
    assert tier(config, standup, now) <= Tier.NORMAL


def test_keywords_match_whole_words(config, now):
    engine = PriorityEngine(config)
    # "exam" must not match inside "example", nor "pay" inside "paycheck".
    assert not any('"exam"' in r for r in engine.score(reminder("Read example code"), now).reasons)
    assert not any('"pay"' in r for r in engine.score(reminder("Paycheck party"), now).reasons)
    assert any('"pay"' in r for r in engine.score(reminder("Pay electric"), now).reasons)


def test_user_keywords_and_calendar_weights(config, now):
    config.extra_high_priority_keywords = ["piano"]
    config.calendar_weights = {"Kids": 25}
    engine = PriorityEngine(config)
    assert engine.score(event("Piano lesson", now + timedelta(hours=3)), now).tier >= Tier.HIGH
    kid = engine.score(event("Soccer", now + timedelta(hours=3), calendar="Kids"), now)
    assert any("Kids" in r for r in kid.reasons)


def test_overdue_reminder_gets_boost(config, now):
    engine = PriorityEngine(config)
    late = engine.score(reminder("Submit report", now - timedelta(days=1)), now)
    later = engine.score(reminder("Submit report", now + timedelta(days=3)), now)
    assert late.score > later.score
    assert "overdue" in late.reasons
