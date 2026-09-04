# tests/test_quota_windows.py
from datetime import datetime, timedelta, timezone

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "windows.py"

)
_spec = _ilu.spec_from_file_location('windows', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
next_reset = _mod.next_reset
window_bounds = _mod.window_bounds
window_fraction_elapsed = _mod.window_fraction_elapsed


UTC = timezone.utc


def test_rolling_five_hours_is_epoch_aligned():
    spec = {"kind": "rolling", "hours": 5}
    now = datetime(2026, 9, 4, 13, 20, tzinfo=UTC)
    assert window_bounds(spec, now) == (
        datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
        datetime(2026, 9, 4, 15, 0, tzinfo=UTC),
    )


def test_rolling_window_is_stable_across_two_nearby_calls():
    spec = {"kind": "rolling", "hours": 5}
    first = datetime(2026, 9, 4, 13, 20, tzinfo=UTC)
    second = first + timedelta(minutes=1)
    assert window_bounds(spec, first) == window_bounds(spec, second)


def test_rolling_fractional_hours():
    spec = {"kind": "rolling", "hours": 0.5}
    now = datetime(2026, 9, 4, 13, 44, tzinfo=UTC)
    assert window_bounds(spec, now) == (
        datetime(2026, 9, 4, 13, 30, tzinfo=UTC),
        datetime(2026, 9, 4, 14, 0, tzinfo=UTC),
    )


def test_rolling_rejects_zero_and_negative_hours():
    for hours in (0, -1, -0.5):
        with pytest.raises(ValueError):
            window_bounds(
                {"kind": "rolling", "hours": hours},
                datetime(2026, 9, 4, tzinfo=UTC),
            )


def test_daily_utc_bounds():
    spec = {"kind": "daily", "tz": "UTC"}
    now = datetime(2026, 9, 4, 13, 20, tzinfo=UTC)
    assert window_bounds(spec, now) == (
        datetime(2026, 9, 4, tzinfo=UTC),
        datetime(2026, 9, 5, tzinfo=UTC),
    )


def test_daily_pacific_is_offset_from_utc():
    spec = {"kind": "daily", "tz": "America/Los_Angeles"}
    now = datetime(2026, 7, 10, 18, 0, tzinfo=UTC)
    start, end = window_bounds(spec, now)
    assert start == datetime(2026, 7, 10, 7, 0, tzinfo=UTC)
    assert end == datetime(2026, 7, 11, 7, 0, tzinfo=UTC)


def test_daily_pacific_spring_forward_is_23_hours():
    spec = {"kind": "daily", "tz": "America/Los_Angeles"}
    now = datetime(2026, 3, 8, 12, 0, tzinfo=UTC)
    start, end = window_bounds(spec, now)
    assert start == datetime(2026, 3, 8, 8, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 9, 7, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=23)


def test_daily_pacific_fall_back_is_25_hours():
    spec = {"kind": "daily", "tz": "America/Los_Angeles"}
    now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    start, end = window_bounds(spec, now)
    assert start == datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    assert end - start == timedelta(hours=25)


def test_daily_rejects_unknown_timezone():
    spec = {"kind": "daily", "tz": "Mars/Olympus"}
    with pytest.raises(ValueError, match="Mars/Olympus"):
        window_bounds(spec, datetime(2026, 9, 4, tzinfo=UTC))


def test_monthly_default_anchor_is_first():
    spec = {"kind": "monthly", "tz": "UTC"}
    now = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    assert window_bounds(spec, now) == (
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    )


def test_monthly_anchor_day_clamps_in_february():
    spec = {"kind": "monthly", "tz": "UTC", "anchor_day": 31}

    early_february = datetime(2026, 2, 15, 12, 0, tzinfo=UTC)
    assert window_bounds(spec, early_february) == (
        datetime(2026, 1, 31, tzinfo=UTC),
        datetime(2026, 2, 28, tzinfo=UTC),
    )

    late_february = datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    assert window_bounds(spec, late_february) == (
        datetime(2026, 2, 28, tzinfo=UTC),
        datetime(2026, 3, 31, tzinfo=UTC),
    )


def test_monthly_rejects_anchor_day_zero_and_32():
    for anchor_day in (0, 32):
        spec = {"kind": "monthly", "tz": "UTC", "anchor_day": anchor_day}
        with pytest.raises(ValueError):
            window_bounds(spec, datetime(2026, 9, 4, tzinfo=UTC))


def test_naive_now_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        window_bounds(
            {"kind": "daily", "tz": "UTC"},
            datetime(2026, 9, 4, 13, 20),
        )


def test_unknown_kind_raises():
    spec = {"kind": "fortnightly"}
    with pytest.raises(ValueError, match="fortnightly"):
        window_bounds(spec, datetime(2026, 9, 4, tzinfo=UTC))


def test_fraction_is_zero_at_start_and_never_one():
    spec = {"kind": "rolling", "hours": 5}
    start = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    end = datetime(2026, 9, 4, 15, 0, tzinfo=UTC)

    assert window_fraction_elapsed(spec, start) == 0.0
    before_end = window_fraction_elapsed(spec, end - timedelta(microseconds=1))
    assert 0.0 <= before_end < 1.0
    assert window_fraction_elapsed(spec, end) == 0.0

    next_start, next_end = window_bounds(spec, end)
    assert next_start == end
    assert next_end == datetime(2026, 9, 4, 20, 0, tzinfo=UTC)


def test_fraction_never_negative():
    cases = [
        (
            {"kind": "rolling", "hours": 5},
            datetime(2026, 9, 4, 13, 20, tzinfo=UTC),
        ),
        (
            {"kind": "daily", "tz": "UTC"},
            datetime(2026, 9, 4, 0, 0, tzinfo=UTC),
        ),
        (
            {"kind": "daily", "tz": "America/Los_Angeles"},
            datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
        ),
        (
            {"kind": "monthly", "tz": "UTC", "anchor_day": 14},
            datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
        ),
    ]
    for spec, now in cases:
        fraction = window_fraction_elapsed(spec, now)
        assert 0.0 <= fraction < 1.0


def test_next_reset_equals_window_end():
    spec = {"kind": "monthly", "tz": "UTC", "anchor_day": 14}
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    assert next_reset(spec, now) == window_bounds(spec, now)[1]


def test_rolling_rejects_non_numeric_and_boolean_hours():
    now = datetime(2026, 9, 4, tzinfo=UTC)
    for hours in ("5", None, True):
        with pytest.raises(ValueError):
            window_bounds({"kind": "rolling", "hours": hours}, now)


def test_supported_specs_reject_extra_keys():
    now = datetime(2026, 9, 4, tzinfo=UTC)
    with pytest.raises(ValueError, match="offending spec"):
        window_bounds({"kind": "daily", "tz": "UTC", "extra": True}, now)
