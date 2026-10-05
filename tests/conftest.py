from datetime import datetime, timedelta

import pytest

from remindersys.config import Config
from remindersys.models import Item, ItemKind


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("REMINDERSYS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def config():
    return Config(use_online_routing=False, home_address="1 Infinite Loop, Cupertino",
                  quiet_hours_start="22:00", quiet_hours_end="07:00")


@pytest.fixture
def now():
    # A Monday morning.
    return datetime(2026, 10, 5, 9, 0).astimezone()


def event(title, start, minutes=60, **kw):
    return Item(uid=title, kind=ItemKind.EVENT, title=title, start=start,
                end=start + timedelta(minutes=minutes), **kw)


def reminder(title, due=None, **kw):
    return Item(uid=title, kind=ItemKind.REMINDER, title=title, start=due, **kw)
