"""Unit tests for the small, side-effect-free helpers in application.helpers."""

from datetime import datetime

from application.helpers import IST, resolve_clock_ist


def test_resolve_clock_ist_combines_time_of_day_with_reference_date():
    reference = datetime(2026, 3, 4, 9, 0, tzinfo=IST)
    resolved = resolve_clock_ist("21:40", reference=reference)
    assert resolved == datetime(2026, 3, 4, 21, 40, tzinfo=IST)


def test_resolve_clock_ist_returns_none_for_absent_or_malformed_input():
    assert resolve_clock_ist(None) is None
    assert resolve_clock_ist("") is None
    assert resolve_clock_ist("not-a-time") is None
    assert resolve_clock_ist("25:00") is None
    assert resolve_clock_ist("12:60") is None


def test_resolve_clock_ist_defaults_reference_to_now():
    resolved = resolve_clock_ist("00:00")
    assert resolved is not None
    assert resolved.hour == 0 and resolved.minute == 0
