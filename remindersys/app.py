"""The engine: sync, analyse, schedule, notify, summarise."""

from __future__ import annotations

import logging
import threading
import time as _time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from remindersys.config import Config, data_dir
from remindersys.models import AnalyzedItem, Item, ItemKind, PlannedNotification, TravelEstimate
from remindersys.notifier import Notifier
from remindersys.priority import PriorityEngine
from remindersys.scheduler import due_notifications, parse_hhmm, plan
from remindersys.sources import Source, SourceError, create_source, filter_calendars
from remindersys.state import State
from remindersys.summaries import Summary, build_daily, build_weekly
from remindersys.travel import TravelEstimator, is_virtual

log = logging.getLogger(__name__)

TICK_SECONDS = 20
ONLINE_TRAVEL_HORIZON = timedelta(days=7)  # look up real routes for events this close
CHAIN_GAP = timedelta(hours=2)  # leave from the previous event if it ends this soon before
ERROR_NOTIFY_INTERVAL = timedelta(hours=3)


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_week(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


class App:
    def __init__(
        self,
        config: Config,
        state: State,
        notifier: Notifier,
        source: Source | None = None,
        travel: TravelEstimator | None = None,
    ):
        self.config = config
        self.state = state
        self.notifier = notifier
        self._source = source
        self._owns_source = source is None
        self._config_mtime: float | None = None
        self.priority = PriorityEngine(config)
        self.travel = travel or TravelEstimator(config, state.geocode_cache)
        self.items: list[AnalyzedItem] = []
        self.planned: list[PlannedNotification] = []
        self.last_sync: datetime | None = None
        self.last_error: str | None = None
        self._last_error_notified: datetime | None = None
        self._lock = threading.RLock()
        self.stop_event = threading.Event()
        self.sync_requested = threading.Event()
        self._wake = threading.Event()

    @property
    def source(self) -> Source:
        if self._source is None:
            self._source = create_source(self.config)
        return self._source

    # --- analysis -----------------------------------------------------------
    def analyze(self, items: list[Item], now: datetime) -> list[AnalyzedItem]:
        items = filter_calendars(items, self.config.calendars_include, self.config.calendars_exclude)
        analyzed = [AnalyzedItem(i, self.priority.score(i, now)) for i in items if not i.completed]

        physical = sorted(
            (
                a for a in analyzed
                if a.item.kind == ItemKind.EVENT and a.item.is_timed and a.item.location
                and not is_virtual(a.item) and a.item.start > now - timedelta(hours=1)
            ),
            key=lambda a: a.item.start,
        )
        previous: AnalyzedItem | None = None
        for a in physical:
            origin = None
            # Back-to-back events: you'll be leaving from the previous venue, not home.
            if previous and previous.item.end and previous.item.start.date() == a.item.start.date():
                gap = a.item.start - previous.item.end
                if timedelta(0) <= gap <= CHAIN_GAP:
                    origin = previous.item.location
            if a.item.start - now <= ONLINE_TRAVEL_HORIZON:
                a.travel = self.travel.estimate(a.item, origin)
            else:
                a.travel = TravelEstimate(self.config.default_travel_minutes, "default")
            previous = a
        for a in analyzed:
            if a.travel is None:
                a.travel = self.travel.estimate(a.item)  # virtual / no location: no network
        return analyzed

    # --- sync -------------------------------------------------------------
    def reload_config_if_changed(self) -> None:
        """Pick up changes saved by the Settings window without a restart."""
        path = Config.path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if self._config_mtime is None:
            self._config_mtime = mtime
            return
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        log.info("Configuration changed; reloading")
        self.config = Config.load()
        self.priority = PriorityEngine(self.config)
        self.travel = TravelEstimator(self.config, self.state.geocode_cache)
        self.notifier.modal_for_urgent = self.config.modal_alert_for_critical
        self._source = None if self._owns_source else self._source

    def sync(self) -> bool:
        self.reload_config_if_changed()
        now = now_local()
        start = now - timedelta(days=1)
        end = now + timedelta(days=max(self.config.lookahead_days, 8))
        try:
            raw = self.source.fetch(start, end)
        except SourceError as exc:
            self._report_error(str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - keep the background loop alive
            log.exception("Sync failed")
            self._report_error(f"Sync failed: {exc}")
            return False
        analyzed = self.analyze(raw, now)
        with self._lock:
            self.items = analyzed
            self.planned = plan(analyzed, self.config, now)
            self.last_sync = now
            self.last_error = None
        self.state.save()  # persists the geocode cache
        log.info("Synced %d items from %s; %d notifications planned",
                 len(analyzed), self.source.name, len(self.planned))
        return True

    def _report_error(self, message: str) -> None:
        log.error(message)
        self.last_error = message
        now = now_local()
        if self._last_error_notified is None or now - self._last_error_notified > ERROR_NOTIFY_INTERVAL:
            self._last_error_notified = now
            self.notifier.notify("RemindersSys can't read your calendar", message)

    # --- notifications ------------------------------------------------------
    def tick(self, now: datetime | None = None) -> list[PlannedNotification]:
        now = now or now_local()
        with self._lock:
            to_send, to_skip = due_notifications(self.planned, self.state.sent, now, self.config)
            for n in to_send:
                self.notifier.notify(n.title, n.message, urgent=n.urgent)
                self.state.mark_sent(n.key, now)
            for n in to_skip:
                self.state.mark_sent(n.key, now)
        if to_send or to_skip:
            self.state.save()
        return to_send

    # --- summaries ----------------------------------------------------------
    def build_summary(self, kind: str, now: datetime | None = None) -> Summary:
        now = now or now_local()
        with self._lock:
            items = list(self.items)
        builder = build_daily if kind == "daily" else build_weekly
        return builder(items, now, self.config)

    def deliver_summary(self, summary: Summary, open_browser: bool | None = None) -> Path:
        folder = data_dir() / "summaries"
        folder.mkdir(exist_ok=True)
        path = folder / f"{summary.kind}-{summary.generated_at:%Y-%m-%d}.html"
        path.write_text(summary.to_html(), encoding="utf-8")
        self.notifier.notify(summary.title, summary.headline)
        if self.config.open_summary_in_browser if open_browser is None else open_browser:
            try:
                webbrowser.open(path.as_uri())
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not open summary in browser: %s", exc)
        return path

    def maybe_send_summaries(self, startup: bool, now: datetime | None = None) -> list[str]:
        """Send the daily/weekly digest if due. Returns the kinds sent."""
        now = now or now_local()
        if self.last_sync is None:
            return []  # never summarise without data (e.g. no network yet at login)
        sent = []
        fallback = parse_hhmm(self.config.daily_summary_fallback_time, datetime.min.time())
        past_fallback = now.time() >= fallback
        today = now.date().isoformat()

        if self.state.last_daily_summary != today and (
            (startup and self.config.daily_summary_on_startup) or past_fallback
        ):
            self.deliver_summary(self.build_summary("daily", now))
            self.state.last_daily_summary = today
            sent.append("daily")

        week = iso_week(now)
        if (
            self.config.weekly_summary_enabled
            and self.state.last_weekly_summary != week
            and now.weekday() >= self.config.weekly_summary_weekday
            and (startup or past_fallback)
        ):
            self.deliver_summary(self.build_summary("weekly", now))
            self.state.last_weekly_summary = week
            sent.append("weekly")
        if sent:
            self.state.save()
        return sent

    # --- main loop ----------------------------------------------------------
    def run_forever(self) -> None:
        """Blocking loop; call ``stop()`` from another thread to exit."""
        startup_pending = True
        next_sync = 0.0
        last_wall = now_local()
        interval = max(1, self.config.sync_interval_minutes) * 60
        while not self.stop_event.is_set():
            wall = now_local()
            # A large jump in wall-clock time means the machine slept: resync now.
            if wall - last_wall > timedelta(seconds=TICK_SECONDS * 6):
                log.info("Wake from sleep detected")
                next_sync = 0.0
                # Waking up on a new day counts as "startup" for the daily summary
                # (many laptops sleep rather than shut down).
                if wall.date() != last_wall.date():
                    startup_pending = True
            last_wall = wall
            if self.sync_requested.is_set() or _time.monotonic() >= next_sync:
                self.sync_requested.clear()
                ok = self.sync()
                # Retry quickly while offline (network is often not up at login).
                next_sync = _time.monotonic() + (interval if ok else 60)
            try:
                self.tick()
                self.maybe_send_summaries(startup=startup_pending)
            except Exception:  # noqa: BLE001
                log.exception("Tick failed")
            if self.last_sync is not None:
                startup_pending = False
            self._wake.wait(TICK_SECONDS)
            self._wake.clear()

    def request_sync(self) -> None:
        self.sync_requested.set()
        self._wake.set()

    def stop(self) -> None:
        self.stop_event.set()
        self._wake.set()
