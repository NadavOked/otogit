# tests/test_quota_routing.py
import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "routing.py"

)
_spec = _ilu.spec_from_file_location('routing', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Decision = _mod.Decision
route = _mod.route


def _base_rules(**overrides):
    rules = {
        "label_tiers": {"documentation": "local", "bug": "heavy", "question": "light"},
        "path_tiers": {"docs/": "local", "server/": "heavy", "tests/": "heavy"},
        "escalate_labels": ["safety-critical", "security"],
        "default_tier": "light",
    }
    rules.update(overrides)
    return rules


def test_single_label_routes_to_its_tier():
    d = route(["bug"], [], _base_rules())
    assert d.tier == "heavy"
    assert d.confident is True
    assert "bug" in d.reason
    assert ("label", "bug") in d.matched


def test_single_path_prefix_routes_to_its_tier():
    d = route([], ["docs/readme.md"], _base_rules())
    assert d.tier == "local"
    assert d.confident is True
    assert ("path", "docs/readme.md") in d.matched


def test_longest_path_prefix_wins():
    rules = _base_rules(
        path_tiers={"server/": "heavy", "server/boot/": "local"},
    )
    d = route([], ["server/boot/init.py"], rules)
    assert d.tier == "local"
    assert d.confident is True
    assert ("path", "server/boot/init.py") in d.matched


def test_strongest_tier_wins_when_signals_disagree():
    d = route(["documentation"], ["server/main.py"], _base_rules())
    assert d.tier == "heavy"
    assert d.confident is True


def test_escalate_label_forces_heavy_over_local():
    d = route(["documentation", "safety-critical"], [], _base_rules())
    assert d.tier == "heavy"
    assert d.confident is True
    assert "safety-critical" in d.reason


def test_escalate_label_reason_names_the_label():
    d = route(["security"], ["docs/a.md"], _base_rules())
    assert d.tier == "heavy"
    assert "security" in d.reason
    assert d.matched == (("label", "security"),)


def test_no_match_returns_default_and_confident_false():
    d = route(["unrelated"], ["other/file.py"], _base_rules())
    assert d.tier == "light"
    assert d.confident is False
    assert d.reason == "no rule matched"
    assert d.matched == ()


def test_any_match_sets_confident_true():
    d = route(["question"], [], _base_rules())
    assert d.confident is True
    assert d.tier == "light"


def test_empty_labels_and_paths_is_default_not_an_error():
    d = route([], [], _base_rules())
    assert d.tier == "light"
    assert d.confident is False
    assert d.reason == "no rule matched"
    assert d.matched == ()


def test_matched_field_lists_contributing_signals():
    d = route(["bug", "question"], ["tests/test_a.py"], _base_rules())
    # bug and tests/ both suggest heavy; question suggests light
    assert d.tier == "heavy"
    assert ("label", "bug") in d.matched
    assert ("path", "tests/test_a.py") in d.matched
    assert ("label", "question") not in d.matched


def test_coordinator_in_rules_raises():
    rules = _base_rules(label_tiers={"merge": "coordinator"})
    with pytest.raises(ValueError) as exc:
        route([], [], rules)
    assert "coordinator" in str(exc.value)


def test_unknown_tier_in_rules_raises_and_names_it():
    rules = _base_rules(label_tiers={"x": "ultra"})
    with pytest.raises(ValueError) as exc:
        route([], [], rules)
    assert "ultra" in str(exc.value)


def test_missing_default_tier_raises():
    rules = {
        "label_tiers": {},
        "path_tiers": {},
        "escalate_labels": [],
    }
    with pytest.raises(ValueError) as exc:
        route([], [], rules)
    assert "default_tier" in str(exc.value)


def test_default_tier_of_coordinator_raises():
    rules = _base_rules(default_tier="coordinator")
    with pytest.raises(ValueError) as exc:
        route([], [], rules)
    assert "coordinator" in str(exc.value)


def test_absent_optional_rule_sections_are_treated_as_empty():
    rules = {"default_tier": "light"}
    d = route(["anything"], ["anywhere"], rules)
    assert d.tier == "light"
    assert d.confident is False
    assert d.reason == "no rule matched"


def test_path_match_is_prefix_not_substring():
    d = route([], ["x/server/y.py"], _base_rules())
    assert d.tier == "light"
    assert d.confident is False
    assert d.reason == "no rule matched"


def test_decision_is_deterministic():
    labels = ["question", "bug", "documentation"]
    paths = ["tests/a.py", "docs/b.md", "server/c.py"]
    d1 = route(labels, paths, _base_rules())
    d2 = route(reversed(labels), reversed(paths), _base_rules())
    assert d1 == d2
    assert d1.tier == "heavy"
