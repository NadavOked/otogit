# tools/agents/claims/protocol.py
"""Claim-lock decision logic. No git, no I/O — only what the caller already saw."""

from typing import NamedTuple, Optional


class Decision(NamedTuple):
    action: str
    owner: Optional[str]
    reason: str
    safe: bool


_HEX = set("0123456789abcdef")
_FORBIDDEN_ACTIONS = frozenset(("retry", "rebase", "force"))


def _validate_me(me):
    if not isinstance(me, dict):
        raise ValueError("me must be a dict")
    name = me.get("name")
    if not isinstance(name, str) or name == "":
        raise ValueError("agent name must be a non-empty string")
    sha = me.get("payload_sha")
    if not isinstance(sha, str) or len(sha) != 40 or any(c not in _HEX for c in sha):
        raise ValueError("payload_sha must be a 40-character lowercase hex string")
    return name, sha


def plan_claim(state, me):
    """Decide the next claim action.

    Never treats unreadable or identical-sha as a win.
    """
    name, payload_sha = _validate_me(me)
    exists = bool(state.get("exists"))
    sha = state.get("sha")
    owner = state.get("owner")
    readable = bool(state.get("readable"))

    if not exists:
        return Decision("push", None, "missing-ref", True)

    # Trap 1: pushing this object is a git no-op. Refuse unless we already own it.
    if sha == payload_sha and owner != name:
        return Decision("stand-down", owner, "identical-payload", False)

    if not readable:
        return Decision("stand-down", owner, "owner-unreadable", False)

    if owner == name:
        return Decision("already-mine", name, "already-mine", True)

    if owner is not None and owner != name:
        return Decision("stand-down", owner, "other-owner", False)

    return Decision("stand-down", owner, "owner-unknown", False)


def interpret_push(state, me, push):
    """Interpret a push result.

    A zero exit is not a claim unless the ref was missing.
    """
    name, payload_sha = _validate_me(me)
    exists = bool(state.get("exists"))
    sha = state.get("sha")
    owner = state.get("owner")
    exit_code = push.get("exit_code")
    rejected = bool(push.get("rejected"))

    if rejected or exit_code != 0:
        reason = "rejected" if rejected else "push-failed"
        return Decision("stand-down", owner, reason, False)

    if not exists:
        return Decision("claimed", name, "claimed", True)

    if sha == payload_sha:
        return Decision("not-granted", owner, "identical-payload", False)

    return Decision("not-granted", owner, "not-granted", False)


def plan_release(state, me):
    """Decide whether this agent may delete the claim.

    Never deletes an unproven owner.
    """
    name, _payload_sha = _validate_me(me)
    exists = bool(state.get("exists"))
    owner = state.get("owner")
    readable = bool(state.get("readable"))

    if not exists:
        return Decision("nothing-to-release", None, "nothing-to-release", True)

    if not readable:
        return Decision("refuse", owner, "owner-unreadable", False)

    if owner == name:
        return Decision("delete", name, "owned", True)

    return Decision("refuse", owner, "not-owner", False)
