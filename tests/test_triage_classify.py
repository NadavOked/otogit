# tests/test_triage_classify.py
"""Tests for automated agent triage classification logic."""

import pytest
import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "triage" / "classify.py"

)
_spec = _ilu.spec_from_file_location('classify', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Verdict = _mod.Verdict
classify = _mod.classify


@pytest.fixture
def base_rules():
    return {
        "solo_ok_prefixes": ["tools/", "docs/", ".github/"],
        "ci_check_names": ["tests", "shellcheck", "codeql"],
        "blocked_reasons": {
            "needs:metal": ["physical machine", "real disk", "bare metal"],
            "needs:fleet": ["multicast", "classroom", "several machines"],
            "needs:real-server": ["systemd", "sshd"],
            "needs:browser": ["browser", "screenshot"],
            "blocked": ["decision", "needs a ruling"],
        },
        "human_only_labels": ["security"],
    }


def test_tools_path_plus_named_ci_check_is_solo_ok(base_rules):
    issue = {
        "number": 1,
        "title": "Fix tool and run tests",
        "body": "Running tests should confirm fix.",
        "labels": [],
        "paths": ["tools/helper.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:solo-ok",)
    assert verdict.confident is True
    assert verdict.needs_human is False


def test_tools_path_without_ci_check_is_ready_not_solo_ok(base_rules):
    issue = {
        "number": 2,
        "title": "Update tool documentation",
        "body": "No validation checks available.",
        "labels": [],
        "paths": ["tools/helper.py"],
    }
    verdict = classify(issue, base_rules)
    assert "agent:solo-ok" not in verdict.labels
    assert verdict.labels == ("agent:ready",)


def test_ci_check_without_allowed_paths_is_ready_not_solo_ok(base_rules):
    issue = {
        "number": 3,
        "title": "Update core module",
        "body": "Run tests to verify.",
        "labels": [],
        "paths": ["src/core.py"],
    }
    verdict = classify(issue, base_rules)
    assert "agent:solo-ok" not in verdict.labels
    assert verdict.labels == ("agent:ready",)


def test_server_path_is_never_solo_ok(base_rules):
    issue = {
        "number": 4,
        "title": "Deploy server updates",
        "body": "Passes tests pipeline.",
        "labels": [],
        "paths": ["server/config.json"],
    }
    verdict = classify(issue, base_rules)
    assert "agent:solo-ok" not in verdict.labels
    assert verdict.labels == ("agent:ready",)


def test_mixed_paths_one_outside_prefixes_is_not_solo_ok(base_rules):
    issue = {
        "number": 5,
        "title": "Update tools and config",
        "body": "Covered by tests.",
        "labels": [],
        "paths": ["tools/a.py", "docs/b.md", ".github/ci.yml", "server/c.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:ready",)


def test_empty_paths_is_ready_and_not_confident(base_rules):
    issue = {
        "number": 6,
        "title": "General investigation",
        "body": "Run tests.",
        "labels": [],
        "paths": [],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:ready",)
    assert verdict.confident is False


def test_security_label_forces_blocked_and_needs_human(base_rules):
    issue = {
        "number": 7,
        "title": "Security patch",
        "body": "Needs review.",
        "labels": ["security"],
        "paths": ["tools/sec.py"],
    }
    verdict = classify(issue, base_rules)
    assert "agent:blocked" in verdict.labels
    assert verdict.needs_human is True


def test_security_label_beats_perfect_solo_ok_conditions(base_rules):
    issue = {
        "number": 8,
        "title": "Security update with tests",
        "body": "Has tests passing.",
        "labels": ["security"],
        "paths": ["tools/sec.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:blocked", "blocked")
    assert verdict.needs_human is True


def test_blocked_phrase_yields_its_reason_label(base_rules):
    issue = {
        "number": 9,
        "title": "Hardware test",
        "body": "Requires a physical machine for execution.",
        "labels": [],
        "paths": ["tools/hw.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:blocked", "needs:metal")


def test_blocked_signal_without_matching_phrase_sets_needs_human(base_rules):
    issue = {
        "number": 10,
        "title": "Task is blocked",
        "body": "Currently blocked due to upstream dependency.",
        "labels": [],
        "paths": ["tools/pkg.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:blocked",)
    assert verdict.needs_human is True
    assert verdict.confident is False


def test_existing_human_label_is_preserved_not_overruled(base_rules):
    issue = {
        "number": 11,
        "title": "Pre-assigned task",
        "body": "Already triaged.",
        "labels": ["agent:solo-ok"],
        "paths": ["server/main.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:solo-ok",)
    assert verdict.confident is True


def test_evidence_strings_occur_in_the_issue_text(base_rules):
    issue = {
        "number": 12,
        "title": "Run shellcheck on scripts",
        "body": "Ensure shellcheck passes completely.",
        "labels": [],
        "paths": ["tools/script.sh"],
    }
    verdict = classify(issue, base_rules)
    text = f"{issue['title']}\n{issue['body']}"
    for ev in verdict.evidence:
        assert ev in text


def test_confident_verdict_has_at_least_one_evidence_string(base_rules):
    issue = {
        "number": 13,
        "title": "Add tools script",
        "body": "Verified with codeql.",
        "labels": [],
        "paths": ["tools/app.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.confident is True
    assert len(verdict.evidence) >= 1


def test_phrase_matching_is_case_insensitive(base_rules):
    issue = {
        "number": 14,
        "title": "Run tests on Bare Metal",
        "body": "Needs BARE METAL setup.",
        "labels": [],
        "paths": ["tools/app.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:blocked", "needs:metal")


def test_phrase_matching_ignores_paths(base_rules):
    issue = {
        "number": 15,
        "title": "Normal task with tests",
        "body": "Running tests.",
        "labels": [],
        "paths": ["tools/bare_metal/app.py"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:solo-ok",)


def test_labels_are_sorted_and_deduplicated(base_rules):
    issue = {
        "number": 16,
        "title": "Needs decision and ruling",
        "body": "A decision is required.",
        "labels": [],
        "paths": ["tools/app.py"],
    }
    verdict = classify(issue, base_rules)
    assert isinstance(verdict.labels, tuple)
    assert verdict.labels == tuple(sorted(list(set(verdict.labels))))


def test_malformed_rules_raise(base_rules):
    issue = {"number": 17, "title": "t", "body": "b", "labels": [], "paths": []}

    bad_rules_1 = base_rules.copy()
    del bad_rules_1["solo_ok_prefixes"]
    with pytest.raises(ValueError):
        classify(issue, bad_rules_1)

    bad_rules_2 = base_rules.copy()
    bad_rules_2["blocked_reasons"] = "not a dict"
    with pytest.raises(ValueError):
        classify(issue, bad_rules_2)

    bad_rules_3 = base_rules.copy()
    bad_rules_3["ci_check_names"] = []
    with pytest.raises(ValueError):
        classify(issue, bad_rules_3)


def test_classify_is_deterministic(base_rules):
    issue = {
        "number": 18,
        "title": "Fix tool and run tests",
        "body": "Running tests should confirm fix.",
        "labels": [],
        "paths": ["tools/helper.py"],
    }
    v1 = classify(issue, base_rules)
    v2 = classify(issue, base_rules)
    assert v1 == v2


def test_human_only_label_beside_an_agent_label_still_blocks(base_rules):
    # F01 rule 1: an issue carrying a human_only_labels label is agent:blocked,
    # "no exceptions". Rule 5 (do not overrule a human's label) must not be
    # read as an exception to it — otherwise a security issue whose triage
    # already says agent:solo-ok is handed to an autonomous agent.
    issue = {
        "number": 19,
        "title": "Security fix with tests",
        "body": "Has tests passing.",
        "labels": ["security", "agent:solo-ok"],
        "paths": ["tools/sec.py"],
    }
    verdict = classify(issue, base_rules)
    assert "agent:blocked" in verdict.labels
    assert "agent:solo-ok" not in verdict.labels
    assert "agent:ready" not in verdict.labels
    assert verdict.needs_human is True


def test_human_only_label_beside_agent_ready_still_blocks(base_rules):
    issue = {
        "number": 20,
        "title": "Security review of docs",
        "body": "Run shellcheck first.",
        "labels": ["agent:ready", "security"],
        "paths": ["docs/x.md"],
    }
    verdict = classify(issue, base_rules)
    assert verdict.labels == ("agent:blocked", "blocked")
    assert verdict.needs_human is True
