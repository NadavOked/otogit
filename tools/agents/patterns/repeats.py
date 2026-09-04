# tools/agents/patterns/repeats.py
"""Detect repeated contiguous command runs across sessions."""

from typing import Any, Dict, List, Sequence, Tuple


def find_repeats(
    sessions: Sequence[Any],
    min_length: int = 3,
    min_occurrences: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (candidates, scan) for repeated command runs.

    Never returns an empty candidates list without an accurate scan
    that distinguishes "nothing scanned" from "scanned and found nothing".
    """
    if min_length < 2:
        raise ValueError("min_length must be at least 2")
    if min_occurrences < 2:
        raise ValueError("min_occurrences must be at least 2")

    sessions_scanned = 0
    sessions_skipped: List[Tuple[Any, str]] = []
    commands_scanned = 0
    valid_sessions: List[Tuple[str, List[str]]] = []

    for idx, sess in enumerate(sessions):
        if not isinstance(sess, dict):
            sessions_skipped.append((idx, "not a dict"))
            continue
        sid = sess.get("id")
        if sid is None:
            sessions_skipped.append((idx, "missing id"))
            continue
        cmds = sess.get("commands")
        if not isinstance(cmds, list):
            sessions_skipped.append((sid, "commands is not a list"))
            continue
        if any(not isinstance(c, str) for c in cmds):
            sessions_skipped.append((sid, "non-string command"))
            continue
        valid_sessions.append((str(sid), list(cmds)))
        sessions_scanned += 1
        commands_scanned += len(cmds)

    # Every contiguous run is a candidate, at every offset. Scanning fixed
    # blocks from index 0 in steps of `length` would never line up with a run
    # whose offset does not divide evenly, and would report it as absent.
    # Upper bound: a run of length L seen min_occurrences times consumes
    # L * min_occurrences commands, so longer runs cannot reach the threshold.
    max_length = commands_scanned // min_occurrences
    seen_sequences = set()
    for _sid, cmds in valid_sessions:
        n = len(cmds)
        for length in range(min_length, min(n, max_length) + 1):
            for i in range(n - length + 1):
                seen_sequences.add(tuple(cmds[i : i + length]))

    candidates_raw: List[Dict[str, Any]] = []
    for seq in seen_sequences:
        occurrences = 0
        session_ids = set()
        for sid, cmds in valid_sessions:
            hits = _count_non_overlapping(cmds, seq)
            if hits:
                occurrences += hits
                session_ids.add(sid)
        if occurrences < min_occurrences:
            continue
        ordered_ids = tuple(sorted(session_ids))
        candidates_raw.append(
            {
                "sequence": seq,
                "length": len(seq),
                "occurrences": occurrences,
                "sessions": ordered_ids,
                "spread": len(ordered_ids),
            }
        )

    # Suppress runs wholly contained in a longer run with the same occurrence count.
    # A shorter run with a strictly higher count is kept.
    to_suppress = set()
    for a in candidates_raw:
        for b in candidates_raw:
            if a is b:
                continue
            if (
                a["length"] < b["length"]
                and a["occurrences"] == b["occurrences"]
                and _is_subsequence(a["sequence"], b["sequence"])
            ):
                to_suppress.add(a["sequence"])

    candidates = [c for c in candidates_raw if c["sequence"] not in to_suppress]

    # Order: occurrences desc, length desc, sequence itself
    candidates.sort(
        key=lambda c: (-c["occurrences"], -c["length"], c["sequence"])
    )

    scan = {
        "sessions_scanned": sessions_scanned,
        "sessions_skipped": sessions_skipped,
        "commands_scanned": commands_scanned,
        "min_length": min_length,
        "min_occurrences": min_occurrences,
    }
    return candidates, scan


def _is_subsequence(short: Tuple[str, ...], long: Tuple[str, ...]) -> bool:
    """True if short appears as a contiguous sub-run of long."""
    n, m = len(short), len(long)
    if n > m:
        return False
    for i in range(m - n + 1):
        if long[i : i + n] == short:
            return True
    return False


def _count_non_overlapping(cmds: List[str], seq: Tuple[str, ...]) -> int:
    """Count occurrences of seq in cmds, scanning left to right and consuming
    each match, so overlapping occurrences are counted once."""
    n, m = len(seq), len(cmds)
    if n == 0 or n > m:
        return 0
    count = 0
    i = 0
    while i + n <= m:
        if tuple(cmds[i : i + n]) == seq:
            count += 1
            i += n
        else:
            i += 1
    return count
