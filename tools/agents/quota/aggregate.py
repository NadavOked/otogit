# tools/agents/quota/aggregate.py
"""Fold usage-log rows into the quota window containing a supplied time."""

import json
from datetime import datetime, timezone


def _parse_timestamp(value):
    if not isinstance(value, str):
        return None, "bad-timestamp"
    try:
        text = value
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None, "bad-timestamp"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "naive-timestamp"
    return parsed, None


def _spec_cache_key(spec):
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), default=repr)


def _excluded(index, reason, key=None, detail=None):
    result = {"index": index, "reason": reason, "key": key}
    if detail is not None:
        result["detail"] = detail
    return result


def fold(rows, now, key_of, window_of, bounds_of):
    """Return ``(totals, excluded)`` for the window containing ``now``."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    totals = {}
    excluded = []
    window_cache = {}

    for index, row in enumerate(rows):
        key = None

        try:
            key = key_of(row)
        except Exception as exc:
            excluded.append(_excluded(index, "callback-error", None, str(exc)))
            continue

        if key is None or key == "":
            excluded.append(_excluded(index, "no-key", key))
            continue

        try:
            spec = window_of(key)
        except Exception as exc:
            excluded.append(_excluded(index, "callback-error", key, str(exc)))
            continue

        if spec is None:
            excluded.append(_excluded(index, "no-window", key))
            continue

        cache_key = _spec_cache_key(spec)
        if cache_key not in window_cache:
            try:
                window_cache[cache_key] = bounds_of(spec, now)
            except Exception as exc:
                excluded.append(_excluded(index, "callback-error", key, str(exc)))
                continue

        start, end = window_cache[cache_key]

        timestamp, reason = _parse_timestamp(row.get("ts"))
        if reason is not None:
            excluded.append(_excluded(index, reason, key))
            continue

        timestamp_utc = timestamp.astimezone(timezone.utc)
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)

        if not (start_utc <= timestamp_utc < end_utc):
            excluded.append(_excluded(index, "outside-window", key))
            continue

        counts = []
        bad_counts = False
        for field in ("requests", "input_tokens", "output_tokens"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                bad_counts = True
                break
            counts.append(value)

        if bad_counts:
            excluded.append(_excluded(index, "bad-counts", key))
            continue

        if key not in totals:
            totals[key] = {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "window_start": start,
                "window_end": end,
            }

        total = totals[key]
        total["requests"] += counts[0]
        total["input_tokens"] += counts[1]
        total["output_tokens"] += counts[2]
        total["calls"] += 1

    return totals, excluded
