# tools/agents/quota/report.py
"""Renders the fleet quota report table and summary headline."""

from datetime import datetime


def _parse_duration(window_end, now):
    if window_end is None:
        return "?"
    if window_end <= now:
        return "due"
    delta = window_end - now
    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d{hours}h"
    elif hours > 0:
        return f"{hours}h{minutes}m"
    else:
        return f"{minutes}m"


def summary_line(rows):
    """Return the one-line headline shown above the table."""
    rows_list = list(rows)
    if not rows_list:
        return "fleet: no data"

    counts = {"ok": 0, "warn": 0, "hold": 0, "dead": 0, "unknown": 0}
    measured_count = 0

    for r in rows_list:
        if not isinstance(r, dict):
            lvl = "unknown"
        else:
            lvl = str(r.get("level", "unknown")).lower()
            if lvl not in counts:
                lvl = "unknown"
            if r.get("state") == "known":
                measured_count += 1
        counts[lvl] += 1

    s = (
        f"fleet: {counts['ok']} ok, {counts['warn']} warn, "
        f"{counts['hold']} hold, {counts['dead']} dead, {counts['unknown']} unknown"
    )
    s += f"  ({measured_count} of {len(rows_list)} keys measured)"
    return s


def render(rows, now, width=None):
    """Return the report as a single string. Never raises for row content."""
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.tzinfo.utcoffset(now) is None
    ):
        raise ValueError("now must be a timezone-aware datetime")

    try:
        rows_list = list(rows)
    except Exception as e:
        raise ValueError("rows must be an iterable") from e

    valid_levels = {"dead": 0, "unknown": 1, "hold": 2, "warn": 3, "ok": 4}

    processed_rows = []
    for r in rows_list:
        if isinstance(r, dict):
            raw_level = r.get("level")
            malformed = (
                r.get("key") is None
                or not isinstance(raw_level, str)
                or raw_level not in valid_levels
            )
        else:
            malformed = True

        if malformed:
            key, level, state, used, limit, ratio, window_end, burn = (
                "?", "unknown", "MALFORMED", None, None, None, None, None
            )
        else:
            key = str(r["key"])
            level = str(r["level"])
            state = str(r.get("state")) if r.get("state") is not None else "unknown"
            used = r.get("used")
            limit = r.get("limit")
            ratio = r.get("ratio")
            window_end = r.get("window_end")
            burn = r.get("burn")

        if level == "unknown" and state != "MALFORMED":
            state_str = "UNKNOWN"
        else:
            state_str = str(state)

        used_str = (
            str(used) if isinstance(used, int) and not isinstance(used, bool) else "?"
        )
        limit_str = (
            str(limit)
            if isinstance(limit, int) and not isinstance(limit, bool)
            else "?"
        )

        if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
            pct_val = (
                int(ratio * 100)
                if ratio < 1
                else int(ratio) if ratio > 1 else int(ratio * 100)
            )
            pct_str = f"{pct_val}%~" if state == "estimated" else f"{pct_val}%"
        else:
            pct_str = "?"

        resets_str = _parse_duration(window_end, now)
        burn_str = str(burn) if burn is not None else "?"
        sort_level = valid_levels.get(level, 1)

        processed_rows.append({
            "key": key, "used": used_str, "limit": limit_str, "pct": pct_str,
            "state": state_str, "resets": resets_str, "burn": burn_str,
            "sort_level": sort_level
        })

    processed_rows.sort(key=lambda x: (x["sort_level"], x["key"]))

    if width is not None:
        for r in processed_rows:
            if len(r["key"]) > width:
                r["key"] = r["key"][:width] + "…"

    max_key_len = len("KEY")
    for r in processed_rows:
        if len(r["key"]) > max_key_len:
            max_key_len = len(r["key"])

    cols = [
        ("KEY", max_key_len), ("USED", 4), ("LIMIT", 5), ("PCT", 4),
        ("STATE", 9), ("RESETS", 6), ("BURN", 6)
    ]

    for r in processed_rows:
        for idx, (col_name, cur_w) in enumerate(cols):
            val_len = len(r[col_name.lower()])
            if val_len > cur_w:
                cols[idx] = (col_name, val_len)

    header = " ".join(name.ljust(w) for name, w in cols).rstrip()
    separator = " ".join("-" * w for _, w in cols).rstrip()

    lines = [header, separator]
    for r in processed_rows:
        row_str = " ".join(r[name.lower()].ljust(w) for name, w in cols).rstrip()
        lines.append(row_str)

    return "\n".join(lines)
