# tools/agents/quota/scope.py
"""Counting-key derivation for AI provider usage quotas.

This module answers exactly one question: under what string key should a
single API call's usage be accumulated, given a *declared* scope? It does
no counting on disk, no network calls, and applies no default scope --
a caller that doesn't know the scope must say "unknown" explicitly.
"""


def _normalise(segment):
    """Lowercase a key segment and escape internal '/' so segments never merge."""
    return segment.replace("/", "_").lower()


def counting_key(provider, account, model, scope):
    """Return the string under which this call's usage must be accumulated.

    scope must be exactly one of "account", "model", "unknown" -- there is
    no default, and any other value raises ValueError naming it.
    """
    if not isinstance(provider, str) or provider == "":
        raise ValueError("provider must be a non-empty string")
    if not isinstance(account, str) or account == "":
        raise ValueError("account must be a non-empty string")
    if scope not in ("account", "model", "unknown"):
        raise ValueError("unknown scope: {!r}".format(scope))

    if scope in ("model", "unknown"):
        if not isinstance(model, str) or model == "":
            raise ValueError(
                "model must be a non-empty string when scope={!r}".format(scope)
            )

    p = _normalise(provider)
    a = _normalise(account)

    if scope == "account":
        return "{}/{}".format(p, a)

    m = _normalise(model)

    if scope == "model":
        return "{}/{}/{}".format(p, a, m)

    # scope == "unknown": trailing '?' is load-bearing, see brief.
    return "{}/{}/{}?".format(p, a, m)


_REQUIRED_ROW_FIELDS = (
    "provider",
    "account",
    "model",
    "requests",
    "input_tokens",
    "output_tokens",
)
_COUNT_FIELDS = ("requests", "input_tokens", "output_tokens")


def _is_clean_int(value):
    # bool is a subclass of int in Python; a count must not silently accept True/False.
    return isinstance(value, int) and not isinstance(value, bool)


def group_usage(rows, scope_of):
    """Fold per-call rows into per-counting-key totals.

    Returns (totals, rejected):
      totals: dict of counting_key -> {"requests", "input_tokens",
        "output_tokens", "calls"} ints.
      rejected: list of (row_index, reason) for rows that could not be
        counted. Such rows are never folded into totals as zero, and never
        silently dropped without a reason.

    scope_of(provider, account) -> scope string; this is how the manifest
    is injected without this module reading any file.
    """
    totals = {}
    rejected = []

    for idx, row in enumerate(rows):
        missing = [f for f in _REQUIRED_ROW_FIELDS if f not in row]
        if missing:
            rejected.append((idx, "missing field(s): " + ", ".join(missing)))
            continue

        bad_counts = [f for f in _COUNT_FIELDS if not _is_clean_int(row[f])]
        if bad_counts:
            rejected.append(
                (idx, "non-integer count field(s): " + ", ".join(bad_counts))
            )
            continue

        scope = scope_of(row["provider"], row["account"])
        try:
            key = counting_key(row["provider"], row["account"], row["model"], scope)
        except ValueError as exc:
            rejected.append((idx, "invalid scope/key: {}".format(exc)))
            continue

        bucket = totals.setdefault(
            key, {"requests": 0, "input_tokens": 0, "output_tokens": 0, "calls": 0}
        )
        bucket["requests"] += row["requests"]
        bucket["input_tokens"] += row["input_tokens"]
        bucket["output_tokens"] += row["output_tokens"]
        bucket["calls"] += 1

    return totals, rejected


def limit_for(key, entries):
    """Return (limit, source) for a counting key, or (None, reason).

    Never returns a guessed number, and never (None, "ok"). Absence of a
    declaration and an unparseable declaration are reported with distinct
    reasons so a caller cannot confuse "unknown ceiling" with "no ceiling".
    """
    if key not in entries:
        return (None, "no-limit-declared")

    declaration = entries[key]
    limit = declaration.get("limit") if isinstance(declaration, dict) else None

    if not _is_clean_int(limit) or limit < 0:
        return (None, "limit-unparseable")

    source = declaration.get("source")
    return (limit, source)
