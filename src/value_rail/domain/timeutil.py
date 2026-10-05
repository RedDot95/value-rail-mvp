"""UTC internally, Europe/Berlin for display."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Europe/Berlin")


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        # Naive datetimes are only ever produced by SQLite round-trips of UTC values.
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_display(dt: datetime | None, tz: ZoneInfo = DISPLAY_TZ) -> str:
    if dt is None:
        return "unbekannt"
    return ensure_utc(dt).astimezone(tz).strftime("%d.%m.%Y %H:%M:%S %Z")


_REL = re.compile(r"^now(?:(?P<sign>[+-])(?P<n>\d+)(?P<unit>[smhd]))?$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def resolve_time(value: str | datetime, now: datetime) -> datetime:
    """Resolve fixture timestamps: 'now', 'now-90s', 'now-2h' or ISO-8601 with offset."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    m = _REL.match(value.strip())
    if m:
        if not m.group("n"):
            return ensure_utc(now)
        delta = timedelta(**{_UNITS[m.group("unit")]: int(m.group("n"))})
        return ensure_utc(now) + (delta if m.group("sign") == "+" else -delta)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without timezone not accepted: {value!r}")
    return ensure_utc(dt)
