# tests/test_quota_scope.py
import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "scope.py"

)
_spec = _ilu.spec_from_file_location('scope', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
counting_key = _mod.counting_key
group_usage = _mod.group_usage
limit_for = _mod.limit_for


# ---------- counting_key ----------


def test_account_scope_collapses_two_models_to_one_key():
    k1 = counting_key("groq", "acct1", "llama-70b", "account")
    k2 = counting_key("groq", "acct1", "mixtral-8x7b", "account")
    assert k1 == k2 == "groq/acct1"


def test_model_scope_separates_two_models():
    k1 = counting_key("groq", "acct1", "llama-70b", "model")
    k2 = counting_key("groq", "acct1", "mixtral-8x7b", "model")
    assert k1 != k2
    assert k1 == "groq/acct1/llama-70b"
    assert k2 == "groq/acct1/mixtral-8x7b"


def test_unknown_scope_key_carries_question_mark():
    k = counting_key("groq", "acct1", "llama-70b", "unknown")
    assert k.endswith("?")
    assert k == "groq/acct1/llama-70b?"


def test_unknown_scope_key_differs_from_model_scope_key():
    k_model = counting_key("groq", "acct1", "llama-70b", "model")
    k_unknown = counting_key("groq", "acct1", "llama-70b", "unknown")
    assert k_model != k_unknown


def test_account_scope_ignores_missing_model():
    k1 = counting_key("groq", "acct1", "", "account")
    k2 = counting_key("groq", "acct1", None, "account")
    assert k1 == k2 == "groq/acct1"


def test_model_scope_requires_model():
    with pytest.raises(ValueError):
        counting_key("groq", "acct1", "", "model")
    with pytest.raises(ValueError):
        counting_key("groq", "acct1", None, "model")


def test_unknown_scope_requires_model():
    with pytest.raises(ValueError):
        counting_key("groq", "acct1", "", "unknown")


def test_empty_provider_or_account_raises():
    with pytest.raises(ValueError):
        counting_key("", "acct1", "m", "account")
    with pytest.raises(ValueError):
        counting_key("groq", "", "m", "account")
    with pytest.raises(ValueError):
        counting_key(None, "acct1", "m", "account")


def test_bad_scope_raises_and_names_it():
    with pytest.raises(ValueError) as exc:
        counting_key("groq", "acct1", "m", "per-key")
    assert "per-key" in str(exc.value)


def test_keys_are_lowercased():
    k = counting_key("GroQ", "AcCt1", "LLaMa-70B", "model")
    assert k == "groq/acct1/llama-70b"


def test_slash_inside_model_name_is_escaped():
    k = counting_key("groq", "acct1", "groq/compound", "model")
    assert k == "groq/acct1/groq_compound"
    assert k.count("/") == 2


def test_slash_inside_provider_or_account_is_escaped():
    k = counting_key("gr/oq", "ac/ct1", "m", "account")
    assert k == "gr_oq/ac_ct1"


# ---------- group_usage ----------


def _scope_of_factory(mapping):
    def scope_of(provider, account):
        return mapping[(provider, account)]

    return scope_of


def test_group_usage_sums_across_models_under_account_scope():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": 600,
            "input_tokens": 100,
            "output_tokens": 50,
        },
        {
            "provider": "groq",
            "account": "acct1",
            "model": "mixtral-8x7b",
            "requests": 600,
            "input_tokens": 100,
            "output_tokens": 50,
        },
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "account"})
    totals, rejected = group_usage(rows, scope_of)
    assert rejected == []
    assert len(totals) == 1
    (bucket,) = totals.values()
    assert bucket["requests"] == 1200
    assert bucket["calls"] == 2


def test_group_usage_keeps_models_apart_under_model_scope():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": 600,
            "input_tokens": 100,
            "output_tokens": 50,
        },
        {
            "provider": "groq",
            "account": "acct1",
            "model": "mixtral-8x7b",
            "requests": 600,
            "input_tokens": 100,
            "output_tokens": 50,
        },
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "model"})
    totals, rejected = group_usage(rows, scope_of)
    assert rejected == []
    assert len(totals) == 2
    for bucket in totals.values():
        assert bucket["requests"] == 600
        assert bucket["calls"] == 1


def test_group_usage_is_order_independent():
    row_a = {
        "provider": "groq",
        "account": "acct1",
        "model": "llama-70b",
        "requests": 100,
        "input_tokens": 10,
        "output_tokens": 5,
    }
    row_b = {
        "provider": "groq",
        "account": "acct1",
        "model": "mixtral-8x7b",
        "requests": 200,
        "input_tokens": 20,
        "output_tokens": 10,
    }
    scope_of = _scope_of_factory({("groq", "acct1"): "account"})
    totals1, rejected1 = group_usage([row_a, row_b], scope_of)
    totals2, rejected2 = group_usage([row_b, row_a], scope_of)
    assert totals1 == totals2
    assert rejected1 == rejected2 == []


def test_group_usage_rejects_row_with_missing_field_and_reports_index():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": 100,
            "input_tokens": 10,
            # output_tokens missing
        }
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "account"})
    totals, rejected = group_usage(rows, scope_of)
    assert totals == {}
    assert len(rejected) == 1
    idx, reason = rejected[0]
    assert idx == 0
    assert "output_tokens" in reason


def test_group_usage_rejects_non_integer_count_rather_than_zeroing_it():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": "600",  # string, not int
            "input_tokens": 10,
            "output_tokens": 5,
        }
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "account"})
    totals, rejected = group_usage(rows, scope_of)
    assert totals == {}
    assert len(rejected) == 1
    idx, reason = rejected[0]
    assert idx == 0
    assert "requests" in reason


def test_group_usage_rejects_bool_count_field():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": True,
            "input_tokens": 10,
            "output_tokens": 5,
        }
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "account"})
    totals, rejected = group_usage(rows, scope_of)
    assert totals == {}
    assert len(rejected) == 1


def test_group_usage_rejects_row_that_fails_scope_validation():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "",  # empty model, but scope requires one
            "requests": 100,
            "input_tokens": 10,
            "output_tokens": 5,
        }
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "model"})
    totals, rejected = group_usage(rows, scope_of)
    assert totals == {}
    assert len(rejected) == 1
    idx, reason = rejected[0]
    assert idx == 0
    assert "invalid scope/key" in reason


def test_group_usage_mixed_valid_and_invalid_rows_preserves_index():
    rows = [
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": 100,
            "input_tokens": 10,
            "output_tokens": 5,
        },
        {
            "provider": "groq",
            "account": "acct1",
            "model": "llama-70b",
            "requests": "bad",
            "input_tokens": 10,
            "output_tokens": 5,
        },
    ]
    scope_of = _scope_of_factory({("groq", "acct1"): "account"})
    totals, rejected = group_usage(rows, scope_of)
    assert len(totals) == 1
    assert len(rejected) == 1
    assert rejected[0][0] == 1


# ---------- limit_for ----------


def test_limit_for_returns_declared_limit_and_source():
    entries = {"groq/acct1": {"limit": 1000, "source": "provider-docs"}}
    limit, source = limit_for("groq/acct1", entries)
    assert limit == 1000
    assert source == "provider-docs"


def test_limit_for_absent_key_is_none_with_no_limit_declared():
    entries = {"groq/acct1": {"limit": 1000, "source": "provider-docs"}}
    limit, source = limit_for("groq/acct2", entries)
    assert limit is None
    assert source == "no-limit-declared"


def test_limit_for_negative_or_null_limit_is_none_with_limit_unparseable():
    entries = {
        "groq/acct1": {"limit": -5, "source": "x"},
        "groq/acct2": {"limit": None, "source": "x"},
        "groq/acct3": {"source": "x"},  # missing limit entirely
        "groq/acct4": {"limit": "1000", "source": "x"},  # not an int
    }
    for key in entries:
        limit, source = limit_for(key, entries)
        assert limit is None
        assert source == "limit-unparseable"


def test_limit_for_never_returns_zero_as_a_stand_in_for_unknown():
    entries = {}
    limit, source = limit_for("groq/acct1", entries)
    assert limit is None
    assert limit != 0
    assert source == "no-limit-declared"


def test_limit_for_bool_limit_is_unparseable():
    entries = {"groq/acct1": {"limit": True, "source": "x"}}
    limit, source = limit_for("groq/acct1", entries)
    assert limit is None
    assert source == "limit-unparseable"


def test_limit_for_zero_is_a_valid_declared_limit():
    entries = {"groq/acct1": {"limit": 0, "source": "provider-docs"}}
    limit, source = limit_for("groq/acct1", entries)
    assert limit == 0
    assert source == "provider-docs"
