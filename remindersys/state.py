"""Persistent runtime state: which notifications were sent, when summaries ran, caches."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from remindersys.config import data_dir

log = logging.getLogger(__name__)

SENT_RETENTION = timedelta(days=30)


class State:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "state.json"
        self._lock = threading.Lock()
        self.sent: dict[str, str] = {}
        self.last_daily_summary: str | None = None  # ISO date
        self.last_weekly_summary: str | None = None  # ISO year-week, e.g. "2026-W41"
        self.first_run_done: bool = False
        self.geocode_cache: dict[str, list[float] | None] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("State file unreadable (%s); starting fresh", exc)
            return
        self.sent = raw.get("sent", {})
        self.last_daily_summary = raw.get("last_daily_summary")
        self.last_weekly_summary = raw.get("last_weekly_summary")
        self.first_run_done = raw.get("first_run_done", False)
        self.geocode_cache = raw.get("geocode_cache", {})

    def save(self) -> None:
        with self._lock:
            self._prune()
            payload = {
                "sent": self.sent,
                "last_daily_summary": self.last_daily_summary,
                "last_weekly_summary": self.last_weekly_summary,
                "first_run_done": self.first_run_done,
                "geocode_cache": self.geocode_cache,
            }
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)

    def _prune(self) -> None:
        cutoff = datetime.now().astimezone() - SENT_RETENTION
        self.sent = {
            k: v for k, v in self.sent.items() if datetime.fromisoformat(v) >= cutoff
        }

    def was_sent(self, key: str) -> bool:
        return key in self.sent

    def mark_sent(self, key: str, when: datetime) -> None:
        with self._lock:
            self.sent[key] = when.isoformat()
