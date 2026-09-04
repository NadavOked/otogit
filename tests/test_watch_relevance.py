# tests/test_watch_relevance.py
"""Tests for tools.agents.watch.relevance."""

import pytest
import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "watch" / "relevance.py"

)
_spec = _ilu.spec_from_file_location('relevance', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Relevance = _mod.Relevance
filter_entries = _mod.filter_entries
score_entry = _mod.score_entry

TOPICS = {
    "concurrency": {
        "terms": ["concurrency", "queued run", "cancel-in-progress"],
        "touches": [".github/workflows/"],
    },
    "branch-protection": {
        "terms": ["branch protection", "ruleset", "required check"],
        "touches": [".github/"],
    },
}

def _entry(id="e1", title="", body="", published="2024-01-01"):
    return {"id": id, "title": title, "body": body, "published": published}

def test_single_term_match_is_relevant():
    e = _entry(title="New concurrency limit")
    r = score_entry(e, TOPICS)
    assert r.verdict == "relevant"
    assert r.topics == ("concurrency",)

def test_match_is_case_insensitive():
    e = _entry(title="CONCURRENCY changed")
    r = score_entry(e, TOPICS)
    assert r.verdict == "relevant"
    assert "concurrency" in r.matches

def test_plural_form_matches():
    e = _entry(title="Updated rulesets behaviour")
    r = score_entry(e, TOPICS)
    assert r.verdict == "relevant"
    assert "ruleset" in r.matches

def test_substring_inside_a_longer_word_does_not_match():
    e = _entry(title="The runner failed")
    r = score_entry(e, {"run": {"terms": ["run"], "touches": []}})
    assert r.verdict == "not-relevant"

def test_match_in_body_counts_as_well_as_title():
    e = _entry(title="Misc", body="We added a new ruleset option")
    r = score_entry(e, TOPICS)
    assert r.verdict == "relevant"
    assert "ruleset" in r.matches

def test_two_topics_matching_are_both_reported_and_sorted():
    e = _entry(title="concurrency and ruleset updates")
    r = score_entry(e, TOPICS)
    assert r.verdict == "relevant"
    assert r.topics == ("branch-protection", "concurrency")

def test_touches_is_the_union_of_matched_topics():
    e = _entry(title="concurrency and ruleset updates")
    r = score_entry(e, TOPICS)
    assert r.touches == (".github/", ".github/workflows/")

def test_matches_field_lists_the_terms_verbatim():
    e = _entry(title="Ruleset and CONCURRENCY")
    r = score_entry(e, TOPICS)
    assert r.matches == ("concurrency", "ruleset")

def test_no_match_is_not_relevant():
    e = _entry(title="Unrelated release notes")
    r = score_entry(e, TOPICS)
    assert r.verdict == "not-relevant"
    assert r.topics == ()
    assert r.matches == ()

def test_empty_title_and_body_is_undecidable_not_not_relevant():
    e = _entry(title="", body="")
    r = score_entry(e, TOPICS)
    assert r.verdict == "undecidable"

def test_non_string_body_is_undecidable():
    e = {"id": "e1", "title": "ok", "body": 123, "published": "2024-01-01"}
    r = score_entry(e, TOPICS)
    assert r.verdict == "undecidable"

def test_missing_id_is_undecidable():
    e = {"title": "concurrency", "body": "x", "published": "2024-01-01"}
    r = score_entry(e, TOPICS)
    assert r.verdict == "undecidable"

def test_topic_with_empty_terms_raises_and_names_it():
    bad = {"empty": {"terms": [], "touches": []}}
    with pytest.raises(ValueError, match="empty"):
        score_entry(_entry(title="x"), bad)

def test_every_entry_appears_in_exactly_one_output_list():
    entries = [
        _entry(id="a", title="concurrency"),
        _entry(id="b", title="nothing"),
        _entry(id="c", title="", body=""),
    ]
    relevant, dropped, _ = filter_entries(entries, TOPICS)
    all_ids = {r.id for r in relevant} | {r.id for r in dropped}
    assert all_ids == {"a", "b", "c"}
    assert len(relevant) + len(dropped) == 3

def test_summary_counts_add_up_to_scanned():
    entries = [
        _entry(id="a", title="concurrency"),
        _entry(id="b", title="nothing"),
        _entry(id="c", title="", body=""),
    ]
    _, _, summary = filter_entries(entries, TOPICS)
    assert summary["scanned"] == 3
    assert (
        summary["relevant"] + summary["not_relevant"] + summary["undecidable"]
        == summary["scanned"]
    )

def test_summary_records_earliest_and_latest_published():
    entries = [
        _entry(id="a", title="x", published="2024-03-01"),
        _entry(id="b", title="y", published="2024-01-15"),
        _entry(id="c", title="z", published="2024-02-10"),
    ]
    _, _, summary = filter_entries(entries, TOPICS)
    assert summary["earliest"] == "2024-01-15"
    assert summary["latest"] == "2024-03-01"

def test_summary_earliest_and_latest_are_none_when_no_dates():
    entries = [
        {"id": "a", "title": "x", "body": "y"},
        {"id": "b", "title": "p", "body": "q"},
    ]
    _, _, summary = filter_entries(entries, TOPICS)
    assert summary["earliest"] is None
    assert summary["latest"] is None

def test_empty_entries_gives_scanned_zero():
    relevant, dropped, summary = filter_entries([], TOPICS)
    assert summary["scanned"] == 0
    assert relevant == []
    assert dropped == []
    assert summary["earliest"] is None
    assert summary["latest"] is None

def test_relevant_preserves_input_order():
    entries = [
        _entry(id="first", title="ruleset"),
        _entry(id="second", title="nothing"),
        _entry(id="third", title="concurrency"),
    ]
    relevant, _, _ = filter_entries(entries, TOPICS)
    assert [r.id for r in relevant] == ["first", "third"]

def test_filtering_is_deterministic():
    entries = [
        _entry(id="a", title="concurrency and ruleset"),
        _entry(id="b", title="nothing interesting"),
    ]
    r1, d1, s1 = filter_entries(entries, TOPICS)
    r2, d2, s2 = filter_entries(entries, TOPICS)
    assert r1 == r2
    assert d1 == d2
    assert s1 == s2
