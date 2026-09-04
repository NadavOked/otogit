# tests/test_quota_report.py
from datetime import datetime, timedelta, timezone
import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "report.py"

)
_spec = _ilu.spec_from_file_location('report', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
render = _mod.render
summary_line = _mod.summary_line


@pytest.fixture
def now():
    return datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_known_row_renders_used_limit_and_pct(now):
    row = {
        "key": "groq/work-account", "level": "ok", "state": "known",
        "used": 50, "limit": 100, "ratio": 0.5,
        "window_end": now + timedelta(hours=1), "burn": "on-pace"
    }
    out = render([row], now)
    assert "50" in out
    assert "100" in out
    assert "50%" in out


def test_none_used_renders_question_mark_not_zero(now):
    row = {
        "key": "groq/work-account", "level": "ok", "state": "known",
        "used": None, "limit": 100, "ratio": None,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    lines = out.splitlines()
    data_line = lines[2]
    parts = data_line.split()
    assert parts[1] == "?"
    assert "0" not in parts[1]


def test_none_limit_renders_question_mark(now):
    row = {
        "key": "groq/work-account", "level": "ok", "state": "known",
        "used": 10, "limit": None, "ratio": None,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    parts = out.splitlines()[2].split()
    assert parts[2] == "?"


def test_none_ratio_renders_question_mark_in_pct(now):
    row = {
        "key": "groq/work-account", "level": "ok", "state": "known",
        "used": 10, "limit": 100, "ratio": None,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    parts = out.splitlines()[2].split()
    assert parts[3] == "?"


def test_estimated_state_suffixes_pct_with_tilde(now):
    row = {
        "key": "groq/work-account", "level": "ok", "state": "estimated",
        "used": 62, "limit": 100, "ratio": 0.62,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    assert "62%~" in out


def test_known_state_has_no_tilde(now):
    row = {
        "key": "groq/work-account", "level": "ok", "state": "known",
        "used": 62, "limit": 100, "ratio": 0.62,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    assert "62%" in out
    assert "62%~" not in out


def test_unknown_level_row_is_present_in_output(now):
    row = {
        "key": "unmeasurable-key", "level": "unknown", "state": "unknown",
        "used": None, "limit": None, "ratio": None,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    assert "unmeasurable-key" in out


def test_unknown_level_state_cell_is_capitalised(now):
    row = {
        "key": "key1", "level": "unknown", "state": "unknown",
        "used": None, "limit": None, "ratio": None,
        "window_end": None, "burn": None
    }
    out = render([row], now)
    assert "UNKNOWN" in out


def test_resets_renders_hours_and_minutes(now):
    row = {
        "key": "key1", "level": "ok", "state": "known",
        "used": 1, "limit": 2, "ratio": 0.5,
        "window_end": now + timedelta(hours=4, minutes=12), "burn": "on-pace"
    }
    out = render([row], now)
    assert "4h12m" in out


def test_resets_renders_days_for_long_windows(now):
    row = {
        "key": "key1", "level": "ok", "state": "known",
        "used": 1, "limit": 2, "ratio": 0.5,
        "window_end": now + timedelta(days=2, hours=3), "burn": "on-pace"
    }
    out = render([row], now)
    assert "2d3h" in out


def test_resets_none_is_question_mark(now):
    row = {
        "key": "key1", "level": "ok", "state": "known",
        "used": 1, "limit": 2, "ratio": 0.5,
        "window_end": None, "burn": "on-pace"
    }
    out = render([row], now)
    parts = out.splitlines()[2].split()
    assert parts[5] == "?"


def test_resets_in_the_past_is_due_not_negative(now):
    row = {
        "key": "key1", "level": "ok", "state": "known",
        "used": 1, "limit": 2, "ratio": 0.5,
        "window_end": now - timedelta(minutes=5), "burn": "on-pace"
    }
    out = render([row], now)
    assert "due" in out
    parts = out.splitlines()[2].split()
    assert "-" not in parts[5]


def test_rows_sorted_dead_unknown_hold_warn_ok(now):
    levels = ["ok", "warn", "hold", "unknown", "dead"]
    rows = [
        {
            "key": f"k_{lvl}",
            "level": lvl,
            "state": "known" if lvl != "unknown" else "unknown",
            "used": None,
            "limit": None,
            "ratio": None,
            "window_end": None,
            "burn": None,
        }
        for lvl in levels
    ]
    out = render(rows, now)
    lines = out.splitlines()[2:]
    rendered_keys = [line.split()[0] for line in lines]
    assert rendered_keys == ["k_dead", "k_unknown", "k_hold", "k_warn", "k_ok"]


def test_ties_within_a_level_sort_by_key(now):
    rows = [
        {
            "key": "b_key",
            "level": "ok",
            "state": "known",
            "used": 1,
            "limit": 2,
            "ratio": 0.5,
            "window_end": None,
            "burn": None,
        },
        {
            "key": "a_key",
            "level": "ok",
            "state": "known",
            "used": 1,
            "limit": 2,
            "ratio": 0.5,
            "window_end": None,
            "burn": None,
        },
    ]
    out = render(rows, now)
    lines = out.splitlines()[2:]
    assert lines[0].startswith("a_key")
    assert lines[1].startswith("b_key")


def test_width_truncates_key_column_only(now):
    row = {
        "key": "very-long-account-key-name", "level": "ok", "state": "known",
        "used": 50, "limit": 100, "ratio": 0.5, "window_end": None, "burn": "ahead"
    }
    out = render([row], now, width=10)
    lines = out.splitlines()
    assert "very-long-…" in lines[2]
    assert "50" in lines[2]
    assert "100" in lines[2]


def test_malformed_row_renders_as_malformed_and_is_not_dropped(now):
    row = {"invalid": "dict"}
    out = render([row], now)
    assert "MALFORMED" in out
    lines = out.splitlines()[2:]
    assert len(lines) == 1


def test_header_and_separator_present(now):
    out = render([], now)
    lines = out.splitlines()
    assert lines[0].startswith("KEY")
    assert "USED" in lines[0]
    assert lines[1].startswith("-")


def test_no_ansi_escape_codes_in_output(now):
    row = {
        "key": "key1", "level": "dead", "state": "known",
        "used": 100, "limit": 100, "ratio": 1.0,
        "window_end": None, "burn": "ahead"
    }
    out = render([row], now)
    assert "\x1b" not in out


def test_summary_counts_all_five_levels_including_zeros():
    rows = [{"level": "ok", "state": "known"}]
    res = summary_line(rows)
    assert "1 ok, 0 warn, 0 hold, 0 dead, 0 unknown" in res


def test_summary_reports_measured_over_total():
    rows = [
        {"level": "ok", "state": "known"},
        {"level": "warn", "state": "estimated"},
        {"level": "unknown", "state": "unknown"},
    ]
    res = summary_line(rows)
    assert "(1 of 3 keys measured)" in res


def test_summary_of_empty_rows_is_the_no_data_sentence():
    res = summary_line([])
    assert res == "fleet: no data"
    assert "0 ok" not in res


def test_naive_now_raises():
    naive_dt = datetime(2026, 9, 4, 12, 0, 0)
    with pytest.raises(ValueError):
        render([], naive_dt)


def test_output_is_stable(now):
    rows = [
        {
            "key": "a",
            "level": "ok",
            "state": "known",
            "used": 10,
            "limit": 100,
            "ratio": 0.1,
            "window_end": None,
            "burn": "ahead",
        },
        {
            "key": "b",
            "level": "warn",
            "state": "estimated",
            "used": 80,
            "limit": 100,
            "ratio": 0.8,
            "window_end": None,
            "burn": "behind",
        },
    ]
    out1 = render(rows, now)
    out2 = render(rows, now)
    assert out1 == out2
