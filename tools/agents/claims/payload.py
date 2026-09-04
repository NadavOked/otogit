# tools/agents/claims/payload.py
"""Build and parse imagectl claim tokens.

A claim token is a strict, reproducible byte string that names the agent
which owns a task. It is the only thing two racing agents share, so it
must be unique by construction (see `build`) and must never be accepted
in a form that could be misread (see `parse`).
"""

import re
from datetime import datetime, timezone

_VERSION_LINE = "imagectl-claim=1"
_EXPECTED_KEYS = ["imagectl-claim", "agent", "task", "at", "nonce"]

_AGENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TASK_RE = re.compile(r"^[A-Za-z0-9._/-]{1,128}$")
_NONCE_RE = re.compile(r"^[0-9a-f]{8,64}$")
_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _validate(name, value, pattern):
    if not isinstance(value, str) or not pattern.match(value):
        raise ValueError("invalid %s: %r" % (name, value))


def build(agent, task, now, nonce):
    """Return the exact bytes of a claim token for (agent, task, now, nonce).

    Raises ValueError if any field fails validation. Two calls that differ
    only in `nonce` are guaranteed to produce different bytes.
    """
    _validate("agent", agent, _AGENT_RE)
    _validate("task", task, _TASK_RE)
    _validate("nonce", nonce, _NONCE_RE)

    if not isinstance(now, datetime):
        raise ValueError("now must be a datetime: %r" % (now,))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    at_utc = now.astimezone(timezone.utc)
    at_str = at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        _VERSION_LINE,
        "agent=" + agent,
        "task=" + task,
        "at=" + at_str,
        "nonce=" + nonce,
    ]
    text = "\n".join(lines) + "\n"
    return text.encode("utf-8")


def parse(blob):
    """Return {version, agent, task, at, nonce} parsed from a claim token.

    Raises ValueError, with a message naming what was wrong, for any
    deviation from the exact five-line format: wrong line count, a line
    without '=', keys out of order, an unknown key, a missing key, a
    version other than 1, a field failing its own character rules, an
    `at` that is not RFC 3339 UTC ("...Z"), or bytes that are not valid
    UTF-8. No whitespace stripping is performed.
    """
    if isinstance(blob, bytes):
        try:
            text = blob.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("blob is not valid UTF-8: %s" % (exc,))
    elif isinstance(blob, str):
        text = blob
    else:
        raise ValueError("blob must be bytes or str, got %r" % (type(blob),))

    parts = text.split("\n")
    if len(parts) == 0 or parts[-1] != "":
        raise ValueError("token must end with a trailing newline")
    content_lines = parts[:-1]

    if len(content_lines) != len(_EXPECTED_KEYS):
        raise ValueError(
            "expected %d lines, got %d" % (len(_EXPECTED_KEYS), len(content_lines))
        )

    fields = {}
    for i, line in enumerate(content_lines):
        key, sep, value = line.partition("=")
        if sep == "":
            raise ValueError("line %d missing '=': %r" % (i, line))
        if key not in _EXPECTED_KEYS:
            raise ValueError("unknown key: %r" % (key,))
        if key != _EXPECTED_KEYS[i]:
            raise ValueError(
                "keys out of order: expected %r at position %d, got %r"
                % (_EXPECTED_KEYS[i], i, key)
            )
        if key in fields:
            raise ValueError("duplicate key: %r" % (key,))
        fields[key] = value

    for key in _EXPECTED_KEYS:
        if key not in fields:
            raise ValueError("missing key: %r" % (key,))

    if fields["imagectl-claim"] != "1":
        raise ValueError("unsupported version: %r" % (fields["imagectl-claim"],))

    _validate("agent", fields["agent"], _AGENT_RE)
    _validate("task", fields["task"], _TASK_RE)
    _validate("nonce", fields["nonce"], _NONCE_RE)

    at_value = fields["at"]
    if not _AT_RE.match(at_value):
        raise ValueError("at is not RFC 3339 UTC: %r" % (at_value,))
    try:
        datetime.strptime(at_value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("at is not a valid timestamp: %r" % (at_value,))

    return {
        "version": 1,
        "agent": fields["agent"],
        "task": fields["task"],
        "at": at_value,
        "nonce": fields["nonce"],
    }


def owner_of(blob):
    """Return the owning agent's name, or None if the token cannot be trusted.

    Never raises. A None result means ownership could not be established
    and callers MUST treat it as "stand down", not as "task is unowned".
    """
    try:
        fields = parse(blob)
    except ValueError:
        return None
    return fields["agent"]
