# tests/test_triage_blockers.py
import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "triage" / "blockers.py"

)
_spec = _ilu.spec_from_file_location('blockers', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
cited_blockers = _mod.cited_blockers
stale_blocks = _mod.stale_blocks


PATTERNS = [
    r"blocked\s+by\s+#(\d+)",
    r"depends\s+on\s+#(\d+)",
    r"waiting\s+on\s+#(\d+)",
]


def issue(number, body, labels=None):
    return {"number": number, "body": body, "labels": labels or []}


def test_blocked_by_phrase_is_extracted():
    assert cited_blockers("This is blocked by #84.", PATTERNS) == [84]


def test_bare_hash_number_is_not_a_blocker():
    assert cited_blockers("This is similar to #84.", PATTERNS) == []


def test_several_phrases_all_matched():
    body = "Blocked by #84, depends on #91, and waiting on #105."
    assert cited_blockers(body, PATTERNS) == [84, 91, 105]


def test_duplicate_citation_appears_once():
    body = "Blocked by #84. Later: waiting on #84."
    assert cited_blockers(body, PATTERNS) == [84]


def test_order_of_first_appearance_is_preserved():
    body = "Waiting on #30, blocked by #10, depends on #20."
    assert cited_blockers(body, PATTERNS) == [30, 10, 20]


def test_matching_is_case_insensitive():
    body = "BLOCKED BY #84 and DePeNdS On #91."
    assert cited_blockers(body, PATTERNS) == [84, 91]


def test_number_inside_inline_code_is_ignored():
    body = "Example: `blocked by #84`; actual text is similar to #91."
    assert cited_blockers(body, PATTERNS) == []


def test_number_inside_fenced_block_is_ignored():
    body = (
        "Example:\n"
        "```\n"
        "blocked by #84\n"
        "depends on #91\n"
        "```\n"
        "Actual: waiting on #105."
    )
    assert cited_blockers(body, PATTERNS) == [105]


def test_empty_and_none_body_return_empty_list():
    assert cited_blockers("", PATTERNS) == []
    assert cited_blockers(None, PATTERNS) == []


def test_uncompilable_pattern_raises_and_names_it():
    bad = r"blocked\s+by\s+#(\d+"
    with pytest.raises(ValueError) as excinfo:
        cited_blockers("blocked by #84", [bad])
    assert bad in str(excinfo.value)


def test_pattern_without_capture_group_raises():
    bad = r"blocked\s+by\s+#\d+"
    with pytest.raises(ValueError) as excinfo:
        cited_blockers("blocked by #84", [bad])
    assert bad in str(excinfo.value)


def test_all_blockers_closed_gives_unblock():
    findings = stale_blocks(
        [issue(10, "Blocked by #84 and waiting on #91.")],
        {84: "closed", 91: "closed"},
        PATTERNS,
    )
    assert findings == [
        {
            "number": 10,
            "blockers": [84, 91],
            "closed_blockers": [84, 91],
            "unknown_blockers": [],
            "verdict": "unblock",
        }
    ]


def test_one_open_blocker_gives_still_blocked():
    findings = stale_blocks(
        [issue(10, "Blocked by #84 and waiting on #91.")],
        {84: "closed", 91: "open"},
        PATTERNS,
    )
    assert findings[0]["verdict"] == "still-blocked"
    assert findings[0]["closed_blockers"] == [84]
    assert findings[0]["unknown_blockers"] == []


def test_unknown_blocker_gives_unknown_not_unblock():
    findings = stale_blocks(
        [issue(10, "Blocked by #84.")],
        {},
        PATTERNS,
    )
    assert findings[0]["verdict"] == "unknown"
    assert findings[0]["verdict"] != "unblock"
    assert findings[0]["unknown_blockers"] == [84]


def test_closed_plus_unknown_gives_unknown():
    findings = stale_blocks(
        [issue(10, "Blocked by #84 and waiting on #91.")],
        {84: "closed"},
        PATTERNS,
    )
    assert findings[0]["verdict"] == "unknown"
    assert findings[0]["verdict"] != "unblock"
    assert findings[0]["closed_blockers"] == [84]
    assert findings[0]["unknown_blockers"] == [91]


def test_issue_citing_nothing_produces_no_finding():
    findings = stale_blocks(
        [issue(10, "Similar to #84, but not blocked by anything.")],
        {84: "closed"},
        PATTERNS,
    )
    assert findings == []
    assert all(finding["number"] != 10 for finding in findings)


def test_findings_are_ordered_by_issue_number():
    findings = stale_blocks(
        [
            issue(30, "Blocked by #3."),
            issue(10, "Blocked by #1."),
            issue(20, "Blocked by #2."),
        ],
        {1: "closed", 2: "closed", 3: "closed"},
        PATTERNS,
    )
    assert [finding["number"] for finding in findings] == [10, 20, 30]


def test_blockers_field_lists_every_citation_even_when_still_blocked():
    findings = stale_blocks(
        [issue(10, "Blocked by #84, depends on #91, waiting on #105.")],
        {84: "closed", 91: "open", 105: "closed"},
        PATTERNS,
    )
    assert findings[0]["verdict"] == "still-blocked"
    assert findings[0]["blockers"] == [84, 91, 105]
    assert findings[0]["closed_blockers"] == [84, 105]
