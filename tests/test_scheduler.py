from datetime import timedelta

from remindersys.models import AnalyzedItem, PriorityResult, Tier, TravelEstimate
from remindersys.scheduler import departure_time, due_notifications, in_quiet_hours, plan
from tests.conftest import event, reminder


def analyzed(item, tier, travel=None):
    return AnalyzedItem(item, PriorityResult(50, tier), travel or TravelEstimate(0, "none"))


def kinds(notifications):
    return [n.key.rsplit("|", 1)[1] for n in notifications]


def test_departure_accounts_for_travel_and_buffer(config, now):
    a = analyzed(event("Dentist", now + timedelta(hours=4), location="x"), Tier.HIGH, TravelEstimate(25, "route"))
    assert departure_time(a, config) == now + timedelta(hours=4) - timedelta(minutes=25 + config.arrival_buffer_minutes)


def test_critical_event_gets_three_alerts(config, now):
    a = analyzed(event("Flight", now + timedelta(days=2), location="SFO"), Tier.CRITICAL, TravelEstimate(40, "route"))
    planned = plan([a], config, now)
    assert kinds(planned) == ["headsup", "prep", "leave"]
    leave = planned[-1]
    assert leave.urgent
    assert leave.fire_at == departure_time(a, config)


def test_normal_event_gets_single_early_alert(config, now):
    a = analyzed(event("Lunch", now + timedelta(hours=4), location="Cafe"), Tier.NORMAL, TravelEstimate(15, "route"))
    planned = plan([a], config, now)
    assert kinds(planned) == ["leave"]
    assert planned[0].fire_at == departure_time(a, config) - timedelta(minutes=10)


def test_low_items_and_mundane_reminders_are_summary_only(config, now):
    items = [
        analyzed(event("Holiday", now + timedelta(hours=4)), Tier.LOW),
        analyzed(reminder("Laundry", now + timedelta(hours=4)), Tier.NORMAL),
        analyzed(reminder("Laundry"), Tier.LOW),
    ]
    assert plan(items, config, now) == []


def test_important_reminder_gets_lead_time(config, now):
    planned = plan([analyzed(reminder("Pay rent", now + timedelta(hours=30)), Tier.CRITICAL)], config, now)
    assert [n.fire_at for n in planned] == [now + timedelta(hours=6), now + timedelta(hours=28)]


def test_expired_notifications_are_dropped(config, now):
    a = analyzed(event("Past", now - timedelta(hours=1)), Tier.CRITICAL)
    assert plan([a], config, now) == []


def test_catch_up_sends_only_latest_per_item(config, now):
    # App was off: both the 24 h and 2 h warnings for this reminder are now due.
    a = analyzed(reminder("Submit thesis", now + timedelta(hours=1)), Tier.CRITICAL)
    planned = plan([a], config, now - timedelta(days=2))
    to_send, to_skip = due_notifications(planned, set(), now, config)
    assert kinds(to_send) == ["due-7200"]
    assert kinds(to_skip) == ["due-86400"]


def test_late_start_still_gets_leave_alert(config, now):
    a = analyzed(event("Meeting", now + timedelta(minutes=20), location="x"), Tier.CRITICAL, TravelEstimate(15, "route"))
    planned = plan([a], config, now - timedelta(days=2))
    to_send, _ = due_notifications(planned, set(), now, config)
    assert kinds(to_send) == ["leave"]


def test_already_sent_not_repeated(config, now):
    a = analyzed(event("Meeting", now + timedelta(minutes=20), location="x"), Tier.HIGH, TravelEstimate(15, "route"))
    planned = plan([a], config, now - timedelta(hours=1))
    to_send, _ = due_notifications(planned, {n.key for n in planned}, now, config)
    assert to_send == []


def test_quiet_hours(config, now):
    night = now.replace(hour=23)
    assert in_quiet_hours(night, config)
    assert in_quiet_hours(now.replace(hour=6, minute=59), config)
    assert not in_quiet_hours(now, config)
    # A HIGH reminder heads-up due at night is deferred to morning...
    r = analyzed(reminder("Submit grant", night + timedelta(hours=10)), Tier.HIGH)
    planned = plan([r], config, night - timedelta(hours=1))
    late = night.replace(hour=23, minute=30) + timedelta(hours=8, minutes=30)  # 8:00 next day
    assert due_notifications(planned, set(), late - timedelta(hours=1), config)[0] == []
    # ...but a critical "leave now" is not.
    e = analyzed(event("Red-eye flight", night + timedelta(minutes=50), location="SFO"), Tier.CRITICAL,
                 TravelEstimate(30, "route"))
    sent, _ = due_notifications(plan([e], config, night - timedelta(hours=3)), set(), night + timedelta(minutes=11), config)
    assert kinds(sent) == ["leave"]


def test_all_day_critical_gets_evening_and_morning(config, now):
    day = now.replace(hour=0) + timedelta(days=2)
    a = analyzed(event("Bar exam", day, minutes=24 * 60, all_day=True), Tier.CRITICAL)
    planned = plan([a], config, now)
    assert kinds(planned) == ["eve", "morning"]
    assert planned[0].fire_at.hour == 19
    assert planned[1].fire_at.hour == 7
