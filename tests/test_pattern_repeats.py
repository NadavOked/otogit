# tests/test_pattern_repeats.py
import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "patterns" / "repeats.py"

)
_spec = _ilu.spec_from_file_location('repeats', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
find_repeats = _mod.find_repeats


def test_three_occurrences_of_a_three_command_run_is_a_candidate():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c"]},
        {"id": "s2", "commands": ["a", "b", "c"]},
        {"id": "s3", "commands": ["a", "b", "c"]},
    ]
    candidates, scan = find_repeats(sessions)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["sequence"] == ("a", "b", "c")
    assert c["length"] == 3
    assert c["occurrences"] == 3
    assert c["spread"] == 3
    assert scan["sessions_scanned"] == 3


def test_two_occurrences_is_not_a_candidate_at_default_threshold():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c"]},
        {"id": "s2", "commands": ["a", "b", "c"]},
    ]
    candidates, _ = find_repeats(sessions)
    assert candidates == []


def test_run_shorter_than_min_length_is_not_a_candidate():
    sessions = [
        {"id": "s1", "commands": ["a", "b"]},
        {"id": "s2", "commands": ["a", "b"]},
        {"id": "s3", "commands": ["a", "b"]},
    ]
    candidates, _ = find_repeats(sessions, min_length=3)
    assert candidates == []


def test_occurrences_across_different_sessions_are_summed():
    sessions = [
        {"id": "s1", "commands": ["x", "y", "z"]},
        {"id": "s2", "commands": ["x", "y", "z"]},
        {"id": "s3", "commands": ["x", "y", "z"]},
    ]
    candidates, _ = find_repeats(sessions)
    assert len(candidates) == 1
    assert candidates[0]["occurrences"] == 3


def test_spread_counts_distinct_sessions_not_occurrences():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c", "a", "b", "c", "a", "b", "c"]},
    ]
    candidates, _ = find_repeats(sessions)
    assert len(candidates) == 1
    assert candidates[0]["occurrences"] == 3
    assert candidates[0]["spread"] == 1
    assert candidates[0]["sessions"] == ("s1",)


def test_overlapping_matches_are_counted_once():
    # A B A B A B — consuming each match left to right yields three occurrences
    # of A B per session (at 0, 2, 4), not the five a sliding window would report.
    sessions = [
        {"id": "s1", "commands": ["A", "B", "A", "B", "A", "B"]},
        {"id": "s2", "commands": ["A", "B", "A", "B", "A", "B"]},
        {"id": "s3", "commands": ["A", "B", "A", "B", "A", "B"]},
    ]
    candidates, _ = find_repeats(sessions, min_length=2, min_occurrences=3)
    ab = [c for c in candidates if c["sequence"] == ("A", "B")]
    assert len(ab) == 1
    assert ab[0]["occurrences"] == 9  # 3 per session × 3 sessions
    # Must not be 5 per session (15) from sliding-window overcounting
    assert ab[0]["occurrences"] != 15
    assert ab[0]["spread"] == 3

    # A B never actually overlaps itself, so the case above cannot tell a
    # consuming scan from a sliding one. A self-overlapping run can: A A A A
    # holds two non-overlapping A A, and three only if windows are slid.
    sessions = [
        {"id": "s1", "commands": ["A", "A", "A", "A"]},
        {"id": "s2", "commands": ["A", "A", "A", "A"]},
        {"id": "s3", "commands": ["A", "A", "A", "A"]},
    ]
    candidates, _ = find_repeats(sessions, min_length=2, min_occurrences=3)
    aa = [c for c in candidates if c["sequence"] == ("A", "A")]
    assert len(aa) == 1
    assert aa[0]["occurrences"] == 6  # 2 per session, not 3


def test_contained_run_with_same_count_is_suppressed():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c", "d"]},
        {"id": "s2", "commands": ["a", "b", "c", "d"]},
        {"id": "s3", "commands": ["a", "b", "c", "d"]},
    ]
    candidates, _ = find_repeats(sessions)
    seqs = {c["sequence"] for c in candidates}
    assert ("a", "b", "c", "d") in seqs
    assert ("a", "b", "c") not in seqs
    assert ("b", "c", "d") not in seqs
    assert ("a", "b") not in seqs


def test_contained_run_with_higher_count_is_kept():
    # Longer run appears 3 times; shorter run appears 4 times → keep both
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c", "d"]},
        {"id": "s2", "commands": ["a", "b", "c", "d"]},
        {"id": "s3", "commands": ["a", "b", "c", "d"]},
        {"id": "s4", "commands": ["a", "b", "c"]},
    ]
    candidates, _ = find_repeats(sessions, min_length=3, min_occurrences=3)
    seqs = {c["sequence"]: c["occurrences"] for c in candidates}
    assert seqs.get(("a", "b", "c", "d")) == 3
    assert seqs.get(("a", "b", "c")) == 4


def test_candidates_are_ordered_by_occurrences_then_length():
    sessions = [
        {"id": "s1", "commands": ["x", "y", "z", "w"]},
        {"id": "s2", "commands": ["x", "y", "z", "w"]},
        {"id": "s3", "commands": ["x", "y", "z", "w"]},
        {"id": "s4", "commands": ["p", "q", "r"]},
        {"id": "s5", "commands": ["p", "q", "r"]},
        {"id": "s6", "commands": ["p", "q", "r"]},
        {"id": "s7", "commands": ["p", "q", "r"]},
    ]
    candidates, _ = find_repeats(sessions)
    assert candidates[0]["sequence"] == ("p", "q", "r")
    assert candidates[0]["occurrences"] == 4
    assert candidates[1]["sequence"] == ("x", "y", "z", "w")
    assert candidates[1]["occurrences"] == 3


def test_result_is_deterministic_across_two_calls():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c"]},
        {"id": "s2", "commands": ["a", "b", "c"]},
        {"id": "s3", "commands": ["a", "b", "c"]},
        {"id": "s4", "commands": ["x", "y", "z"]},
        {"id": "s5", "commands": ["x", "y", "z"]},
        {"id": "s6", "commands": ["x", "y", "z"]},
    ]
    c1, s1 = find_repeats(sessions)
    c2, s2 = find_repeats(sessions)
    assert c1 == c2
    assert s1 == s2


def test_min_length_below_two_raises():
    with pytest.raises(ValueError):
        find_repeats([], min_length=1)


def test_min_occurrences_below_two_raises():
    with pytest.raises(ValueError):
        find_repeats([], min_occurrences=1)


def test_empty_sessions_returns_empty_candidates_and_zero_scanned():
    candidates, scan = find_repeats([])
    assert candidates == []
    assert scan["sessions_scanned"] == 0
    assert scan["commands_scanned"] == 0
    assert scan["sessions_skipped"] == []


def test_empty_result_is_distinguishable_from_nothing_scanned():
    # Scanned but found nothing
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c"]},
        {"id": "s2", "commands": ["d", "e", "f"]},
    ]
    c1, scan1 = find_repeats(sessions)
    assert c1 == []
    assert scan1["sessions_scanned"] == 2

    # Nothing to scan
    c2, scan2 = find_repeats([])
    assert c2 == []
    assert scan2["sessions_scanned"] == 0
    assert scan1["sessions_scanned"] != scan2["sessions_scanned"]


def test_malformed_session_is_recorded_in_skipped_not_dropped():
    sessions = [
        {"id": "good", "commands": ["a", "b", "c"]},
        "not-a-dict",
        {"id": "good2", "commands": ["a", "b", "c"]},
        {"id": "good3", "commands": ["a", "b", "c"]},
    ]
    candidates, scan = find_repeats(sessions)
    assert len(candidates) == 1
    assert scan["sessions_scanned"] == 3
    assert len(scan["sessions_skipped"]) == 1
    idx, reason = scan["sessions_skipped"][0]
    assert idx == 1
    assert "dict" in reason.lower()


def test_non_string_command_skips_the_whole_session():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c"]},
        {"id": "s2", "commands": ["a", 42, "c"]},
        {"id": "s3", "commands": ["a", "b", "c"]},
        {"id": "s4", "commands": ["a", "b", "c"]},
    ]
    candidates, scan = find_repeats(sessions)
    assert len(candidates) == 1
    assert candidates[0]["occurrences"] == 3
    assert scan["sessions_scanned"] == 3
    assert any(sid == "s2" for sid, _ in scan["sessions_skipped"])


def test_session_without_id_is_skipped_with_its_index():
    sessions = [
        {"commands": ["a", "b", "c"]},
        {"id": "s2", "commands": ["a", "b", "c"]},
        {"id": "s3", "commands": ["a", "b", "c"]},
        {"id": "s4", "commands": ["a", "b", "c"]},
    ]
    candidates, scan = find_repeats(sessions)
    assert len(candidates) == 1
    assert scan["sessions_scanned"] == 3
    assert any(idx == 0 for idx, _ in scan["sessions_skipped"])


def test_commands_scanned_counts_only_scanned_sessions():
    sessions = [
        {"id": "s1", "commands": ["a", "b", "c", "d"]},
        "bad",
        {"id": "s2", "commands": ["e", "f"]},
        {"commands": ["g", "h", "i"]},  # no id
    ]
    _, scan = find_repeats(sessions)
    assert scan["sessions_scanned"] == 2
    assert scan["commands_scanned"] == 6  # 4 + 2


def test_custom_thresholds_are_honoured_and_echoed_in_scan():
    sessions = [
        {"id": "s1", "commands": ["a", "b"]},
        {"id": "s2", "commands": ["a", "b"]},
    ]
    candidates, scan = find_repeats(sessions, min_length=2, min_occurrences=2)
    assert len(candidates) == 1
    assert candidates[0]["sequence"] == ("a", "b")
    assert scan["min_length"] == 2
    assert scan["min_occurrences"] == 2


def test_run_not_aligned_to_a_block_boundary_is_still_found():
    # F05 rule 1: a candidate is any contiguous run. Counting only blocks that
    # start at index 0 and step by `length` misses every run whose offset does
    # not divide evenly — "we scanned and found nothing" about something that
    # is there three times per session.
    sessions = [
        {"id": "s%d" % i,
         "commands": ["ssh", "deploy", "restart", "deploy",
                      "restart", "deploy", "restart"]}
        for i in range(3)
    ]
    candidates, scan = find_repeats(sessions, min_length=2, min_occurrences=3)
    by_seq = {c["sequence"]: c for c in candidates}
    assert ("deploy", "restart") in by_seq
    hit = by_seq[("deploy", "restart")]
    assert hit["occurrences"] == 9  # 3 per session x 3 sessions
    assert hit["spread"] == 3
    assert hit["sessions"] == ("s0", "s1", "s2")
    assert scan["sessions_scanned"] == 3


def test_offset_run_inside_a_single_session_is_found():
    # The run starts at index 1 and repeats every 3 commands: no block scan
    # anchored at 0 ever lines up with it.
    sessions = [
        {"id": "solo",
         "commands": ["boot", "a", "b", "c", "x", "a", "b", "c",
                      "x", "a", "b", "c"]},
    ]
    candidates, _ = find_repeats(sessions, min_length=3, min_occurrences=3)
    by_seq = {c["sequence"]: c for c in candidates}
    assert ("a", "b", "c") in by_seq
    assert by_seq[("a", "b", "c")]["occurrences"] == 3
