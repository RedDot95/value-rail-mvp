"""Column types: Decimal stored as TEXT (exact), datetimes always UTC-aware."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.types import String, Text, TypeDecorator


class DecimalText(TypeDecorator):
    """Exact Decimal persistence. SQLite NUMERIC would round-trip through float."""

    impl = String(64)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("float not allowed for money columns")
        if value == "unknown":
            return "unknown"
        return format(Decimal(value), "f")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value == "unknown":
            return "unknown"
        return Decimal(value)


class UTCDateTime(TypeDecorator):
    """Stores ISO-8601 UTC text; always returns tz-aware UTC datetimes."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("datetime expected")
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed; use UTC-aware datetimes")
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return datetime.fromisoformat(value).astimezone(UTC)


class JSONText(TypeDecorator):
    """Canonical JSON (sorted keys) so hashes/replays are stable."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)
