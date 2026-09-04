# tools/agents/quota/thresholds.py
"""Quota threshold verdicts for AI coding agents.

Never treat "could not measure" as "plenty of room".
"""

from collections import namedtuple
from typing import Iterable, Optional

Verdict = namedtuple("Verdict", ["level", "ratio", "state", "reason", "burn"])

_LEVEL_ORDER = {
    "dead": 0,
    "unknown": 1,
    "hold": 2,
    "warn": 3,
    "ok": 4,
}

_ALLOWED_STATES = frozenset({"known", "estimated", "unknown"})


def verdict(
    used: Optional[int],
    limit: Optional[int],
    state: str,
    fraction_elapsed: Optional[float] = None,
) -> Verdict:
    """Return a Verdict for one counting key.

    Refuses to invent a ratio or a permissive level when provenance or
    numbers are missing. Invalid inputs raise ValueError.
    """
    if state not in _ALLOWED_STATES:
        raise ValueError(f"state must be one of {_ALLOWED_STATES}, got {state!r}")

    if fraction_elapsed is not None:
        if not isinstance(fraction_elapsed, (int, float)) or isinstance(
            fraction_elapsed, bool
        ):
            raise ValueError("fraction_elapsed must be a float in [0.0, 1.0)")
        if not (0.0 <= float(fraction_elapsed) < 1.0):
            raise ValueError("fraction_elapsed must be in [0.0, 1.0)")

    if state == "unknown":
        return Verdict("unknown", None, state, "state-unknown", None)

    if limit is None:
        return Verdict("unknown", None, state, "no-limit-declared", None)

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be a positive integer or None")
    if limit <= 0:
        raise ValueError("limit must be positive; zero is a caller bug")

    if used is None:
        return Verdict("unknown", None, state, "usage-not-counted", None)

    if isinstance(used, bool) or not isinstance(used, int):
        raise ValueError("used must be a non-negative integer or None")
    if used < 0:
        raise ValueError("used must be non-negative")

    ratio = used / limit

    if ratio >= 1.0:
        level, reason = "dead", "at-limit"
    elif ratio >= 0.90:
        level, reason = "hold", "ninety-percent"
    elif ratio >= 0.80:
        level, reason = "warn", "eighty-percent"
    else:
        level, reason = "ok", ""

    burn = None
    if fraction_elapsed is not None:
        fe = float(fraction_elapsed)
        if ratio > fe + 0.10:
            burn = "ahead"
        elif ratio < fe - 0.10:
            burn = "behind"
        else:
            burn = "on-pace"

    return Verdict(level, ratio, state, reason, burn)


def worst(verdicts: Iterable[Verdict]) -> Verdict:
    """Return the most restrictive verdict in an iterable. Empty -> unknown."""
    best = None
    best_rank = None
    for v in verdicts:
        rank = _LEVEL_ORDER[v.level]
        if best is None or rank < best_rank:
            best = v
            best_rank = rank
    if best is None:
        return Verdict("unknown", None, "unknown", "nothing-to-judge", None)
    return best


def may_delegate(v: Verdict) -> bool:
    """True only when it is safe to hand this provider new work."""
    return v.level in ("ok", "warn")
