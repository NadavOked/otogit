# tools/agents/quota/ledger.py
import json
from datetime import datetime, timezone
from pathlib import Path


_REQUIRED = {
    "ts",
    "provider",
    "account",
    "model",
    "requests",
    "input_tokens",
    "output_tokens",
    "state",
}

_OPTIONAL = {
    "remaining_requests",
    "remaining_tokens",
    "reset_at",
    "task",
    "note",
}

_ALLOWED_STATES = {"known", "estimated", "unknown"}
_COUNT_FIELDS = {"requests", "input_tokens", "output_tokens"}
_OPTIONAL_COUNT_FIELDS = {"remaining_requests", "remaining_tokens"}


def _is_rfc3339(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_nonempty_string(record, field, problems):
    value = record.get(field)
    if not isinstance(value, str) or not value:
        problems.append("%s must be a non-empty string" % field)


def _validate_count(record, field, problems, optional=False):
    if field not in record:
        return
    value = record[field]
    if optional and value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        problems.append("%s must be an integer" % field)
    elif value < 0:
        problems.append("%s must be >= 0" % field)


def validate(record):
    """Return human-readable validation problems; empty means valid."""
    if not isinstance(record, dict):
        return ["record must be a dict"]

    problems = []

    for field in sorted(set(record) - _REQUIRED - _OPTIONAL):
        problems.append("unexpected field: %s" % field)

    for field in sorted(_REQUIRED - set(record)):
        problems.append("missing required field: %s" % field)

    if "ts" in record and not _is_rfc3339(record["ts"]):
        problems.append("ts must be an RFC 3339 timestamp with timezone")

    if "provider" in record:
        _validate_nonempty_string(record, "provider", problems)
        value = record["provider"]
        if isinstance(value, str) and value and value != value.lower():
            problems.append("provider must be lowercase")

    for field in ("account", "model"):
        if field in record:
            _validate_nonempty_string(record, field, problems)

    for field in _COUNT_FIELDS:
        _validate_count(record, field, problems)

    if "state" in record:
        if record["state"] not in _ALLOWED_STATES:
            problems.append(
                "state must be one of: estimated, known, unknown"
            )

    for field in _OPTIONAL_COUNT_FIELDS:
        _validate_count(record, field, problems, optional=True)

    if "reset_at" in record:
        value = record["reset_at"]
        if value is not None and not _is_rfc3339(value):
            problems.append(
                "reset_at must be an RFC 3339 timestamp with timezone or null"
            )

    for field in ("task", "note"):
        if field in record and not isinstance(record[field], str):
            problems.append("%s must be a string" % field)

    return problems


def append(path, record, now):
    """Append one valid record and return the new normalised dict."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    normalised = dict(record)
    if "ts" not in normalised:
        normalised["ts"] = now.astimezone(timezone.utc).isoformat()

    problems = validate(normalised)
    if problems:
        raise ValueError("; ".join(problems))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        normalised,
        sort_keys=True,
        ensure_ascii=False,
    )

    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")
        handle.flush()

    return normalised


def read_all(path):
    """Return (valid records, rejected-line problems) without hiding corruption."""
    path = Path(path)
    try:
        handle = path.open("r", encoding="utf-8")
    except FileNotFoundError:
        return [], []

    records = []
    problems = []

    with handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            try:
                value = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                problems.append("line %d: %s" % (line_number, exc))
                continue

            validation_problems = validate(value)
            if validation_problems:
                problems.append(
                    "line %d: %s"
                    % (line_number, "; ".join(validation_problems))
                )
                continue

            records.append(value)

    return records, problems
