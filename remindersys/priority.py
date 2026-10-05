"""Heuristic priority scoring.

Every item gets a score from 0 to 100 built from explainable signals (keywords,
explicit priority, attendees, location, recurrence, calendar...). The score maps
to a tier, and the tier decides how aggressively the user is notified:

* CRITICAL - early heads-up, a "get ready" nudge and a "leave now" alert.
* HIGH     - a "get ready" nudge and a "leave now" alert.
* NORMAL   - events get a single timely alert; reminders go in the daily summary.
* LOW      - daily summary only.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from remindersys.config import Config
from remindersys.models import Item, ItemKind, PriorityResult, Tier
from remindersys.travel import is_virtual

TIER_THRESHOLDS = [(75, Tier.CRITICAL), (55, Tier.HIGH), (35, Tier.NORMAL)]

# Keyword -> weight. Matched as whole words/phrases, case-insensitively.
HIGH_KEYWORDS: dict[str, int] = {
    # Hard-to-reschedule, costly to miss.
    "flight": 35, "airport": 30, "boarding": 30, "train": 15, "surgery": 35,
    "exam": 30, "final": 15, "midterm": 30, "interview": 35, "court": 35,
    "hearing": 25, "wedding": 30, "funeral": 30, "graduation": 25,
    "closing": 20, "visa": 25, "passport": 20, "jury": 30,
    # Health.
    "doctor": 25, "dr": 20, "dentist": 25, "appointment": 20, "appt": 20,
    "hospital": 25, "clinic": 20, "therapy": 15, "vaccine": 15, "vet": 15,
    # Money and deadlines.
    "deadline": 30, "due": 15, "submit": 15, "tax": 25, "taxes": 25,
    "rent": 25, "mortgage": 25, "payment": 20, "pay": 10, "bill": 15,
    "invoice": 15, "renew": 15, "expires": 20, "expiry": 20,
    # Work.
    "presentation": 25, "demo": 15, "pitch": 25, "review": 10, "client": 15,
    "board": 15, "1:1": 10, "launch": 20, "urgent": 35, "important": 25,
    "asap": 30, "!!": 20,
    # People.
    "pick up": 20, "pickup": 20, "drop off": 15, "school": 10, "recital": 20,
    "birthday party": 15, "anniversary": 20,
}

LOW_KEYWORDS: dict[str, int] = {
    "groceries": 15, "grocery": 15, "laundry": 15, "clean": 10, "tidy": 15,
    "dishes": 15, "vacuum": 15, "water plants": 15, "maybe": 15, "someday": 20,
    "idea": 10, "read": 10, "watch": 10, "browse": 15, "optional": 20,
    "tentative": 10, "fyi": 15, "lunch": 5, "coffee": 5, "gym": 5, "workout": 5,
}

# Calendar/list names that are usually informational.
DEFAULT_CALENDAR_WEIGHTS: dict[str, int] = {
    "holiday": -35,
    "birthdays": -25,
    "siri suggestions": -20,
    "found in": -15,
    "scheduled reminders": -10,
    "work": 5,
}


def _compile(words: dict[str, int]) -> list[tuple[re.Pattern[str], str, int]]:
    out = []
    for word, weight in words.items():
        if word.isalnum() or " " in word:
            pattern = re.compile(rf"(?<![\w]){re.escape(word)}(?![\w])", re.IGNORECASE)
        else:  # punctuation-heavy tokens like "!!" or "1:1"
            pattern = re.compile(re.escape(word), re.IGNORECASE)
        out.append((pattern, word, weight))
    return out


class PriorityEngine:
    def __init__(self, config: Config):
        self.config = config
        high = dict(HIGH_KEYWORDS)
        high.update({k.lower(): 30 for k in config.extra_high_priority_keywords})
        low = dict(LOW_KEYWORDS)
        low.update({k.lower(): 20 for k in config.extra_low_priority_keywords})
        self._high = _compile(high)
        self._low = _compile(low)
        # User-defined weights are checked before the built-in ones.
        self._calendar_weights = {k.lower(): v for k, v in config.calendar_weights.items()}
        for name, weight in DEFAULT_CALENDAR_WEIGHTS.items():
            self._calendar_weights.setdefault(name, weight)

    def score(self, item: Item, now: datetime) -> PriorityResult:
        reasons: list[str] = []
        score = 35 if item.kind == ItemKind.EVENT else 30

        # Explicit priority set by the user always matters most.
        if 1 <= item.source_priority <= 4:
            score += 30
            reasons.append("marked high priority")
        elif item.source_priority == 5:
            score += 12
            reasons.append("marked medium priority")
        elif item.source_priority >= 6:
            score -= 10
            reasons.append("marked low priority")
        if item.flagged:
            score += 15
            reasons.append("flagged")

        # Keywords: take the strongest match rather than summing so long notes
        # don't inflate scores. Title matches count fully, notes count half.
        title = item.title or ""
        notes = item.notes or ""
        best_high, best_word = 0, None
        for pattern, word, weight in self._high:
            if pattern.search(title):
                hit = weight
            elif pattern.search(notes):
                hit = weight // 2
            else:
                continue
            if hit > best_high:
                best_high, best_word = hit, word
        if best_high:
            score += best_high
            reasons.append(f'mentions "{best_word}"')
        best_low = max(
            (w for p, _, w in self._low if p.search(title)), default=0
        )
        if best_low and not best_high:
            score -= best_low
            reasons.append("routine task")

        if item.kind == ItemKind.EVENT:
            if item.location and not is_virtual(item):
                score += 10
                reasons.append("requires travel")
            elif is_virtual(item):
                score += 3
            if item.attendees:
                bump = min(item.attendees * 2, 10)
                score += bump
                reasons.append(f"{item.attendees} attendee(s)")
            if item.all_day:
                score -= 12
            duration = item.duration
            if duration and duration <= timedelta(minutes=15) and not item.location:
                score -= 5
            if item.alarms_minutes:
                score += 5
                reasons.append("has an alert set")

        if item.recurring:
            score -= 10
            reasons.append("recurring")

        if item.kind == ItemKind.REMINDER and item.start is not None:
            if item.start < now:
                score += 10
                reasons.append("overdue")
            elif item.start - now <= timedelta(hours=24):
                score += 5

        cal = (item.calendar or "").lower()
        for name, weight in self._calendar_weights.items():
            if name and name in cal:
                score += weight
                if weight:
                    reasons.append(f'calendar "{item.calendar}" ({weight:+d})')
                break

        score = max(0, min(100, score))
        tier = next((t for threshold, t in TIER_THRESHOLDS if score >= threshold), Tier.LOW)
        return PriorityResult(score=score, tier=tier, reasons=reasons)
