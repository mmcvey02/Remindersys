from datetime import timedelta

from remindersys.models import AnalyzedItem, PriorityResult, Tier, TravelEstimate
from remindersys.summaries import build_daily, build_weekly
from tests.conftest import event, reminder


def a(item, tier=Tier.NORMAL, travel=None):
    return AnalyzedItem(item, PriorityResult(50, tier), travel or TravelEstimate(0, "none"))


def section(summary, heading):
    return [x.item.title for s in summary.sections if s.heading == heading for x in s.rows]


def test_daily_summary_groups(config, now):
    items = [
        a(event("Dentist", now + timedelta(hours=3), location="Main St"), Tier.HIGH, TravelEstimate(20, "route")),
        a(event("Holiday", now.replace(hour=0), all_day=True), Tier.LOW),
        a(reminder("Groceries", now + timedelta(hours=8)), Tier.LOW),
        a(reminder("Expense report", now - timedelta(days=2)), Tier.HIGH),
        a(reminder("Renew passport"), Tier.HIGH),
        a(reminder("Someday: learn piano"), Tier.LOW),
        a(event("Flight", now + timedelta(days=1)), Tier.CRITICAL),
        a(event("Next week", now + timedelta(days=6)), Tier.CRITICAL),
    ]
    s = build_daily(items, now, config)
    assert section(s, "Today's schedule") == ["Dentist"]
    assert section(s, "All-day") == ["Holiday"]
    assert section(s, "Reminders due today") == ["Groceries"]
    assert section(s, "Overdue") == ["Expense report"]
    assert section(s, "Important, no due date") == ["Renew passport"]
    assert section(s, "Heads-up for tomorrow") == ["Flight"]
    assert "1 event" in s.headline and "1 overdue" in s.headline
    html = s.to_html()
    assert "leave by" in html and "Dentist" in html
    assert "Someday" not in html
    assert "overdue by 2 day(s)" in s.to_text()


def test_html_is_escaped(config, now):
    s = build_daily([a(event("<script>x</script>", now + timedelta(hours=1)))], now, config)
    assert "<script>x" not in s.to_html()


def test_weekly_only_major_items(config, now):
    items = [
        a(event("Board presentation", now + timedelta(days=3)), Tier.CRITICAL),
        a(reminder("Taxes", now + timedelta(days=5)), Tier.HIGH),
        a(event("Coffee", now + timedelta(days=2)), Tier.NORMAL),
        a(event("Too far", now + timedelta(days=9)), Tier.CRITICAL),
    ]
    s = build_weekly(items, now, config)
    titles = [x.item.title for sec in s.sections for x in sec.rows]
    assert titles == ["Board presentation", "Taxes"]
    assert s.headline.startswith("2 major items this week, plus 1 routine")


def test_empty_summary(config, now):
    s = build_daily([], now, config)
    assert s.is_empty()
    assert "Nothing scheduled" in s.to_html()
