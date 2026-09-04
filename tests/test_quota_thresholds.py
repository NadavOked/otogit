# tests/test_quota_thresholds.py
"""Tests for tools/agents/quota/thresholds.py"""

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "thresholds.py"

)
_spec = _ilu.spec_from_file_location('thresholds', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Verdict = _mod.Verdict
may_delegate = _mod.may_delegate
verdict = _mod.verdict
worst = _mod.worst


def test_zero_usage_is_ok():
    v = verdict(0, 100, "known")
    assert v.level == "ok"
    assert v.ratio == 0.0
    assert v.reason == ""
    assert v.state == "known"
    assert v.burn is None


def test_seventy_nine_percent_is_ok():
    v = verdict(79, 100, "known")
    assert v.level == "ok"
    assert v.ratio == 0.79
    assert v.reason == ""


def test_exactly_eighty_percent_is_warn():
    v = verdict(80, 100, "known")
    assert v.level == "warn"
    assert v.ratio == 0.80
    assert v.reason == "eighty-percent"


def test_exactly_ninety_percent_is_hold():
    v = verdict(90, 100, "known")
    assert v.level == "hold"
    assert v.ratio == 0.90
    assert v.reason == "ninety-percent"


def test_exactly_one_hundred_percent_is_dead():
    v = verdict(100, 100, "known")
    assert v.level == "dead"
    assert v.ratio == 1.0
    assert v.reason == "at-limit"


def test_over_one_hundred_percent_is_dead():
    v = verdict(150, 100, "known")
    assert v.level == "dead"
    assert v.ratio == 1.5
    assert v.reason == "at-limit"


def test_state_unknown_is_unknown_even_with_good_numbers():
    v = verdict(1, 100, "unknown")
    assert v.level == "unknown"
    assert v.ratio is None
    assert v.reason == "state-unknown"
    assert v.level != "ok"


def test_no_limit_declared_is_unknown_not_ok():
    v = verdict(50, None, "known")
    assert v.level == "unknown"
    assert v.ratio is None
    assert v.reason == "no-limit-declared"
    assert v.level != "ok"


def test_used_none_is_unknown_not_zero():
    v = verdict(None, 100, "known")
    assert v.level == "unknown"
    assert v.ratio is None
    assert v.reason == "usage-not-counted"
    assert v.level != "ok"
    assert v.ratio != 0.0


def test_estimated_state_keeps_the_level_but_marks_provenance():
    v = verdict(85, 100, "estimated")
    assert v.level == "warn"
    assert v.ratio == 0.85
    assert v.state == "estimated"
    assert v.reason == "eighty-percent"


def test_limit_zero_raises():
    with pytest.raises(ValueError):
        verdict(0, 0, "known")


def test_negative_used_raises():
    with pytest.raises(ValueError):
        verdict(-1, 100, "known")


def test_boolean_used_raises():
    with pytest.raises(ValueError):
        verdict(True, 100, "known")


def test_bad_state_string_raises():
    with pytest.raises(ValueError):
        verdict(10, 100, "guess")


def test_fraction_elapsed_out_of_range_raises():
    with pytest.raises(ValueError):
        verdict(50, 100, "known", fraction_elapsed=1.0)
    with pytest.raises(ValueError):
        verdict(50, 100, "known", fraction_elapsed=-0.1)


def test_burn_ahead_behind_on_pace():
    # fixed ratio 0.50
    ahead = verdict(50, 100, "known", fraction_elapsed=0.20)
    assert ahead.burn == "ahead"
    behind = verdict(50, 100, "known", fraction_elapsed=0.80)
    assert behind.burn == "behind"
    on_pace = verdict(50, 100, "known", fraction_elapsed=0.45)
    assert on_pace.burn == "on-pace"


def test_burn_is_none_when_ratio_is_none():
    v = verdict(None, 100, "known", fraction_elapsed=0.5)
    assert v.ratio is None
    assert v.burn is None
    v2 = verdict(10, 100, "unknown", fraction_elapsed=0.5)
    assert v2.ratio is None
    assert v2.burn is None


def test_burn_is_none_when_fraction_not_given():
    v = verdict(50, 100, "known")
    assert v.burn is None


def test_worst_picks_dead_over_everything():
    items = [
        verdict(50, 100, "known"),
        verdict(95, 100, "known"),
        verdict(100, 100, "known"),
        verdict(None, None, "unknown"),
    ]
    w = worst(items)
    assert w.level == "dead"


def test_worst_picks_unknown_over_hold():
    items = [
        verdict(95, 100, "known"),  # hold
        verdict(10, 100, "unknown"),
    ]
    w = worst(items)
    assert w.level == "unknown"


def test_worst_of_empty_is_unknown_not_ok():
    w = worst([])
    assert w.level == "unknown"
    assert w.reason == "nothing-to-judge"
    assert w.level != "ok"


def test_may_delegate_false_for_unknown():
    v = verdict(10, 100, "unknown")
    assert may_delegate(v) is False


def test_may_delegate_true_for_ok_and_warn_only():
    assert may_delegate(verdict(0, 100, "known")) is True
    assert may_delegate(verdict(85, 100, "known")) is True
    assert may_delegate(verdict(95, 100, "known")) is False
    assert may_delegate(verdict(100, 100, "known")) is False
    assert may_delegate(verdict(None, None, "unknown")) is False
