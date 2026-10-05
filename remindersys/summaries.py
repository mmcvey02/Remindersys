"""Daily and weekly digest generation (notification text + a readable HTML page)."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from remindersys.config import Config
from remindersys.models import AnalyzedItem, ItemKind, Tier
from remindersys.scheduler import departure_time, fmt_minutes, fmt_time


@dataclass
class Section:
    heading: str
    rows: list[AnalyzedItem] = field(default_factory=list)


@dataclass
class Summary:
    kind: str  # "daily" | "weekly"
    title: str
    headline: str  # short text for the notification body
    sections: list[Section]
    generated_at: datetime
    config: Config

    def is_empty(self) -> bool:
        return not any(s.rows for s in self.sections)

    # --- rendering ---------------------------------------------------------
    def _describe(self, a: AnalyzedItem, with_day: bool) -> tuple[str, str, str]:
        """Return (when, title, detail) for one row."""
        item = a.item
        if item.start is None:
            when = "No date"
        elif item.all_day:
            when = f"{item.start:%a %b %d}" if with_day else "All day"
        else:
            when = (f"{item.start:%a} " if with_day else "") + fmt_time(item.start)
        details = []
        if item.location:
            details.append(item.location.replace("\n", ", "))
        if a.travel and a.travel.needs_travel and item.is_timed:
            details.append(
                f"leave by {fmt_time(departure_time(a, self.config))} "
                f"({fmt_minutes(a.travel.minutes)} travel)"
            )
        if item.kind == ItemKind.REMINDER and item.start and item.start < self.generated_at:
            days = (self.generated_at.date() - item.start.date()).days
            details.append("overdue" + (f" by {days} day(s)" if days else ""))
        if item.calendar:
            details.append(item.calendar)
        return when, item.title, " · ".join(details)

    def to_text(self) -> str:
        lines = [self.title, "=" * len(self.title), self.headline, ""]
        for section in self.sections:
            if not section.rows:
                continue
            lines.append(section.heading)
            for a in section.rows:
                when, title, detail = self._describe(a, self.kind == "weekly")
                flag = "!" if a.priority.tier >= Tier.HIGH else " "
                lines.append(f" {flag} {when:>12}  {title}" + (f"  ({detail})" if detail else ""))
            lines.append("")
        if self.is_empty():
            lines.append("Nothing scheduled. Enjoy!")
        return "\n".join(lines)

    def to_html(self) -> str:
        esc = html.escape
        parts = []
        for section in self.sections:
            if not section.rows:
                continue
            rows = []
            for a in section.rows:
                when, title, detail = self._describe(a, self.kind == "weekly")
                tier = a.priority.tier
                why = ", ".join(a.priority.reasons) or "no strong signals"
                rows.append(
                    f'<li class="t{tier.value}"><span class="when">{esc(when)}</span>'
                    f'<span class="body"><span class="title">{esc(title)}</span>'
                    f'<span class="badge" title="{esc(why)}">{tier.label}</span>'
                    + (f'<span class="detail">{esc(detail)}</span>' if detail else "")
                    + "</span></li>"
                )
            parts.append(f"<section><h2>{esc(section.heading)}</h2><ul>{''.join(rows)}</ul></section>")
        if not parts:
            parts.append('<p class="empty">Nothing scheduled. Enjoy!</p>')
        return HTML_TEMPLATE.format(
            title=esc(self.title),
            headline=esc(self.headline),
            generated=esc(f"{self.generated_at:%A %B %d, %Y} at {fmt_time(self.generated_at)}"),
            body="".join(parts),
        )


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --fg:#1d1d1f; --muted:#6e6e73; --line:#e5e5ea;
  --crit:#d70015; --high:#c93400; --norm:#0071e3; --low:#8e8e93; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#111214; --card:#1c1c1e; --fg:#f5f5f7;
  --muted:#a1a1a6; --line:#2c2c2e; --crit:#ff453a; --high:#ff9f0a; --norm:#0a84ff; --low:#8e8e93; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font:15px/1.45 -apple-system, "Segoe UI", system-ui, sans-serif; }}
main {{ max-width:720px; margin:0 auto; padding:32px 16px 48px; }}
h1 {{ margin:0 0 4px; font-size:26px; }} .sub {{ color:var(--muted); margin:0 0 24px; }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
  padding:4px 16px 8px; margin-bottom:16px; }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:14px 0 6px; }}
ul {{ list-style:none; margin:0; padding:0; }}
li {{ display:flex; gap:14px; padding:10px 0; border-top:1px solid var(--line); border-left:3px solid transparent; }}
li:first-child {{ border-top:none; }}
.when {{ flex:0 0 92px; color:var(--muted); font-variant-numeric:tabular-nums; padding-left:8px; }}
.body {{ display:flex; flex-wrap:wrap; gap:4px 8px; align-items:baseline; min-width:0; }}
.title {{ font-weight:600; overflow-wrap:anywhere; }}
.detail {{ flex-basis:100%; color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
.badge {{ font-size:11px; border-radius:6px; padding:1px 6px; color:#fff; background:var(--low); cursor:help; }}
li.t3 {{ border-left-color:var(--crit); }} li.t3 .badge {{ background:var(--crit); }}
li.t2 {{ border-left-color:var(--high); }} li.t2 .badge {{ background:var(--high); }}
li.t1 .badge {{ background:var(--norm); }}
.empty {{ color:var(--muted); text-align:center; padding:40px 0; }}
</style></head><body><main>
<h1>{title}</h1><p class="sub">{headline}<br>Generated {generated}</p>
{body}
</main></body></html>
"""


FAR_FUTURE = datetime.max.replace(tzinfo=timezone.utc)


def _sort_key(a: AnalyzedItem):
    item = a.item
    return (item.start is None, item.start or FAR_FUTURE, -a.priority.score)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def build_daily(items: list[AnalyzedItem], now: datetime, config: Config) -> Summary:
    today = now.date()
    tomorrow = today + timedelta(days=1)
    open_items = [a for a in items if not a.item.completed]

    def on(day, a):
        return a.item.start is not None and a.item.start.date() == day

    events_today = sorted(
        (a for a in open_items if a.item.kind == ItemKind.EVENT and on(today, a)), key=_sort_key
    )
    timed = [a for a in events_today if not a.item.all_day]
    all_day = [a for a in events_today if a.item.all_day]
    reminders_today = sorted(
        (a for a in open_items if a.item.kind == ItemKind.REMINDER and on(today, a)), key=_sort_key
    )
    overdue = sorted(
        (
            a for a in open_items
            if a.item.kind == ItemKind.REMINDER and a.item.start and a.item.start.date() < today
        ),
        key=_sort_key,
    )
    undated = sorted(
        (a for a in open_items if a.item.kind == ItemKind.REMINDER and a.item.start is None),
        key=lambda a: -a.priority.score,
    )
    # Only surface undated reminders that are actually important; the rest is noise.
    undated_important = [a for a in undated if a.priority.tier >= Tier.HIGH][:10]
    tomorrow_important = sorted(
        (a for a in open_items if on(tomorrow, a) and a.priority.tier >= Tier.HIGH), key=_sort_key
    )

    sections = [
        Section("Today's schedule", timed),
        Section("All-day", all_day),
        Section("Reminders due today", reminders_today),
        Section("Overdue", overdue),
        Section("Important, no due date", undated_important),
        Section("Heads-up for tomorrow", tomorrow_important),
    ]
    bits = []
    if timed:
        first = timed[0]
        bits.append(f"{_plural(len(timed), 'event')} (first at {fmt_time(first.item.start)})")
    if reminders_today:
        bits.append(_plural(len(reminders_today), "task") + " due")
    if overdue:
        bits.append(f"{len(overdue)} overdue")
    important = sum(1 for a in timed + reminders_today if a.priority.tier >= Tier.HIGH)
    if important:
        bits.append(f"{important} important")
    headline = ", ".join(bits) + "." if bits else "Nothing scheduled today."
    return Summary("daily", f"Your day: {now:%A, %B %d}", headline, sections, now, config)


def build_weekly(items: list[AnalyzedItem], now: datetime, config: Config) -> Summary:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    open_items = [a for a in items if not a.item.completed]
    in_week = [a for a in open_items if a.item.start is not None and start <= a.item.start < end]

    major = [a for a in in_week if a.priority.tier >= Tier.HIGH]
    sections = []
    for offset in range(7):
        day = (start + timedelta(days=offset)).date()
        rows = sorted((a for a in major if a.item.start.date() == day), key=_sort_key)
        label = "Today" if offset == 0 else ("Tomorrow" if offset == 1 else f"{day:%A %b %d}")
        sections.append(Section(label, rows))
    overdue_major = sorted(
        (
            a for a in open_items
            if a.item.kind == ItemKind.REMINDER and a.item.start and a.item.start < start
            and a.priority.tier >= Tier.HIGH
        ),
        key=_sort_key,
    )
    sections.append(Section("Still overdue", overdue_major))

    minor = len(in_week) - len(major)
    headline = (
        f"{_plural(len(major), 'major item')} this week"
        + (f", plus {minor} routine" if minor else "")
        + (f"; {len(overdue_major)} important overdue" if overdue_major else "")
        + "."
    )
    title = f"Week ahead: {start:%b %d} – {(end - timedelta(days=1)):%b %d}"
    return Summary("weekly", title, headline, sections, now, config)
