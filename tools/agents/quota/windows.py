# tools/agents/quota/windows.py
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from math import isfinite
from numbers import Real
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _aware_utc(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    try:
        offset = now.utcoffset()
    except (TypeError, ValueError) as exc:
        raise ValueError("now must be a timezone-aware datetime") from exc
    if offset is None:
        raise ValueError("now must be a timezone-aware datetime")
    return now.astimezone(timezone.utc)


def _validate_keys(spec, required, optional=()):
    if not isinstance(spec, dict):
        raise ValueError("offending spec: {!r}".format(spec))
    allowed = set(required) | set(optional)
    if set(spec) - allowed or not set(required).issubset(spec):
        raise ValueError("offending spec: {!r}".format(spec))


def _zone(name, spec):
    if not isinstance(name, str):
        raise ValueError("offending spec: {!r}".format(spec))
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            "unknown timezone {!r} in spec {!r}".format(name, spec)
        ) from exc


def _shift_month(year, month, delta):
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _month_anchor(year, month, anchor_day, tz):
    day = min(anchor_day, monthrange(year, month)[1])
    return datetime(year, month, day, tzinfo=tz)


def _rolling_bounds(spec, now_utc):
    _validate_keys(spec, ("kind", "hours"))
    hours = spec["hours"]
    if isinstance(hours, bool) or not isinstance(hours, Real):
        raise ValueError("offending rolling spec: {!r}".format(spec))
    hours = float(hours)
    if not isfinite(hours) or hours <= 0:
        raise ValueError("offending rolling spec: {!r}".format(spec))

    window_seconds = hours * 3600.0
    elapsed_seconds = (now_utc - _EPOCH).total_seconds()
    index = elapsed_seconds // window_seconds
    start = _EPOCH + timedelta(seconds=index * window_seconds)
    end = start + timedelta(seconds=window_seconds)
    return start, end


def _daily_bounds(spec, now_utc):
    _validate_keys(spec, ("kind", "tz"))
    tz = _zone(spec["tz"], spec)
    local_now = now_utc.astimezone(tz)
    start_local = datetime(
        local_now.year, local_now.month, local_now.day, tzinfo=tz
    )
    next_date = local_now.date() + timedelta(days=1)
    end_local = datetime(
        next_date.year, next_date.month, next_date.day, tzinfo=tz
    )
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _monthly_bounds(spec, now_utc):
    _validate_keys(spec, ("kind", "tz"), ("anchor_day",))
    tz = _zone(spec["tz"], spec)
    anchor_day = spec.get("anchor_day", 1)
    if (
        isinstance(anchor_day, bool)
        or not isinstance(anchor_day, int)
        or not 1 <= anchor_day <= 31
    ):
        raise ValueError("offending monthly spec: {!r}".format(spec))

    local_now = now_utc.astimezone(tz)
    current = _month_anchor(local_now.year, local_now.month, anchor_day, tz)

    if local_now >= current:
        start_local = current
        end_year, end_month = _shift_month(local_now.year, local_now.month, 1)
        end_local = _month_anchor(end_year, end_month, anchor_day, tz)
    else:
        start_year, start_month = _shift_month(local_now.year, local_now.month, -1)
        start_local = _month_anchor(start_year, start_month, anchor_day, tz)
        end_local = current

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def window_bounds(spec, now):
    """Return the inclusive UTC start and exclusive UTC end containing now."""
    now_utc = _aware_utc(now)
    if not isinstance(spec, dict):
        raise ValueError("offending spec: {!r}".format(spec))

    kind = spec.get("kind")
    if kind == "rolling":
        return _rolling_bounds(spec, now_utc)
    if kind == "daily":
        return _daily_bounds(spec, now_utc)
    if kind == "monthly":
        return _monthly_bounds(spec, now_utc)
    raise ValueError("unknown kind {!r} in spec {!r}".format(kind, spec))


def window_fraction_elapsed(spec, now):
    """Return the fraction of the containing window elapsed, in [0.0, 1.0)."""
    now_utc = _aware_utc(now)
    start, end = window_bounds(spec, now_utc)
    fraction = (now_utc - start) / (end - start)
    if fraction < 0:
        return 0.0
    if fraction >= 1:
        return 0.0
    return float(fraction)


def next_reset(spec, now):
    """Return the UTC instant at which the current window ends."""
    return window_bounds(spec, now)[1]
