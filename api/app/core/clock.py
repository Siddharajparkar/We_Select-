"""Clock abstraction so business logic never calls ``datetime.now()`` directly.

Tests inject :class:`FakeClock` to control time precisely. All datetimes are
timezone-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    def __init__(self, initial: datetime | None = None) -> None:
        self._current = _utc(initial) if initial else datetime.now(UTC)

    def now(self) -> datetime:
        return self._current

    def set_time(self, value: datetime) -> None:
        self._current = _utc(value)

    def advance(self, **kwargs: float) -> None:
        """``advance(seconds=5)``, ``advance(minutes=1)``, ``advance(days=1)`` ..."""
        self._current = self._current + timedelta(**kwargs)

    def advance_seconds(self, seconds: float) -> None:
        self.advance(seconds=seconds)

    def advance_minutes(self, minutes: float) -> None:
        self.advance(minutes=minutes)

    def advance_hours(self, hours: float) -> None:
        self.advance(hours=hours)

    def advance_days(self, days: float) -> None:
        self.advance(days=days)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
