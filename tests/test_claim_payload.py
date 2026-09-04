# tests/test_claim_payload.py
from datetime import datetime, timezone, timedelta

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "claims" / "payload.py"

)
_spec = _ilu.spec_from_file_location('payload', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build = _mod.build
parse = _mod.parse
owner_of = _mod.owner_of

UTC = timezone.utc
NOW = datetime(2024, 3, 5, 12, 30, 45, tzinfo=UTC)
NONCE = "a1b2c3d4"


def test_build_produces_the_exact_five_lines():
    blob = build("agent-1", "task/one", NOW, NONCE)
    text = blob.decode("utf-8")
    lines = text.split("\n")
    assert lines == [
        "imagectl-claim=1",
        "agent=agent-1",
        "task=task/one",
        "at=2024-03-05T12:30:45Z",
        "nonce=" + NONCE,
        "",
    ]


def test_build_is_reproducible_for_identical_inputs():
    b1 = build("agent-1", "task-1", NOW, NONCE)
    b2 = build("agent-1", "task-1", NOW, NONCE)
    assert b1 == b2


def test_different_nonce_gives_different_bytes():
    b1 = build("agent-1", "task-1", NOW, "a1b2c3d4")
    b2 = build("agent-1", "task-1", NOW, "f0f0f0f0")
    assert b1 != b2


def test_different_agent_gives_different_bytes():
    b1 = build("agent-1", "task-1", NOW, NONCE)
    b2 = build("agent-2", "task-1", NOW, NONCE)
    assert b1 != b2


def test_build_converts_offset_datetime_to_utc():
    offset_now = datetime(2024, 3, 5, 8, 30, 45, tzinfo=timezone(timedelta(hours=-4)))
    blob = build("agent-1", "task-1", offset_now, NONCE)
    assert b"at=2024-03-05T12:30:45Z" in blob


def test_build_rejects_naive_datetime():
    naive = datetime(2024, 3, 5, 12, 30, 45)
    with pytest.raises(ValueError):
        build("agent-1", "task-1", naive, NONCE)


def test_build_rejects_newline_in_agent():
    with pytest.raises(ValueError):
        build("agent\n1", "task-1", NOW, NONCE)


def test_build_rejects_equals_sign_in_agent():
    with pytest.raises(ValueError):
        build("agent=1", "task-1", NOW, NONCE)


def test_build_rejects_space_in_task():
    with pytest.raises(ValueError):
        build("agent-1", "task one", NOW, NONCE)


def test_build_rejects_empty_agent_and_empty_task():
    with pytest.raises(ValueError):
        build("", "task-1", NOW, NONCE)
    with pytest.raises(ValueError):
        build("agent-1", "", NOW, NONCE)


def test_build_rejects_short_and_non_hex_nonce():
    with pytest.raises(ValueError):
        build("agent-1", "task-1", NOW, "abc123")  # too short
    with pytest.raises(ValueError):
        build("agent-1", "task-1", NOW, "g1b2c3d4")  # non-hex char


def test_roundtrip_build_then_parse():
    blob = build("agent-1", "task/one", NOW, NONCE)
    fields = parse(blob)
    assert fields == {
        "version": 1,
        "agent": "agent-1",
        "task": "task/one",
        "at": "2024-03-05T12:30:45Z",
        "nonce": NONCE,
    }


def test_parse_accepts_bytes_and_str_identically():
    blob = build("agent-1", "task-1", NOW, NONCE)
    from_bytes = parse(blob)
    from_str = parse(blob.decode("utf-8"))
    assert from_bytes == from_str


def test_parse_rejects_reordered_lines():
    bad = (
        "agent=agent-1\nimagectl-claim=1\ntask=task-1\n"
        "at=2024-03-05T12:30:45Z\nnonce=" + NONCE + "\n"
    )
    with pytest.raises(ValueError):
        parse(bad)


def test_parse_rejects_extra_line():
    good = build("agent-1", "task-1", NOW, NONCE).decode("utf-8")
    bad = good[:-1] + "\nextra=field\n"
    with pytest.raises(ValueError):
        parse(bad)


def test_parse_rejects_missing_line():
    bad = "imagectl-claim=1\nagent=agent-1\ntask=task-1\nnonce=" + NONCE + "\n"
    with pytest.raises(ValueError):
        parse(bad)


def test_parse_rejects_unknown_key():
    bad = (
        "imagectl-claim=1\nagent=agent-1\ntask=task-1\n"
        "at=2024-03-05T12:30:45Z\nbogus=" + NONCE + "\n"
    )
    with pytest.raises(ValueError):
        parse(bad)


def test_parse_rejects_wrong_version():
    bad = (
        "imagectl-claim=2\nagent=agent-1\ntask=task-1\n"
        "at=2024-03-05T12:30:45Z\nnonce=" + NONCE + "\n"
    )
    with pytest.raises(ValueError):
        parse(bad)


def test_parse_rejects_invalid_utf8_bytes():
    with pytest.raises(ValueError):
        parse(b"\xff\xfe\x00\x01")


def test_parse_rejects_bad_at_timestamp():
    bad = (
        "imagectl-claim=1\nagent=agent-1\ntask=task-1\n"
        "at=not-a-timestamp\nnonce=" + NONCE + "\n"
    )
    with pytest.raises(ValueError):
        parse(bad)

    bad_offset = (
        "imagectl-claim=1\nagent=agent-1\ntask=task-1\n"
        "at=2024-03-05T12:30:45+00:00\nnonce=" + NONCE + "\n"
    )
    with pytest.raises(ValueError):
        parse(bad_offset)

    bad_date = (
        "imagectl-claim=1\nagent=agent-1\ntask=task-1\n"
        "at=2024-13-99T99:99:99Z\nnonce=" + NONCE + "\n"
    )
    with pytest.raises(ValueError):
        parse(bad_date)


def test_owner_of_returns_name_for_valid_token():
    blob = build("agent-1", "task-1", NOW, NONCE)
    assert owner_of(blob) == "agent-1"


def test_owner_of_returns_none_for_garbage_and_does_not_raise():
    assert owner_of(b"not a claim token at all") is None
    assert owner_of(b"\xff\xfe garbage") is None


def test_owner_of_none_is_not_an_empty_string():
    result = owner_of(b"garbage")
    assert result is None
    assert result != ""
