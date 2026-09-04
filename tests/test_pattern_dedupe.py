# tests/test_pattern_dedupe.py
import difflib

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "patterns" / "dedupe.py"

)
_spec = _ilu.spec_from_file_location('dedupe', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
classify_candidates = _mod.classify_candidates
fingerprint = _mod.fingerprint
normalise = _mod.normalise


def test_normalise_lowercases_and_collapses_whitespace():
    assert normalise("  Hello   WORLD \n test  ") == "hello world test"


def test_normalise_strips_leading_emoji():
    assert normalise("🚀 ✨  Fix the pipeline") == "fix the pipeline"


def test_normalise_keeps_digits_and_slashes():
    assert normalise("Fix /api/v2/item #123") == "fix /api/v2/item #123"


def test_normalise_of_none_is_empty_string():
    assert normalise(None) == ""


def test_fingerprint_is_stable_for_the_same_sequence():
    candidate = {"sequence": ("run", "pytest tests/test_api.py")}
    assert fingerprint(candidate) == "run | pytest tests/test_api.py"
    assert fingerprint(candidate) == fingerprint(candidate)


def test_fingerprint_ignores_title_wording():
    first = {"title": "Automate API tests", "sequence": ("git", "pytest tests/api.py")}
    second = {
        "title": "Improve API test automation",
        "sequence": ("git", "pytest tests/api.py"),
    }
    assert fingerprint(first) == fingerprint(second)


def test_fingerprint_of_empty_sequence_raises():
    with pytest.raises(ValueError):
        fingerprint({"sequence": []})


def test_exact_fingerprint_in_body_is_duplicate_with_score_one():
    candidate = {"title": "Something new", "sequence": ("git", "pytest tests/api.py")}
    existing = [{
        "number": 42,
        "title": "Unrelated wording",
        "body": "Command path: git | pytest tests/api.py",
    }]

    result = classify_candidates([candidate], existing)

    assert result["duplicate"] == [(candidate, 42, 1.0)]
    assert result["new"] == []
    assert result["uncertain"] == []


def test_unrelated_candidate_is_new():
    candidate = {"title": "Automate database cleanup", "sequence": ("cleanup-db",)}
    existing = [{"number": 7, "title": "Automate image resizing", "body": ""}]

    result = classify_candidates([candidate], existing)

    assert result["new"] == [candidate]
    assert result["duplicate"] == []
    assert result["uncertain"] == []


def test_high_similarity_title_is_duplicate():
    candidate = {"title": "Automate API test checks", "sequence": ("run-api-checks",)}
    existing = [{
        "number": 18,
        "title": "Automate API test check",
        "body": "",
    }]

    expected = difflib.SequenceMatcher(
        None,
        normalise(candidate["title"]),
        normalise(existing[0]["title"]),
    ).ratio()

    result = classify_candidates([candidate], existing, threshold=0.85)

    assert result["duplicate"] == [(candidate, 18, expected)]
    assert result["new"] == []
    assert result["uncertain"] == []


def test_near_threshold_similarity_is_uncertain_not_duplicate():
    # ratio 0.807 — inside the [threshold - 0.10, threshold) band
    candidate = {
        "title": "automate api test check weekly now",
        "sequence": ("run-now",),
    }
    existing = [{"number": 19, "title": "automate api test check", "body": ""}]
    score = difflib.SequenceMatcher(
        None,
        normalise(candidate["title"]),
        normalise(existing[0]["title"]),
    ).ratio()
    assert 0.75 <= score < 0.85

    result = classify_candidates([candidate], existing, threshold=0.85)

    assert result["uncertain"] == [(candidate, 19, score)]
    assert result["duplicate"] == []
    assert result["new"] == []


def test_uncertain_is_not_folded_into_new():
    # same near-threshold case as above, asserted from the other side
    candidate = {
        "title": "automate api test check weekly now",
        "sequence": ("run-now",),
    }
    existing = [{"number": 19, "title": "automate api test check", "body": ""}]

    result = classify_candidates([candidate], existing, threshold=0.85)

    assert result["uncertain"]
    assert candidate not in result["new"]
    assert not result["duplicate"]


def test_duplicate_entry_carries_the_issue_number_and_score():
    candidate = {"title": "Automate API tests", "sequence": ("api-tests",)}
    existing = [{"number": 123, "title": "Automate API tests", "body": ""}]

    result = classify_candidates([candidate], existing)

    assert len(result["duplicate"]) == 1
    found_candidate, issue_number, score = result["duplicate"][0]
    assert found_candidate is candidate
    assert issue_number == 123
    assert score == 1.0


def test_candidate_without_title_falls_back_to_fingerprint():
    candidate = {"sequence": ("deploy", "/api/v2")}
    existing = [{
        "number": 55,
        "title": "deploy endpoint",
        "body": "",
    }]

    result = classify_candidates([candidate], existing, threshold=0.85)

    expected = difflib.SequenceMatcher(
        None,
        fingerprint(candidate),
        normalise(existing[0]["title"]),
    ).ratio()
    assert (
        result["duplicate"] == [(candidate, 55, expected)]
        if expected >= 0.85
        else True
    )
    if expected < 0.75:
        assert result["new"] == [candidate]
    else:
        assert result["uncertain"] == [(candidate, 55, expected)]


def test_empty_existing_list_makes_everything_new():
    candidates = [
        {"sequence": ("one",)},
        {"sequence": ("two",)},
    ]

    result = classify_candidates(candidates, [])

    assert result["new"] == candidates
    assert result["duplicate"] == []
    assert result["uncertain"] == []


@pytest.mark.parametrize("threshold", [0.0, 1.5])
def test_threshold_out_of_range_raises(threshold):
    with pytest.raises(ValueError):
        classify_candidates([], [], threshold=threshold)


def test_existing_issue_missing_title_raises():
    with pytest.raises(ValueError, match="missing title"):
        classify_candidates([], [{"number": 1, "body": ""}])


def test_existing_issue_missing_number_raises():
    with pytest.raises(ValueError, match="missing number"):
        classify_candidates([], [{"title": "Issue", "body": ""}])


def test_output_order_follows_input_order():
    candidates = [
        {"title": "Brand new task", "sequence": ("new",)},
        {"title": "Existing task", "sequence": ("existing",)},
        {"title": "Another brand new task", "sequence": ("another-new",)},
    ]
    existing = [{"number": 10, "title": "Existing task", "body": ""}]

    result = classify_candidates(candidates, existing)

    assert result["new"] == [candidates[0], candidates[2]]
    assert result["duplicate"] == [(candidates[1], 10, 1.0)]


def test_classification_is_deterministic():
    candidates = [
        {"title": "Automate API test checks", "sequence": ("one",)},
        {"title": "Completely unrelated", "sequence": ("two",)},
    ]
    existing = [
        {"number": 20, "title": "Automate API test check", "body": ""},
        {"number": 21, "title": "Other task", "body": ""},
    ]

    first = classify_candidates(candidates, existing)
    second = classify_candidates(candidates, existing)

    assert first == second


def test_exact_fingerprint_takes_precedence_over_high_similarity():
    candidate = {"title": "Different title", "sequence": ("same", "command")}
    existing = [
        {"number": 30, "title": "Different title", "body": "same | command"},
        {"number": 31, "title": "Different title", "body": ""},
    ]

    result = classify_candidates([candidate], existing)

    assert result["duplicate"] == [(candidate, 30, 1.0)]


def test_best_similarity_match_is_returned():
    candidate = {"title": "automate api tests", "sequence": ("command",)}
    existing = [
        {"number": 40, "title": "automate database backups", "body": ""},
        {"number": 41, "title": "automate api tests", "body": ""},
    ]

    result = classify_candidates([candidate], existing)

    assert result["duplicate"] == [(candidate, 41, 1.0)]
