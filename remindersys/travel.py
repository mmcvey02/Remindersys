"""Travel-time estimation so "leave now" alerts fire early enough.

Strategy, from most to least accurate:
1. Geocode both ends with OpenStreetMap Nominatim and, for driving, get a road
   route duration from the public OSRM server. A rush-hour factor is applied.
2. If routing fails but geocoding worked, estimate from straight-line distance.
3. If the location can't be resolved, fall back to ``default_travel_minutes``.
Virtual meetings (Zoom/Teams/Meet links, "online", "phone") need no travel.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from remindersys import __version__
from remindersys.config import Config
from remindersys.models import Item, TravelEstimate

log = logging.getLogger(__name__)

USER_AGENT = f"RemindersSys/{__version__} (desktop reminder app)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{a};{b}?overview=false"

VIRTUAL_RE = re.compile(
    r"zoom\.us|teams\.microsoft|teams\.live|meet\.google|webex|whereby\.com|"
    r"gotomeeting|skype|discord\.gg|facetime|chime\.aws|bluejeans|"
    r"^\s*(online|virtual|remote|phone|call|video call|tbd|n/?a)\s*$",
    re.IGNORECASE,
)

# Rooms inside a building you're presumably already in ("Conference Room A", "Office 3B").
ONSITE_RE = re.compile(r"^[^,\d]*\b(room|conf|conference|boardroom|office|desk|floor|lobby|cafeteria)\b[^,]*$", re.IGNORECASE)
ONSITE_MINUTES = 5
OFFLINE_BACKOFF_SECONDS = 600

# Average door-to-door speeds (km/h) and road-detour factors per mode.
MODE_SPEED_KMH = {"driving": 40.0, "walking": 4.8, "cycling": 15.0, "transit": 22.0}
DETOUR_FACTOR = 1.3
TRANSIT_WAIT_MINUTES = 8


def is_virtual(item: Item) -> bool:
    location = (item.location or "").strip()
    if location:
        return bool(VIRTUAL_RE.search(location)) or location.lower().startswith("http")
    # No location: treat as virtual if the notes/url carry a meeting link.
    return bool(VIRTUAL_RE.search(item.url or "") or VIRTUAL_RE.search(item.notes or ""))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def rush_hour_factor(when: datetime) -> float:
    """Driving takes longer in weekday rush hours."""
    if when.weekday() < 5:
        minutes = when.hour * 60 + when.minute
        if 7 * 60 <= minutes <= 9 * 60 + 30 or 16 * 60 <= minutes <= 19 * 60:
            return 1.4
    return 1.1


def _normalise(address: str) -> str:
    # Apple Calendar often stores "Place Name\n123 Street, City" - keep it all on one line.
    return re.sub(r"\s+", " ", address.replace("\n", ", ")).strip(" ,")


class TravelEstimator:
    def __init__(self, config: Config, geocode_cache: dict | None = None, online: bool | None = None):
        self.config = config
        self.geocode_cache = geocode_cache if geocode_cache is not None else {}
        self.online = config.use_online_routing if online is None else online
        self._route_cache: dict[tuple, float | None] = {}
        self._lock = threading.Lock()
        self._last_nominatim = 0.0
        self._offline_until = 0.0  # skip network calls for a while after a failure

    # --- network helpers -------------------------------------------------
    def _network_ok(self) -> bool:
        return self.online and time.monotonic() >= self._offline_until

    def _mark_offline(self) -> None:
        self._offline_until = time.monotonic() + OFFLINE_BACKOFF_SECONDS

    def _get_json(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def geocode(self, address: str) -> tuple[float, float] | None:
        address = _normalise(address)
        if not address:
            return None
        if address in self.geocode_cache:
            cached = self.geocode_cache[address]
            return tuple(cached) if cached else None
        if not self._network_ok():
            return None
        coords = None
        # Try the full string, then progressively drop the leading part
        # (usually a venue name Nominatim doesn't know).
        parts = [p.strip() for p in address.split(",") if p.strip()]
        candidates = [", ".join(parts[i:]) for i in range(min(len(parts), 3))] or [address]
        for query in candidates:
            with self._lock:  # Nominatim policy: max 1 request per second.
                wait = 1.1 - (time.monotonic() - self._last_nominatim)
                if wait > 0:
                    time.sleep(wait)
                self._last_nominatim = time.monotonic()
            try:
                url = NOMINATIM_URL + "?" + urllib.parse.urlencode(
                    {"q": query, "format": "json", "limit": 1}
                )
                results = self._get_json(url)
            except Exception as exc:  # noqa: BLE001 - network errors are non-fatal
                log.warning("Geocoding failed for %r: %s", query, exc)
                self._mark_offline()
                return None  # don't cache: may be a transient outage
            if results:
                coords = (float(results[0]["lat"]), float(results[0]["lon"]))
                break
        self.geocode_cache[address] = list(coords) if coords else None
        return coords

    def _route_minutes(self, a: tuple[float, float], b: tuple[float, float]) -> float | None:
        key = (round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4))
        if key in self._route_cache:
            return self._route_cache[key]
        if not self._network_ok():
            return None
        minutes = None
        try:
            url = OSRM_URL.format(a=f"{a[1]},{a[0]}", b=f"{b[1]},{b[0]}")
            data = self._get_json(url)
            if data.get("code") == "Ok" and data.get("routes"):
                minutes = data["routes"][0]["duration"] / 60.0
        except Exception as exc:  # noqa: BLE001
            log.warning("Routing failed: %s", exc)
            self._mark_offline()
            return None
        self._route_cache[key] = minutes
        return minutes

    # --- public API -------------------------------------------------------
    def estimate(self, item: Item, origin: str | None = None) -> TravelEstimate:
        if not item.is_timed:
            return TravelEstimate(0, "none")
        if is_virtual(item):
            return TravelEstimate(0, "virtual")
        if not (item.location or "").strip():
            return TravelEstimate(0, "none")

        cfg = self.config
        if ONSITE_RE.match(_normalise(item.location)):
            return TravelEstimate(ONSITE_MINUTES, "onsite")
        origin = origin or cfg.home_address
        mode = cfg.travel_mode if cfg.travel_mode in MODE_SPEED_KMH else "driving"
        dest_xy = self.geocode(item.location)
        origin_xy = self.geocode(origin) if origin else None
        if not dest_xy or not origin_xy:
            return TravelEstimate(cfg.default_travel_minutes, "default", origin=origin)

        distance = haversine_km(origin_xy, dest_xy) * DETOUR_FACTOR
        method = "distance"
        minutes: float | None = None
        if mode == "driving" and self.online:
            minutes = self._route_minutes(origin_xy, dest_xy)
            if minutes is not None:
                method = "route"
        if minutes is None:
            minutes = distance / MODE_SPEED_KMH[mode] * 60
        if mode == "driving":
            minutes = minutes * rush_hour_factor(item.start) + cfg.parking_minutes
        elif mode == "transit":
            minutes += TRANSIT_WAIT_MINUTES
        # Round up to 5 minutes; anything under 2 km still gets a few minutes.
        rounded = max(5, int(math.ceil(minutes / 5.0) * 5))
        return TravelEstimate(rounded, method, distance_km=round(distance, 1), origin=origin)
