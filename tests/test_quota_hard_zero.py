# tests/test_quota_hard_zero.py
import pytest
import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "hard_zero.py"

)
_spec = _ilu.spec_from_file_location('hard_zero', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
check_hard_zero = _mod.check_hard_zero
unreviewed_keys = _mod.unreviewed_keys


@pytest.fixture
def valid_config():
    return {
        "model_list": [
            {
                "model_name": "cheap-fast",
                "litellm_params": {
                    "model": "groq/llama-3.1-8b",
                    "api_key": "os.environ/GROQ_KEY",
                },
            },
            {
                "model_name": "cheap-long",
                "litellm_params": {"model": "gemini/gemini-2.0-flash"},
            },
        ],
        "router_settings": {
            "fallbacks": [{"cheap-fast": ["cheap-long"]}],
            "context_window_fallbacks": [{"cheap-long": ["cheap-fast"]}],
            "default_fallbacks": ["cheap-long"],
            "allowed_fails": 3,
        },
        "general_settings": {"master_key": "os.environ/PROXY_KEY"},
    }


@pytest.fixture
def free_providers():
    return {"groq", "gemini"}


def test_all_free_routes_pass(valid_config, free_providers):
    assert check_hard_zero(valid_config, free_providers) == []


def test_paid_provider_route_is_a_violation(valid_config, free_providers):
    valid_config["model_list"].append(
        {
            "model_name": "expensive",
            "litellm_params": {"model": "openai/gpt-4o"},
        }
    )
    violations = check_hard_zero(valid_config, free_providers)
    assert any("expensive" in v and "openai" in v for v in violations)


def test_model_without_provider_prefix_is_a_violation(valid_config, free_providers):
    valid_config["model_list"].append(
        {
            "model_name": "noprefix",
            "litellm_params": {"model": "gpt-4o"},
        }
    )
    violations = check_hard_zero(valid_config, free_providers)
    assert any(
        "provider could not be determined" in v and "gpt-4o" in v for v in violations
    )


def test_fallback_to_undefined_model_name_is_a_violation(valid_config, free_providers):
    valid_config["router_settings"]["fallbacks"] = [{"cheap-fast": ["ghost-model"]}]
    violations = check_hard_zero(valid_config, free_providers)
    assert any(
        "fallbacks targets undefined model_name 'ghost-model'" in v
        for v in violations
    )


def test_context_window_fallback_to_undefined_model_name_is_a_violation(
    valid_config, free_providers
):
    valid_config["router_settings"]["context_window_fallbacks"] = [
        {"cheap-fast": ["unknown-model"]}
    ]
    violations = check_hard_zero(valid_config, free_providers)
    assert any(
        "context_window_fallbacks targets undefined model_name 'unknown-model'" in v
        for v in violations
    )


def test_default_fallback_to_undefined_model_name_is_a_violation(
    valid_config, free_providers
):
    valid_config["router_settings"]["default_fallbacks"] = ["missing-model"]
    violations = check_hard_zero(valid_config, free_providers)
    assert any(
        "default_fallbacks targets undefined model_name 'missing-model'" in v
        for v in violations
    )


def test_wildcard_star_in_fallbacks_is_a_violation(valid_config, free_providers):
    valid_config["router_settings"]["fallbacks"] = [{"cheap-fast": ["*"]}]
    violations = check_hard_zero(valid_config, free_providers)
    assert any("wildcard '*'" in v for v in violations)


def test_wildcard_all_case_insensitive_is_a_violation(valid_config, free_providers):
    valid_config["router_settings"]["default_fallbacks"] = ["ALL"]
    violations = check_hard_zero(valid_config, free_providers)
    assert any("wildcard 'ALL'" in v for v in violations)


def test_empty_model_list_is_a_violation_not_a_pass(valid_config, free_providers):
    valid_config["model_list"] = []
    violations = check_hard_zero(valid_config, free_providers)
    assert len(violations) > 0


def test_missing_model_list_is_a_violation(valid_config, free_providers):
    del valid_config["model_list"]
    violations = check_hard_zero(valid_config, free_providers)
    assert len(violations) > 0


def test_duplicate_model_name_is_a_violation(valid_config, free_providers):
    valid_config["model_list"].append(
        {
            "model_name": "cheap-fast",
            "litellm_params": {"model": "groq/llama-3.1-8b"},
        }
    )
    violations = check_hard_zero(valid_config, free_providers)
    assert any("duplicate model_name 'cheap-fast'" in v for v in violations)


def test_empty_free_provider_list_is_a_violation(valid_config):
    violations = check_hard_zero(valid_config, [])
    assert len(violations) > 0
    assert any("free provider list is empty" in v for v in violations)


def test_env_var_api_key_is_not_a_violation(valid_config, free_providers):
    valid_config["model_list"][0]["litellm_params"]["api_key"] = "os.environ/ANY_KEY"
    assert check_hard_zero(valid_config, free_providers) == []


def test_missing_router_settings_is_not_a_violation_by_itself(
    valid_config, free_providers
):
    del valid_config["router_settings"]
    assert check_hard_zero(valid_config, free_providers) == []


def test_all_violations_are_reported_together(valid_config, free_providers):
    valid_config["model_list"].append(
        {"model_name": "paid", "litellm_params": {"model": "openai/gpt-4o"}}
    )
    valid_config["model_list"].append(
        {"model_name": "noprefix", "litellm_params": {"model": "gpt-4o"}}
    )
    valid_config["router_settings"]["default_fallbacks"] = ["missing"]

    violations = check_hard_zero(valid_config, free_providers)
    assert len(violations) == 3


def test_unreviewed_keys_lists_unknown_paths(valid_config):
    valid_config["router_settings"]["timeout"] = 30
    valid_config["extra_section"] = {"foo": "bar"}
    unreviewed = unreviewed_keys(valid_config)
    assert "router_settings.timeout" in unreviewed
    assert "extra_section" in unreviewed
    assert "extra_section.foo" in unreviewed


def test_unreviewed_keys_is_empty_for_a_fully_understood_config(valid_config):
    assert unreviewed_keys(valid_config) == []


def test_unreviewed_keys_does_not_appear_in_violations(valid_config, free_providers):
    valid_config["router_settings"]["timeout"] = 30
    violations = check_hard_zero(valid_config, free_providers)
    assert violations == []
