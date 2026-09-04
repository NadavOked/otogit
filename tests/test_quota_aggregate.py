# tests/test_quota_aggregate.py
from datetime import datetime, timezone

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "aggregate.py"

)
_spec = _ilu.spec_from_file_location('aggregate', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
fold = _mod.fold


UTC = timezone.utc
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
START = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
END = datetime(2026, 1, 16, 0, 0, tzinfo=UTC)


def row(ts="2026-01-15T10:00:00Z", key="k", requests=1,
        input_tokens=10, output_tokens=20):
    return {
        "ts": ts,
        "key": key,
        "requests": requests,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def key_of(item):
    return item.get("key")


def window_of(key):
    return {"window": "daily"}


def bounds_of(spec, now):
    return START, END


def test_single_row_inside_window_is_counted():
    totals, excluded = fold([row()], NOW, key_of, window_of, bounds_of)
    assert totals["k"]["requests"] == 1
    assert totals["k"]["input_tokens"] == 10
    assert totals["k"]["output_tokens"] == 20
    assert totals["k"]["calls"] == 1
    assert excluded == []


def test_two_rows_same_key_are_summed_and_calls_is_two():
    totals, excluded = fold(
        [row(requests=2, input_tokens=3, output_tokens=4),
         row(requests=5, input_tokens=6, output_tokens=7)],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals["k"] == {
        "requests": 7,
        "input_tokens": 9,
        "output_tokens": 11,
        "calls": 2,
        "window_start": START,
        "window_end": END,
    }
    assert excluded == []


def test_two_keys_are_kept_apart():
    totals, excluded = fold(
        [row(key="a", requests=2), row(key="b", requests=3)],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals["a"]["requests"] == 2
    assert totals["b"]["requests"] == 3
    assert excluded == []


def test_two_keys_with_different_windows_get_their_own_bounds():
    bounds = {
        "a": (
            datetime(2026, 1, 15, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 16, 0, 0, tzinfo=UTC),
        ),
        "b": (
            datetime(2026, 1, 15, 6, 0, tzinfo=UTC),
            datetime(2026, 1, 15, 18, 0, tzinfo=UTC),
        ),
    }

    def windows(key):
        return {"name": key}

    def get_bounds(spec, now):
        return bounds[spec["name"]]

    totals, excluded = fold(
        [row(key="a"), row(key="b")],
        NOW, key_of, windows, get_bounds,
    )
    assert totals["a"]["window_start"] == bounds["a"][0]
    assert totals["a"]["window_end"] == bounds["a"][1]
    assert totals["b"]["window_start"] == bounds["b"][0]
    assert totals["b"]["window_end"] == bounds["b"][1]
    assert excluded == []


def test_row_exactly_at_window_start_is_included():
    totals, excluded = fold(
        [row(ts="2026-01-15T00:00:00Z")],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals["k"]["calls"] == 1
    assert excluded == []


def test_row_exactly_at_window_end_is_excluded_as_outside_window():
    totals, excluded = fold(
        [row(ts="2026-01-16T00:00:00Z")],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "outside-window"


def test_row_before_window_is_excluded_as_outside_window():
    totals, excluded = fold(
        [row(ts="2026-01-14T23:59:59Z")],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "outside-window"


def test_offset_timestamp_is_converted_before_comparing():
    totals, excluded = fold(
        [row(ts="2026-01-15T13:00:00+03:00")],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals["k"]["calls"] == 1
    assert excluded == []


def test_naive_timestamp_is_excluded_with_its_own_slug():
    totals, excluded = fold(
        [row(ts="2026-01-15T10:00:00")],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "naive-timestamp"


def test_unparseable_timestamp_is_excluded_as_bad_timestamp():
    totals, excluded = fold(
        [row(ts="not-a-timestamp")],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "bad-timestamp"


def test_missing_timestamp_is_excluded_as_bad_timestamp():
    item = row()
    del item["ts"]
    totals, excluded = fold(
        [item], NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "bad-timestamp"


def test_no_key_row_is_excluded_and_not_counted_anywhere():
    totals, excluded = fold(
        [row(key=None)],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded == [{"index": 0, "reason": "no-key", "key": None}]


def test_no_window_row_is_excluded_with_its_key_recorded():
    def no_window(key):
        return None

    totals, excluded = fold(
        [row(key="missing")],
        NOW, key_of, no_window, bounds_of,
    )
    assert totals == {}
    assert excluded == [{"index": 0, "reason": "no-window", "key": "missing"}]


def test_negative_count_is_excluded_as_bad_counts_not_treated_as_zero():
    totals, excluded = fold(
        [row(requests=-1)],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "bad-counts"


def test_boolean_count_is_excluded_as_bad_counts():
    totals, excluded = fold(
        [row(requests=True)],
        NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "bad-counts"


def test_missing_count_field_is_excluded_as_bad_counts():
    item = row()
    del item["input_tokens"]
    totals, excluded = fold(
        [item], NOW, key_of, window_of, bounds_of,
    )
    assert totals == {}
    assert excluded[0]["reason"] == "bad-counts"


def test_callback_error_is_recorded_and_fold_continues():
    rows = [row(key="a"), row(key="boom"), row(key="c")]

    def raising_key(item):
        if item["key"] == "boom":
            raise RuntimeError("broken key")
        return item["key"]

    totals, excluded = fold(
        rows, NOW, raising_key, window_of, bounds_of,
    )
    assert totals["a"]["calls"] == 1
    assert totals["c"]["calls"] == 1
    assert "boom" not in totals
    assert excluded == [{
        "index": 1,
        "reason": "callback-error",
        "key": None,
        "detail": "broken key",
    }]


def test_bounds_of_is_called_once_per_distinct_spec():
    calls = []

    def get_bounds(spec, now):
        calls.append(spec)
        return START, END

    rows = [row(key="a"), row(key="b"), row(key="a")]

    def same_spec(key):
        return {"period": "daily"}

    totals, excluded = fold(
        rows, NOW, key_of, same_spec, get_bounds,
    )
    assert len(calls) == 1
    assert totals["a"]["calls"] == 2
    assert totals["b"]["calls"] == 1
    assert excluded == []


def test_naive_now_raises():
    naive = datetime(2026, 1, 15, 12, 0)
    with pytest.raises(ValueError):
        fold([], naive, key_of, window_of, bounds_of)


def test_empty_rows_returns_empty_totals_and_empty_excluded():
    assert fold([], NOW, key_of, window_of, bounds_of) == ({}, [])


def test_result_is_order_independent():
    rows = [
        row(key="a", requests=2, input_tokens=3, output_tokens=4),
        row(key="b", requests=5, input_tokens=6, output_tokens=7),
        row(key="a", requests=8, input_tokens=9, output_tokens=10),
    ]
    first = fold(rows, NOW, key_of, window_of, bounds_of)
    second = fold(list(reversed(rows)), NOW, key_of, window_of, bounds_of)
    assert first == second


def test_excluded_reasons_are_distinguishable():
    bad_counts = row(key="bad-counts", requests=-1)
    naive = row(key="naive", ts="2026-01-15T10:00:00")
    bad_timestamp = row(key="bad-ts", ts="nope")
    outside = row(key="outside", ts="2026-01-16T00:00:00Z")
    no_key = row(key=None)
    no_window = row(key="no-window")

    def selective_window(key):
        if key == "no-window":
            return None
        return {"window": key}

    totals, excluded = fold(
        [no_key, no_window, bad_timestamp, naive, bad_counts, outside],
        NOW, key_of, selective_window, bounds_of,
    )
    assert totals == {}
    assert {item["reason"] for item in excluded} == {
        "no-key",
        "no-window",
        "bad-timestamp",
        "naive-timestamp",
        "bad-counts",
        "outside-window",
    }


def test_window_callback_error_is_recorded_and_fold_continues():
    def raising_window(key):
        if key == "boom":
            raise RuntimeError("window failure")
        return {"window": "daily"}

    totals, excluded = fold(
        [row(key="a"), row(key="boom"), row(key="c")],
        NOW, key_of, raising_window, bounds_of,
    )
    assert set(totals) == {"a", "c"}
    assert excluded[0]["index"] == 1
    assert excluded[0]["reason"] == "callback-error"
    assert excluded[0]["key"] == "boom"
    assert excluded[0]["detail"] == "window failure"


def test_bounds_callback_error_is_recorded_and_fold_continues():
    def raising_bounds(spec, now):
        if spec["window"] == "boom":
            raise RuntimeError("bounds failure")
        return START, END

    def windows(key):
        return {"window": key}

    totals, excluded = fold(
        [row(key="a"), row(key="boom"), row(key="c")],
        NOW, key_of, windows, raising_bounds,
    )
    assert set(totals) == {"a", "c"}
    assert excluded[0]["index"] == 1
    assert excluded[0]["reason"] == "callback-error"
    assert excluded[0]["key"] == "boom"
    assert excluded[0]["detail"] == "bounds failure"
