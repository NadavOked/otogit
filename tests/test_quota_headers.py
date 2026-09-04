# tests/test_quota_headers.py
from datetime import datetime, timezone
import pytest
import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "quota" / "headers.py"

)
_spec = _ilu.spec_from_file_location('headers', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_rate_limit_headers = _mod.parse_rate_limit_headers

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_anthropic_full_headers_known():
    headers = {
        "x-ratelimit-limit-requests": "100",
        "x-ratelimit-remaining-requests": "90",
        "x-ratelimit-limit-tokens": "100000",
        "x-ratelimit-remaining-tokens": "95000",
        "x-ratelimit-reset-requests": "10s",
        "x-ratelimit-reset-tokens": "20s",
    }
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.provider == "anthropic"
    assert res.state == "known"
    assert res.limit_requests == 100
    assert res.remaining_requests == 90
    assert res.limit_tokens == 100000
    assert res.remaining_tokens == 95000
    assert res.reset_at == datetime(2026, 9, 4, 12, 0, 20, tzinfo=timezone.utc)
    assert res.reason == ""


def test_xai_only_remaining_requests_known():
    headers = {
        "x-ratelimit-remaining-requests": "50",
    }
    res = parse_rate_limit_headers("xai", headers, NOW)
    assert res.provider == "xai"
    assert res.state == "known"
    assert res.remaining_requests == 50
    assert res.limit_requests is None
    assert res.limit_tokens is None
    assert res.remaining_tokens is None
    assert res.reset_at is None
    assert res.reason == ""


def test_groq_header_case_is_ignored():
    headers = {
        "X-RateLimit-Limit-Requests": "60",
        "x-RATELIMIT-REMAINING-REQUESTS": "45",
    }
    res = parse_rate_limit_headers("groq", headers, NOW)
    assert res.provider == "groq"
    assert res.state == "known"
    assert res.limit_requests == 60
    assert res.remaining_requests == 45


def test_anthropic_no_headers_is_unknown_not_estimated():
    res = parse_rate_limit_headers("anthropic", {}, NOW)
    assert res.state == "unknown"
    assert res.state != "estimated"
    assert res.state != "ok"
    assert res.reason == "no-headers"


def test_anthropic_garbage_remaining_is_unknown():
    headers = {"x-ratelimit-remaining-requests": "abc"}
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.state == "unknown"
    assert res.reason == "unparseable-remaining"


def test_negative_remaining_is_unknown():
    headers = {"x-ratelimit-remaining-requests": "-1"}
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.state == "unknown"
    assert res.reason == "unparseable-remaining"


def test_reset_duration_compound():
    headers = {
        "x-ratelimit-remaining-requests": "10",
        "x-ratelimit-reset-requests": "1m30s",
    }
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.reset_at == datetime(2026, 9, 4, 12, 1, 30, tzinfo=timezone.utc)


def test_reset_duration_milliseconds_round_up():
    headers = {
        "x-ratelimit-remaining-requests": "10",
        "x-ratelimit-reset-requests": "500ms",
    }
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.reset_at == datetime(2026, 9, 4, 12, 0, 1, tzinfo=timezone.utc)


def test_reset_absolute_z_suffix():
    headers = {
        "x-ratelimit-remaining-requests": "10",
        "x-ratelimit-reset-requests": "2026-09-04T12:00:00Z",
    }
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.reset_at == datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_reset_takes_the_later_of_two():
    headers = {
        "x-ratelimit-remaining-requests": "10",
        "x-ratelimit-reset-requests": "10s",
        "x-ratelimit-reset-tokens": "60s",
    }
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.reset_at == datetime(2026, 9, 4, 12, 1, 0, tzinfo=timezone.utc)


def test_unparseable_reset_keeps_known_state():
    headers = {
        "x-ratelimit-remaining-requests": "10",
        "x-ratelimit-reset-requests": "soon",
    }
    res = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res.state == "known"
    assert res.reset_at is None


def test_google_is_always_estimated():
    headers = {"x-ratelimit-remaining-requests": "10"}
    res = parse_rate_limit_headers("google", headers, NOW)
    assert res.provider == "google"
    assert res.state == "estimated"
    assert res.reason == "provider-sends-no-headers"
    assert res.remaining_requests is None


def test_openai_is_estimated_but_keeps_numbers():
    headers = {
        "x-ratelimit-remaining-requests": "10",
        "x-ratelimit-limit-requests": "100",
    }
    res = parse_rate_limit_headers("openai", headers, NOW)
    assert res.provider == "openai"
    assert res.state == "estimated"
    assert res.remaining_requests == 10
    assert res.limit_requests == 100
    assert res.reason == "provider-numbers-untrusted"


def test_unrecognised_provider_is_unknown():
    res1 = parse_rate_limit_headers("cerebras", {}, NOW)
    assert res1.state == "unknown"
    assert res1.reason == "unknown-provider"

    res2 = parse_rate_limit_headers(None, {}, NOW)
    assert res2.state == "unknown"
    assert res2.reason == "unknown-provider"


def test_reading_is_immutable_or_at_least_not_shared():
    headers = {"x-ratelimit-remaining-requests": "10"}
    res1 = parse_rate_limit_headers("anthropic", headers, NOW)
    res2 = parse_rate_limit_headers("anthropic", headers, NOW)
    assert res1 is not res2
    with pytest.raises(AttributeError):
        res1.state = "estimated"
