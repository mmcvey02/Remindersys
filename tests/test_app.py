from datetime import datetime, timedelta

from remindersys.app import App
from remindersys.models import Item, ItemKind
from remindersys.sources.base import Source, SourceError
from remindersys.sources.demo import DemoSource
from remindersys.state import State
from remindersys.travel import TravelEstimator


class FakeNotifier:
    def __init__(self):
        self.sent = []
        self.modal_for_urgent = False

    def notify(self, title, message, urgent=False):
        self.sent.append((title, message, urgent))
        return True


class ListSource(Source):
    name = "list"

    def __init__(self, items):
        self.items = items

    def fetch(self, start, end):
        return list(self.items)


class BrokenSource(Source):
    name = "broken"

    def fetch(self, start, end):
        raise SourceError("no network")


def make_app(config, source, tmp_path):
    config.open_summary_in_browser = False
    return App(config, State(tmp_path / "state.json"), FakeNotifier(), source,
               TravelEstimator(config, {}, online=False))


def test_demo_end_to_end(config, tmp_path):
    app = make_app(config, DemoSource(), tmp_path)
    assert app.sync()
    assert app.items and app.planned
    summary = app.build_summary("daily")
    assert summary.sections


def test_tick_sends_once_and_persists(config, tmp_path):
    now = datetime.now().astimezone()
    item = Item("x", ItemKind.EVENT, "Job interview", now + timedelta(minutes=20),
                now + timedelta(minutes=80), location="123 Main St, Springfield")
    app = make_app(config, ListSource([item]), tmp_path)
    app.sync()
    sent = app.tick(now + timedelta(minutes=1))
    assert len(sent) == 1 and app.notifier.sent[0][0].startswith("Time to leave")
    assert app.tick(now + timedelta(minutes=2)) == []
    # Survives a restart.
    assert State(tmp_path / "state.json").was_sent(sent[0].key)


def test_back_to_back_events_chain_origin(config, tmp_path):
    now = datetime.now().astimezone().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    first = Item("a", ItemKind.EVENT, "Doctor", now, now + timedelta(hours=1), location="Clinic, 5 Elm St, Town")
    second = Item("b", ItemKind.EVENT, "Lunch", now + timedelta(hours=1, minutes=30),
                  now + timedelta(hours=2, minutes=30), location="Cafe, 9 Oak St, Town")
    app = make_app(config, ListSource([first, second]), tmp_path)
    app.sync()
    by_title = {x.item.title: x for x in app.items}
    assert by_title["Lunch"].travel.origin == first.location
    assert by_title["Doctor"].travel.origin == config.home_address


def test_summaries_on_startup_once_per_day_and_week(config, tmp_path):
    app = make_app(config, DemoSource(), tmp_path)
    monday = datetime(2026, 10, 5, 6, 30).astimezone()
    assert app.maybe_send_summaries(startup=True, now=monday) == []  # no data yet
    app.sync()
    assert app.maybe_send_summaries(startup=True, now=monday) == ["daily", "weekly"]
    assert app.maybe_send_summaries(startup=True, now=monday + timedelta(hours=2)) == []
    tuesday_early = monday + timedelta(days=1)
    assert app.maybe_send_summaries(startup=False, now=tuesday_early) == []  # before fallback time
    assert app.maybe_send_summaries(startup=False, now=tuesday_early + timedelta(hours=2)) == ["daily"]
    assert (tmp_path / "summaries" / "daily-2026-10-06.html").exists()


def test_weekly_respects_configured_day(config, tmp_path):
    config.weekly_summary_weekday = 4  # Friday
    app = make_app(config, DemoSource(), tmp_path)
    app.sync()
    monday = datetime(2026, 10, 5, 9, 0).astimezone()
    assert app.maybe_send_summaries(startup=True, now=monday) == ["daily"]
    assert app.maybe_send_summaries(startup=True, now=monday + timedelta(days=4)) == ["daily", "weekly"]


def test_sync_error_is_reported_not_raised(config, tmp_path):
    app = make_app(config, BrokenSource(), tmp_path)
    assert not app.sync()
    assert app.last_error == "no network"
    assert len(app.notifier.sent) == 1
    app.sync()
    assert len(app.notifier.sent) == 1  # rate-limited
