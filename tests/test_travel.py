from datetime import datetime, timedelta

from remindersys.models import Item, ItemKind
from remindersys.travel import TravelEstimator, haversine_km, is_virtual, rush_hour_factor
from tests.conftest import event


def test_virtual_detection():
    assert is_virtual(Item("1", ItemKind.EVENT, "x", None, location="https://zoom.us/j/1"))
    assert is_virtual(Item("1", ItemKind.EVENT, "x", None, location="Microsoft Teams Meeting teams.microsoft.com"))
    assert is_virtual(Item("1", ItemKind.EVENT, "x", None, location="Online"))
    assert is_virtual(Item("1", ItemKind.EVENT, "x", None, notes="Join: https://meet.google.com/abc"))
    assert not is_virtual(Item("1", ItemKind.EVENT, "x", None, location="123 Main St, Springfield"))
    assert not is_virtual(Item("1", ItemKind.EVENT, "x", None, location="Phoenix Coffee"))


def test_haversine():
    sf, la = (37.7749, -122.4194), (34.0522, -118.2437)
    assert 540 < haversine_km(sf, la) < 570


def test_rush_hour():
    monday_8am = datetime(2026, 10, 5, 8, 0)
    sunday_8am = datetime(2026, 10, 4, 8, 0)
    assert rush_hour_factor(monday_8am) > rush_hour_factor(sunday_8am)


def test_estimate_from_cached_coordinates(config, now):
    cache = {
        "1 Infinite Loop, Cupertino": [37.3318, -122.0312],
        "Stanford Hospital, Palo Alto": [37.4337, -122.1750],
    }
    est = TravelEstimator(config, cache).estimate(
        event("Doctor", now + timedelta(hours=3), location="Stanford Hospital\nPalo Alto")
    )
    assert est.method == "distance"
    assert 20 <= est.minutes <= 60
    assert est.minutes % 5 == 0


def test_unknown_location_uses_default(config, now):
    est = TravelEstimator(config, {}).estimate(event("Party", now + timedelta(hours=3), location="Somewhere odd"))
    assert est.method == "default"
    assert est.minutes == config.default_travel_minutes


def test_onsite_room_and_virtual(config, now):
    est = TravelEstimator(config).estimate(event("Sync", now, location="Conference Room B"))
    assert est.method == "onsite"
    est = TravelEstimator(config).estimate(event("Sync", now, location="https://zoom.us/j/9"))
    assert est.method == "virtual" and est.minutes == 0
