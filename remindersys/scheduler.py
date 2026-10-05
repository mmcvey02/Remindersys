"""Turns analysed items into a concrete list of timed notifications."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from remindersys.config import Config
from remindersys.models import AnalyzedItem, ItemKind, PlannedNotification, Tier


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    hours, mins = divmod(minutes, 60)
    return f"{hours} h {mins} min" if mins else f"{hours} h"


def parse_hhmm(value: str, fallback: time) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError):
        return fallback


def in_quiet_hours(when: datetime, config: Config) -> bool:
    start = parse_hhmm(config.quiet_hours_start, time(22, 0))
    end = parse_hhmm(config.quiet_hours_end, time(7, 0))
    t = when.time()
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def quiet_hours_end_after(when: datetime, config: Config) -> datetime:
    end = parse_hhmm(config.quiet_hours_end, time(7, 0))
    candidate = when.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= when:
        candidate += timedelta(days=1)
    return candidate


def departure_time(a: AnalyzedItem, config: Config) -> datetime:
    """When the user must leave (or, for virtual/no-location events, get ready)."""
    start = a.item.start
    travel = a.travel
    if travel and travel.needs_travel:
        return start - timedelta(minutes=travel.minutes + config.arrival_buffer_minutes)
    return start - timedelta(minutes=5)


def _travel_phrase(a: AnalyzedItem) -> str:
    t = a.travel
    if not t or not t.needs_travel:
        return ""
    if t.method == "default":
        return f"~{fmt_minutes(t.minutes)} travel (estimated)"
    if t.method == "onsite":
        return "on-site"
    dist = f", {t.distance_km:g} km" if t.distance_km else ""
    return f"{fmt_minutes(t.minutes)} travel{dist}"


def _where(a: AnalyzedItem) -> str:
    loc = (a.item.location or "").replace("\n", ", ").strip()
    return f" at {loc}" if loc else ""


def plan_item(a: AnalyzedItem, config: Config) -> list[PlannedNotification]:
    item, tier = a.item, a.priority.tier
    if item.completed or item.start is None:
        return []
    if item.kind == ItemKind.EVENT:
        return _plan_event(a, config) if item.is_timed else _plan_all_day(a, config)
    return _plan_reminder(a, config)


def _plan_event(a: AnalyzedItem, config: Config) -> list[PlannedNotification]:
    item, tier = a.item, a.priority.tier
    if tier == Tier.LOW:
        return []
    start = item.start
    leave = departure_time(a, config)
    travel = a.travel is not None and a.travel.needs_travel
    travel_txt = _travel_phrase(a)
    out: list[PlannedNotification] = []

    def add(kind: str, fire_at: datetime, expires: datetime, title: str, msg: str, urgent=False):
        out.append(
            PlannedNotification(
                key=f"{item.key}|{kind}",
                item_key=item.key,
                fire_at=fire_at,
                expires_at=expires,
                title=title,
                message=msg,
                tier=tier,
                urgent=urgent,
            )
        )

    when = f"{start:%a} {fmt_time(start)}"
    if tier == Tier.CRITICAL:
        heads_up = start - timedelta(hours=24)
        detail = f"Leave by {fmt_time(leave)}; {travel_txt}." if travel else ""
        add(
            "headsup",
            heads_up,
            leave - timedelta(hours=2),
            f"Tomorrow: {item.title}",
            f"{when}{_where(a)}. {detail}".strip(),
        )

    prep_lead = {Tier.CRITICAL: 60, Tier.HIGH: 30, Tier.NORMAL: 0}[tier]
    if prep_lead:
        if travel:
            msg = f"Leave in {fmt_minutes(prep_lead)} (by {fmt_time(leave)}) for {fmt_time(start)}{_where(a)}. {travel_txt}."
        else:
            msg = f"Starts at {fmt_time(start)}{_where(a)}."
        add("prep", leave - timedelta(minutes=prep_lead), leave, f"Coming up: {item.title}", msg)

    if travel:
        msg = f"Leave now to arrive by {fmt_time(start)}{_where(a)}. {travel_txt}."
        if tier == Tier.NORMAL:
            # A single alert for routine events, a little before departure.
            add("leave", leave - timedelta(minutes=10), start,
                f"Leave in 10 min: {item.title}",
                f"Leave by {fmt_time(leave)} to arrive at {fmt_time(start)}{_where(a)}. {travel_txt}.")
        else:
            add("leave", leave, start, f"Time to leave: {item.title}", msg, urgent=tier == Tier.CRITICAL)
    else:
        add("start", leave, start + timedelta(minutes=5),
            f"Starting soon: {item.title}", f"Starts at {fmt_time(start)}{_where(a)}.")
    return out


def _plan_all_day(a: AnalyzedItem, config: Config) -> list[PlannedNotification]:
    """All-day items: only critical ones get their own alert (the evening before
    and the morning of); everything else appears in the daily summary."""
    item, tier = a.item, a.priority.tier
    if tier != Tier.CRITICAL:
        return []
    day = item.start.replace(hour=0, minute=0, second=0, microsecond=0)
    morning = quiet_hours_end_after(day - timedelta(minutes=1), config)
    noun = "Due" if item.kind == ItemKind.REMINDER else "Today"
    return [
        PlannedNotification(
            key=f"{item.key}|eve",
            item_key=item.key,
            fire_at=day - timedelta(hours=5),  # 7 PM the evening before
            expires_at=day,
            title=f"Tomorrow: {item.title}",
            message="All day tomorrow. Plan ahead.",
            tier=tier,
        ),
        PlannedNotification(
            key=f"{item.key}|morning",
            item_key=item.key,
            fire_at=morning,
            expires_at=day + timedelta(days=1),
            title=f"{noun}: {item.title}",
            message="Important item for today.",
            tier=tier,
        ),
    ]


def _plan_reminder(a: AnalyzedItem, config: Config) -> list[PlannedNotification]:
    item, tier = a.item, a.priority.tier
    if not item.is_timed:
        return _plan_all_day(a, config)
    # Mundane reminders are left to the daily summary.
    if tier < Tier.HIGH:
        return []
    due = item.start
    leads = [timedelta(hours=24), timedelta(hours=2)] if tier == Tier.CRITICAL else [timedelta(hours=1)]
    out = []
    for lead in leads:
        label = fmt_minutes(int(lead.total_seconds() // 60))
        out.append(
            PlannedNotification(
                key=f"{item.key}|due-{int(lead.total_seconds())}",
                item_key=item.key,
                fire_at=due - lead,
                expires_at=due,
                title=f"Due in {label}: {item.title}",
                message=f"Due {due:%a} {fmt_time(due)}.",
                tier=tier,
            )
        )
    return out


def plan(items: list[AnalyzedItem], config: Config, now: datetime) -> list[PlannedNotification]:
    """Plan all notifications that haven't expired yet, sorted by fire time."""
    out = []
    for a in items:
        for n in plan_item(a, config):
            if n.expires_at > now and n.fire_at < n.expires_at:
                out.append(n)
    out.sort(key=lambda n: n.fire_at)
    return out


def due_notifications(
    planned: list[PlannedNotification], sent: set[str] | dict, now: datetime, config: Config
) -> tuple[list[PlannedNotification], list[PlannedNotification]]:
    """Return (to_send, to_skip).

    When several notifications for the same item are due at once (e.g. the app
    started late), only the most recent is sent; the stale ones are skipped.
    Non-critical notifications are deferred during quiet hours unless they would
    expire first - "leave now" alerts are never held back.
    """
    due_by_item: dict[str, list[PlannedNotification]] = {}
    for n in planned:
        if n.key in sent or n.fire_at > now or n.expires_at <= now:
            continue
        due_by_item.setdefault(n.item_key, []).append(n)

    to_send, to_skip = [], []
    for group in due_by_item.values():
        group.sort(key=lambda n: n.fire_at)
        latest = group[-1]
        if in_quiet_hours(now, config) and latest.tier < Tier.CRITICAL:
            if quiet_hours_end_after(now, config) < latest.expires_at:
                continue  # defer; it will still be relevant in the morning
        to_send.append(latest)
        to_skip.extend(group[:-1])
    return to_send, to_skip
