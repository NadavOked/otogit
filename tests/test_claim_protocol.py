# tests/test_claim_protocol.py

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "claims" / "protocol.py"

)
_spec = _ilu.spec_from_file_location('protocol', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Decision = _mod.Decision
interpret_push = _mod.interpret_push
plan_claim = _mod.plan_claim
plan_release = _mod.plan_release


ME = {
    "name": "agent-a",
    "payload_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
}
OTHER_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _state(exists=False, sha=None, owner=None, readable=True):
    return {"exists": exists, "sha": sha, "owner": owner, "readable": readable}


def _push(exit_code=0, rejected=False, stderr=""):
    return {"exit_code": exit_code, "rejected": rejected, "stderr": stderr}


def test_missing_ref_plans_push():
    d = plan_claim(_state(exists=False), ME)
    assert d.action == "push"
    assert d.safe is True
    assert d.owner is None


def test_own_claim_is_already_mine_and_safe():
    d = plan_claim(
        _state(exists=True, sha=OTHER_SHA, owner=ME["name"], readable=True),
        ME,
    )
    assert d.action == "already-mine"
    assert d.safe is True
    assert d.owner == ME["name"]


def test_other_owner_stands_down_and_is_not_safe():
    d = plan_claim(
        _state(exists=True, sha=OTHER_SHA, owner="agent-b", readable=True),
        ME,
    )
    assert d.action == "stand-down"
    assert d.safe is False
    assert d.owner == "agent-b"


def test_unreadable_owner_stands_down_and_is_not_safe():
    d = plan_claim(
        _state(exists=True, sha=OTHER_SHA, owner=None, readable=False),
        ME,
    )
    assert d.action == "stand-down"
    assert d.safe is False
    assert d.reason == "owner-unreadable"


def test_identical_payload_sha_stands_down_before_pushing():
    d = plan_claim(
        _state(exists=True, sha=ME["payload_sha"], owner="agent-b", readable=True),
        ME,
    )
    assert d.action == "stand-down"
    assert d.safe is False
    assert d.reason == "identical-payload"


def test_interpret_zero_exit_on_fresh_ref_is_claimed():
    d = interpret_push(_state(exists=False), ME, _push(exit_code=0))
    assert d.action == "claimed"
    assert d.safe is True
    assert d.owner == ME["name"]


def test_interpret_zero_exit_on_identical_payload_is_not_granted():
    d = interpret_push(
        _state(exists=True, sha=ME["payload_sha"], owner="agent-b"),
        ME,
        _push(exit_code=0, rejected=False),
    )
    assert d.action == "not-granted"
    assert d.safe is False


def test_interpret_rejection_stands_down():
    d = interpret_push(
        _state(exists=True, sha=OTHER_SHA, owner="agent-b"),
        ME,
        _push(exit_code=1, rejected=True, stderr="failed to update ref"),
    )
    assert d.action == "stand-down"
    assert d.safe is False


def test_interpret_nonzero_exit_stands_down():
    d = interpret_push(
        _state(exists=False),
        ME,
        _push(exit_code=128, rejected=False, stderr="remote error"),
    )
    assert d.action == "stand-down"
    assert d.safe is False


def test_no_input_ever_yields_retry_rebase_or_force():
    forbidden = {"retry", "rebase", "force"}
    cases = [
        plan_claim(_state(exists=False), ME),
        plan_claim(_state(exists=True, sha=OTHER_SHA, owner=ME["name"]), ME),
        plan_claim(_state(exists=True, sha=OTHER_SHA, owner="agent-b"), ME),
        plan_claim(_state(exists=True, sha=OTHER_SHA, owner=None, readable=False), ME),
        plan_claim(
            _state(exists=True, sha=ME["payload_sha"], owner=None, readable=False),
            ME,
        ),
        interpret_push(_state(exists=False), ME, _push(0, False)),
        interpret_push(_state(exists=True, sha=ME["payload_sha"]), ME, _push(0, False)),
        interpret_push(_state(exists=True, sha=OTHER_SHA), ME, _push(1, True)),
        interpret_push(_state(exists=False), ME, _push(128, False)),
        plan_release(_state(exists=False), ME),
        plan_release(_state(exists=True, owner=ME["name"], readable=True), ME),
        plan_release(_state(exists=True, owner="agent-b", readable=True), ME),
        plan_release(_state(exists=True, owner=None, readable=False), ME),
    ]
    assert len(cases) >= 8
    for d in cases:
        assert d.action not in forbidden
        assert "retry" not in d.reason
        assert "rebase" not in d.reason
        assert "force" not in d.reason


def test_release_missing_ref_is_nothing_to_release():
    d = plan_release(_state(exists=False), ME)
    assert d.action == "nothing-to-release"
    assert d.safe is True


def test_release_own_claim_is_delete():
    d = plan_release(
        _state(exists=True, sha=OTHER_SHA, owner=ME["name"], readable=True), ME
    )
    assert d.action == "delete"
    assert d.safe is True
    assert d.owner == ME["name"]


def test_release_other_owner_is_refuse():
    d = plan_release(
        _state(exists=True, sha=OTHER_SHA, owner="agent-b", readable=True), ME
    )
    assert d.action == "refuse"
    assert d.safe is False
    assert d.reason == "not-owner"


def test_release_unreadable_is_refuse():
    d = plan_release(_state(exists=True, sha=OTHER_SHA, owner=None, readable=False), ME)
    assert d.action == "refuse"
    assert d.safe is False
    assert d.reason == "owner-unreadable"


def test_bad_payload_sha_raises():
    with pytest.raises(ValueError):
        plan_claim(_state(), {"name": "agent-a", "payload_sha": "abc"})
    with pytest.raises(ValueError):
        plan_claim(
            _state(),
            {"name": "agent-a", "payload_sha": "A" * 40},
        )
    with pytest.raises(ValueError):
        plan_claim(
            _state(),
            {
                "name": "agent-a",
                "payload_sha": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
            },
        )


def test_empty_agent_name_raises():
    with pytest.raises(ValueError):
        plan_claim(_state(), {"name": "", "payload_sha": ME["payload_sha"]})


def test_owner_is_reported_when_known():
    d = plan_claim(
        _state(exists=True, sha=OTHER_SHA, owner="agent-b", readable=True),
        ME,
    )
    assert d.action == "stand-down"
    assert d.owner == "agent-b"


def test_decisions_are_deterministic():
    state = _state(exists=True, sha=OTHER_SHA, owner="agent-b", readable=True)
    first = plan_claim(state, ME)
    second = plan_claim(state, ME)
    assert first == second
    assert interpret_push(state, ME, _push(1, True)) == interpret_push(
        state, ME, _push(1, True)
    )
    assert plan_release(state, ME) == plan_release(state, ME)
    assert isinstance(first, Decision)
