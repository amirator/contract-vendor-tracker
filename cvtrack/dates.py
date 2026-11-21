"""Small date helpers that respect a configurable weekend (Fri-Sat by default)."""

from __future__ import annotations

from datetime import date, timedelta


def parse(value: str) -> date | None:
    value = (value or "").strip()
    return date.fromisoformat(value) if value else None


def business_days_until(start: date, end: date, weekend: set[int]) -> int:
    """Working days after `start` up to and including `end` (negative if `end` is earlier)."""
    if end == start:
        return 0
    step = 1 if end > start else -1
    n, d = 0, start
    while d != end:
        d += timedelta(days=step)
        if d.weekday() not in weekend:
            n += step
    return n


def next_business_day(d: date, weekend: set[int]) -> date:
    while d.weekday() in weekend:
        d += timedelta(days=1)
    return d
