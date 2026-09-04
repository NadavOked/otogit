# tools/agents/quota/manifest.py
import json
from datetime import date
from pathlib import Path


_TOP_LEVEL = {"version", "updated", "providers"}
_SCOPES = {"account", "model", "unknown"}
_WINDOW_KINDS = {"rolling", "daily", "monthly"}
_SOURCES = {"measured", "owner-reported", "third-party", "guess"}
_LIMIT_KEYS = {"requests", "tokens"}


def _is_iso_date(value):
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10 and value[4] == "-" and value[7] == "-"


def _problem(path, message):
    return f"{path}: {message}"


def _validate_limits(value, path):
    problems = []
    numeric = False

    if not isinstance(value, dict):
        return [_problem(path, "must be an object")], False

    for key in value:
        if key not in _LIMIT_KEYS:
            problems.append(_problem(f"{path}.{key}", "unknown key"))

    for key in _LIMIT_KEYS:
        if key not in value:
            continue
        item = value[key]
        if item is None:
            continue
        if isinstance(item, bool) or not isinstance(item, int):
            problems.append(_problem(
                f"{path}.{key}", "must be a positive integer or null"
            ))
        elif item <= 0:
            problems.append(_problem(
                f"{path}.{key}", "must be a positive integer or null"
            ))
        else:
            numeric = True
    return problems, numeric


def _validate_source(entry, path, numeric):
    problems = []
    has_source = "source" in entry

    if numeric and not has_source:
        problems.append(_problem(
            f"{path}.source",
            "missing, but limits contains a numeric value"
        ))
    if has_source:
        source = entry["source"]
        if source not in _SOURCES:
            problems.append(_problem(
                f"{path}.source",
                f"must be one of {sorted(_SOURCES)}"
            ))
        if "measured_at" not in entry:
            problems.append(_problem(
                f"{path}.measured_at",
                "missing, but source is present"
            ))
    if "measured_at" in entry and not _is_iso_date(entry["measured_at"]):
        problems.append(_problem(
            f"{path}.measured_at", "must be an ISO date YYYY-MM-DD"
        ))
    return problems


def _validate_window(value, path):
    problems = []
    if not isinstance(value, dict):
        return [_problem(path, "must be an object")]

    kind = value.get("kind")
    if kind not in _WINDOW_KINDS:
        problems.append(_problem(
            f"{path}.kind",
            f"must be one of {sorted(_WINDOW_KINDS)}"
        ))
        return problems

    if kind == "rolling":
        if "hours" not in value:
            problems.append(_problem(
                f"{path}.hours", "missing for rolling window"
            ))
        elif isinstance(value["hours"], bool) or not isinstance(
            value["hours"], (int, float)
        ) or value["hours"] <= 0:
            problems.append(_problem(
                f"{path}.hours", "must be a positive number"
            ))
    else:
        if "tz" not in value:
            problems.append(_problem(
                f"{path}.tz", f"missing for {kind} window"
            ))
        elif not isinstance(value["tz"], str) or not value["tz"]:
            problems.append(_problem(
                f"{path}.tz", "must be a non-empty string"
            ))

    if kind == "monthly" and "anchor_day" in value:
        anchor = value["anchor_day"]
        if (
            isinstance(anchor, bool)
            or not isinstance(anchor, int)
            or not 1 <= anchor <= 31
        ):
            problems.append(_problem(
                f"{path}.anchor_day", "must be an integer in 1..31"
            ))
    return problems


def _validate_entry(entry, path, required):
    problems = []
    if not isinstance(entry, dict):
        return [_problem(path, "must be an object")], False

    if required:
        for key, kind in (
            ("paid", bool),
            ("billing_enabled", bool),
            ("scope", str),
            ("window", dict),
            ("reports_remaining_quota", bool),
        ):
            if key not in entry:
                problems.append(_problem(f"{path}.{key}", "missing"))
            elif not isinstance(entry[key], kind):
                problems.append(_problem(
                    f"{path}.{key}", f"must be a {kind.__name__}"
                ))

        if (
            isinstance(entry.get("paid"), bool)
            and isinstance(entry.get("billing_enabled"), bool)
            and not entry["paid"]
            and entry["billing_enabled"]
        ):
            problems.append(_problem(
                f"{path}.billing_enabled",
                "cannot be true when paid is false"
            ))

        if "scope" in entry and entry["scope"] not in _SCOPES:
            problems.append(_problem(
                f"{path}.scope", f"must be one of {sorted(_SCOPES)}"
            ))

        if "window" in entry:
            problems.extend(_validate_window(entry["window"], f"{path}.window"))

    numeric = False
    if "limits" in entry:
        limit_problems, numeric = _validate_limits(
            entry["limits"], f"{path}.limits"
        )
        problems.extend(limit_problems)
        problems.extend(_validate_source(entry, path, numeric))
    elif "source" in entry:
        problems.extend(_validate_source(entry, path, False))

    if "models" in entry:
        models = entry["models"]
        if not isinstance(models, dict):
            problems.append(_problem(f"{path}.models", "must be an object"))
        else:
            for model, model_entry in models.items():
                model_path = f"{path}.models.{model}"
                model_problems, model_numeric = _validate_entry(
                    model_entry, model_path, False
                )
                problems.extend(model_problems)
                if (
                    entry.get("scope") == "account"
                    and model_numeric
                ):
                    problems.append(
                        f"provider '{path.split('.')[-1]}': scope is account "
                        f"but model '{model}' declares its own limits"
                    )
    if (
        entry.get("scope") == "model"
        and numeric
    ):
        problems.append(_problem(
            f"{path}.limits",
            "numeric limits are not allowed when scope is model"
        ))

    return problems, numeric


def validate_manifest(doc):
    """Return all validation problems; refuse non-dict documents with TypeError."""
    if not isinstance(doc, dict):
        raise TypeError("manifest must be a dict")

    problems = []
    for key in doc:
        if key not in _TOP_LEVEL:
            problems.append(_problem(key, "unknown top-level key"))

    if doc.get("version") != 1 or (
        "version" in doc and
        (isinstance(doc["version"], bool) or not isinstance(doc["version"], int))
    ):
        problems.append(_problem("version", "must be the integer 1"))

    if "updated" not in doc:
        problems.append(_problem("updated", "missing"))
    elif not _is_iso_date(doc["updated"]):
        problems.append(_problem("updated", "must be an ISO date YYYY-MM-DD"))

    if "providers" not in doc:
        problems.append(_problem("providers", "missing"))
    elif not isinstance(doc["providers"], dict):
        problems.append(_problem("providers", "must be an object"))
    elif not doc["providers"]:
        problems.append(_problem("providers", "must be a non-empty object"))
    else:
        for name, provider in doc["providers"].items():
            provider_problems, _ = _validate_entry(
                provider, f"providers.{name}", True
            )
            problems.extend(provider_problems)

    return problems


def load_and_validate(path):
    """Read JSON from path and return (document, problems).

    Never raises for missing or malformed files.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, [f"{path}: no such file"]
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"{path}: not valid JSON: {exc.msg}"]
    return doc, validate_manifest(doc)
