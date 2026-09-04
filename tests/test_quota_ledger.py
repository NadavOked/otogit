# tests/test_quota_ledger.py
import json
from datetime import datetime, timedelta, timezone

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "ledger.py"

)
_spec = _ilu.spec_from_file_location('ledger', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
append = _mod.append
read_all = _mod.read_all
validate = _mod.validate


NOW = datetime(
    2026, 9, 4, 13, 20, 5, 123456, tzinfo=timezone.utc
)


def good_record(**changes):
    record = {
        "ts": "2026-09-04T13:20:05.123456+00:00",
        "provider": "openai",
        "account": "primary",
        "model": "example-model",
        "requests": 1,
        "input_tokens": 100,
        "output_tokens": 25,
        "state": "known",
    }
    record.update(changes)
    return record


def test_append_then_read_roundtrip(tmp_path):
    path = tmp_path / "ledger.jsonl"
    expected = good_record()

    written = append(path, expected, NOW)
    records, problems = read_all(path)

    assert written == expected
    assert records == [expected]
    assert problems == []


def test_append_sets_ts_when_absent(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record = good_record()
    del record["ts"]

    written = append(path, record, NOW)

    assert written["ts"] == "2026-09-04T13:20:05.123456+00:00"


def test_append_preserves_existing_ts(tmp_path):
    path = tmp_path / "ledger.jsonl"
    existing = "2025-01-02T03:04:05+00:00"
    record = good_record(ts=existing)

    written = append(path, record, NOW)

    assert written["ts"] == existing


def test_append_rejects_missing_required_field(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record = good_record()
    del record["model"]

    with pytest.raises(ValueError) as exc_info:
        append(path, record, NOW)

    assert "model" in str(exc_info.value)
    assert not path.exists()


def test_append_rejects_negative_counts(tmp_path):
    path = tmp_path / "ledger.jsonl"

    with pytest.raises(ValueError) as exc_info:
        append(path, good_record(input_tokens=-1), NOW)

    assert "input_tokens" in str(exc_info.value)
    assert not path.exists()


def test_append_rejects_bad_state_value(tmp_path):
    path = tmp_path / "ledger.jsonl"

    with pytest.raises(ValueError) as exc_info:
        append(path, good_record(state="fine"), NOW)

    assert "state" in str(exc_info.value)


def test_append_rejects_unexpected_field(tmp_path):
    path = tmp_path / "ledger.jsonl"

    with pytest.raises(ValueError) as exc_info:
        append(path, good_record(cost_usd=0.01), NOW)

    assert "unexpected field: cost_usd" in str(exc_info.value)


def test_append_rejects_boolean_as_count(tmp_path):
    path = tmp_path / "ledger.jsonl"

    with pytest.raises(ValueError) as exc_info:
        append(path, good_record(requests=True), NOW)

    assert "requests" in str(exc_info.value)


def test_append_does_not_mutate_caller_dict(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record = good_record()
    del record["ts"]
    original = dict(record)

    written = append(path, record, NOW)

    assert record == original
    assert "ts" not in record
    assert "ts" in written
    assert written is not record


def test_append_does_not_truncate_existing_file(tmp_path):
    path = tmp_path / "ledger.jsonl"
    first = good_record(model="first")
    second = good_record(model="second")

    append(path, first, NOW)
    append(path, second, NOW)

    records, problems = read_all(path)
    assert records == [first, second]
    assert problems == []


def test_append_creates_missing_parent_directory(tmp_path):
    path = tmp_path / "a" / "b" / "ledger.jsonl"

    append(path, good_record(), NOW)

    assert path.is_file()


def test_read_all_missing_file_is_empty_not_error(tmp_path):
    assert read_all(tmp_path / "missing.jsonl") == ([], [])


def test_read_all_reports_corrupt_line_with_number(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps(good_record()) + "\n"
        '{"broken":\n',
        encoding="utf-8",
    )

    records, problems = read_all(path)

    assert records == [good_record()]
    assert len(problems) == 1
    assert problems[0].startswith("line 2:")


def test_read_all_survives_truncated_final_line(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps(good_record()) + "\n"
        '{"ts":"2026-09-04T13:20',
        encoding="utf-8",
    )

    records, problems = read_all(path)

    assert records == [good_record()]
    assert len(problems) == 1
    assert problems[0].startswith("line 2:")


def test_read_all_skips_blank_lines_without_reporting_them(tmp_path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "\n   \n" + json.dumps(good_record()) + "\n\t\n",
        encoding="utf-8",
    )

    records, problems = read_all(path)

    assert records == [good_record()]
    assert problems == []


def test_read_all_reports_valid_json_that_fails_validation(tmp_path):
    path = tmp_path / "ledger.jsonl"
    bad = good_record(requests=-1)
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")

    records, problems = read_all(path)

    assert records == []
    assert len(problems) == 1
    assert problems[0].startswith("line 1:")
    assert "requests" in problems[0]


def test_unicode_survives_roundtrip(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record = good_record(note="שלום עולם — בדיקת מכסה")

    append(path, record, NOW)
    records, problems = read_all(path)

    assert problems == []
    assert records[0]["note"] == "שלום עולם — בדיקת מכסה"


def test_validate_returns_empty_list_for_good_record():
    assert validate(good_record()) == []


def test_validate_checks_all_optional_fields():
    record = good_record(
        remaining_requests=10,
        remaining_tokens=None,
        reset_at="2026-09-05T00:00:00+00:00",
        task="coding",
        note="ok",
    )
    assert validate(record) == []


def test_validate_rejects_uppercase_provider():
    problems = validate(good_record(provider="OpenAI"))
    assert any("provider" in problem for problem in problems)


def test_validate_rejects_boolean_optional_count():
    problems = validate(good_record(remaining_requests=True))
    assert any("remaining_requests" in problem for problem in problems)


def test_validate_rejects_naive_timestamp():
    problems = validate(good_record(ts="2026-09-04T13:20:05"))
    assert any("ts" in problem for problem in problems)


def test_append_converts_non_utc_now_to_utc(tmp_path):
    path = tmp_path / "ledger.jsonl"
    record = good_record()
    del record["ts"]
    local_now = datetime(
        2026, 9, 4, 16, 20, 5, 123456,
        tzinfo=timezone(timedelta(hours=3)),
    )

    written = append(path, record, local_now)

    assert written["ts"] == "2026-09-04T13:20:05.123456+00:00"


def test_append_rejects_naive_now(tmp_path):
    path = tmp_path / "ledger.jsonl"
    naive_now = datetime(2026, 9, 4, 13, 20, 5)

    with pytest.raises(ValueError, match="timezone-aware"):
        append(path, good_record(), naive_now)
