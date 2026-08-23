"""iCalendar (.ics) — one chunk per event.

A token window over a calendar file is meaningless: it would cut across unrelated events
and embed half of one meeting with half of another. An event is the unit someone
remembers, so it is the unit that gets embedded.

Recurrences are stored once, never expanded. 31 of the 355 events in the real corpus
carry an RRULE, and expanding a daily event over four years is tens of thousands of
chunks from a single entry. Resolving "the interview in February" against a recurrence
is query understanding's problem, not ingestion's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

ICS_MAGIC = b"BEGIN:VCALENDAR"


@dataclass(frozen=True)
class CalendarEvent:
    summary: str
    starts_at: datetime | None
    ends_at: datetime | None
    location: str = ""
    description: str = ""
    recurrence: str = ""
    meta: dict = field(default_factory=dict)

    def render(self) -> str:
        """What actually gets embedded - a human sentence, not a VEVENT block."""
        parts = [self.summary]
        if self.starts_at:
            parts.append(f"on {self.starts_at:%A %d %B %Y at %H:%M}")
        if self.location:
            parts.append(f"at {self.location}")
        if self.recurrence:
            parts.append("(repeating)")
        if self.description:
            parts.append(self.description)
        return " ".join(p for p in parts if p).strip()


def is_calendar(data: bytes) -> bool:
    return data.lstrip()[: len(ICS_MAGIC)] == ICS_MAGIC


def _as_datetime(value: object) -> datetime | None:
    """iCal gives a date for all-day events and a datetime otherwise."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return None


def _text(component, key: str) -> str:
    raw = component.get(key)
    return str(raw).strip() if raw is not None else ""


def parse_calendar(data: bytes) -> tuple[str, list[CalendarEvent]]:
    """Return (calendar name, events). Unnamed busy-blocks are skipped."""
    from icalendar import Calendar

    calendar = Calendar.from_ical(data)
    name = _text(calendar, "X-WR-CALNAME") or "Calendar"

    events: list[CalendarEvent] = []
    for component in calendar.walk("VEVENT"):
        summary = _text(component, "SUMMARY")
        description = _text(component, "DESCRIPTION")
        if not summary and not description:
            # A bare busy-block is not a document anyone searches for.
            continue

        starts = _as_datetime(getattr(component.get("DTSTART"), "dt", None))
        ends = _as_datetime(getattr(component.get("DTEND"), "dt", None))
        recurrence = _text(component, "RRULE")

        events.append(
            CalendarEvent(
                summary=summary or description[:80],
                starts_at=starts,
                ends_at=ends,
                location=_text(component, "LOCATION"),
                description=description,
                recurrence=recurrence,
                meta={
                    "location": _text(component, "LOCATION"),
                    "recurrence": recurrence,
                    "organizer": _text(component, "ORGANIZER"),
                },
            )
        )

    return name, events
