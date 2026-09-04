# tests/test_quota_manifest.py
import json

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "manifest.py"

)
_spec = _ilu.spec_from_file_location('manifest', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
load_and_validate = _mod.load_and_validate
validate_manifest = _mod.validate_manifest


def valid_provider():
    return {
        "paid": False,
        "billing_enabled": False,
        "scope": "account",
        "window": {"kind": "daily", "tz": "UTC"},
        "reports_remaining_quota": True,
        "limits": {"requests": 1000, "tokens": None},
        # The spec requires `source` whenever any limit is a number, and
        # `measured_at` whenever `source` is present. Both are in the spec's
        # own example provider; a fixture without them is not a valid document.
        "source": "owner-reported",
        "measured_at": "2026-09-02",
    }


def valid_doc():
    return {
        "version": 1,
        "updated": "2026-09-04",
        "providers": {"example": valid_provider()},
    }


def test_minimal_valid_document_has_no_problems():
    assert validate_manifest(valid_doc()) == []


def test_wrong_version_is_reported():
    doc = valid_doc()
    doc["version"] = 2
    assert any("version" in p and "integer 1" in p for p in validate_manifest(doc))


def test_unknown_top_level_key_is_reported_by_name():
    doc = valid_doc()
    doc["unexpected"] = True
    assert any("unexpected: unknown top-level key" == p for p in validate_manifest(doc))


def test_empty_providers_is_reported():
    doc = valid_doc()
    doc["providers"] = {}
    assert any(
        "providers: must be a non-empty object" == p for p in validate_manifest(doc)
    )


def test_free_provider_with_billing_enabled_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["billing_enabled"] = True
    assert any("billing_enabled" in p for p in validate_manifest(doc))


def test_missing_scope_is_reported_not_defaulted():
    doc = valid_doc()
    del doc["providers"]["example"]["scope"]
    original = json.loads(json.dumps(doc))
    problems = validate_manifest(doc)
    assert doc == original
    assert "scope" not in doc["providers"]["example"]
    assert any("providers.example.scope: missing" == p for p in problems)


def test_bad_scope_value_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["scope"] = "global"
    assert any("providers.example.scope" in p for p in validate_manifest(doc))


def test_rolling_window_without_hours_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["window"] = {"kind": "rolling"}
    assert any("window.hours: missing" in p for p in validate_manifest(doc))


def test_rolling_window_with_zero_hours_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["window"] = {"kind": "rolling", "hours": 0}
    assert any("window.hours" in p and "positive" in p for p in validate_manifest(doc))


def test_daily_window_without_tz_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["window"] = {"kind": "daily"}
    assert any("window.tz: missing" in p for p in validate_manifest(doc))


def test_monthly_anchor_day_out_of_range_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["window"] = {
        "kind": "monthly", "tz": "UTC", "anchor_day": 32
    }
    assert any("anchor_day" in p and "1..31" in p for p in validate_manifest(doc))


def test_unknown_window_kind_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["window"] = {"kind": "weekly"}
    assert any("window.kind" in p for p in validate_manifest(doc))


def test_numeric_limit_without_source_is_reported():
    doc = valid_doc()
    provider = doc["providers"]["example"]
    provider["limits"] = {"requests": 100}
    del provider["source"]
    del provider["measured_at"]
    assert any("source: missing" in p for p in validate_manifest(doc))


def test_source_without_measured_at_is_reported():
    doc = valid_doc()
    provider = doc["providers"]["example"]
    provider["source"] = "measured"
    provider["limits"] = {"requests": 100}
    del provider["measured_at"]
    assert any("measured_at: missing" in p for p in validate_manifest(doc))


def test_null_limit_is_allowed():
    doc = valid_doc()
    doc["providers"]["example"]["limits"] = {"requests": None}
    assert validate_manifest(doc) == []


def test_negative_limit_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["limits"] = {"requests": -1}
    assert any("requests" in p and "positive" in p for p in validate_manifest(doc))


def test_account_scope_with_per_model_limits_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["models"] = {
        "example-fast": {
            "limits": {"requests": 500},
            "source": "measured",
            "measured_at": "2026-09-02",
        }
    }
    problems = validate_manifest(doc)
    assert any(
        "provider 'example': scope is account but model 'example-fast' "
        "declares its own limits"
        == p
        for p in problems
    )


def test_account_scope_with_models_but_no_model_limits_is_fine():
    doc = valid_doc()
    doc["providers"]["example"]["models"] = {
        "example-fast": {"source": "owner-reported", "measured_at": "2026-09-02"}
    }
    assert validate_manifest(doc) == []


def test_model_scope_with_top_level_numeric_limits_is_reported():
    doc = valid_doc()
    provider = doc["providers"]["example"]
    provider["scope"] = "model"
    provider["limits"] = {"requests": 100}
    provider["source"] = "measured"
    provider["measured_at"] = "2026-09-04"
    assert any(
        "providers.example.limits" in p and "scope is model" in p
        for p in validate_manifest(doc)
    )


def test_all_problems_are_reported_together():
    doc = valid_doc()
    doc["version"] = 2
    doc["unexpected"] = True
    doc["providers"]["example"]["billing_enabled"] = True
    doc["providers"]["example"]["scope"] = "bad"
    problems = validate_manifest(doc)
    assert len(problems) == 4
    assert any("version" in p for p in problems)
    assert any("unexpected" in p for p in problems)
    assert any("billing_enabled" in p for p in problems)
    assert any("scope" in p for p in problems)


def test_load_and_validate_missing_file_returns_none_and_problem(tmp_path):
    path = tmp_path / "missing.json"
    doc, problems = load_and_validate(path)
    assert doc is None
    assert problems == [f"{path}: no such file"]


def test_load_and_validate_malformed_json_returns_none_and_problem(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"version":', encoding="utf-8")
    doc, problems = load_and_validate(path)
    assert doc is None
    assert len(problems) == 1
    assert problems[0].startswith(f"{path}: not valid JSON:")


def test_load_and_validate_good_file_returns_doc_and_empty_problems(tmp_path):
    path = tmp_path / "manifest.json"
    expected = valid_doc()
    path.write_text(json.dumps(expected), encoding="utf-8")
    doc, problems = load_and_validate(path)
    assert doc == expected
    assert problems == []


def test_model_source_without_measured_at_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["models"] = {
        "m": {
            "limits": {"requests": 5},
            "source": "measured",
        }
    }
    problems = validate_manifest(doc)
    assert any("providers.example.models.m.measured_at: missing" in p for p in problems)


def test_provider_with_unknown_limit_key_is_reported():
    doc = valid_doc()
    doc["providers"]["example"]["limits"]["calls"] = 10
    problems = validate_manifest(doc)
    assert any("providers.example.limits.calls: unknown key" == p for p in problems)


def test_non_dict_manifest_raises_type_error():
    with pytest.raises(TypeError):
        validate_manifest([])


def test_invalid_iso_dates_are_reported():
    doc = valid_doc()
    doc["updated"] = "2026-99-99"
    provider = doc["providers"]["example"]
    provider["limits"] = {"requests": 10}
    provider["source"] = "measured"
    provider["measured_at"] = "not-a-date"
    problems = validate_manifest(doc)
    assert any("updated" in p for p in problems)
    assert any("measured_at" in p for p in problems)
