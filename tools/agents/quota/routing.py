# tools/agents/quota/routing.py
"""Route a task to a model tier from labels, paths and a rules table.

A tier is about what is worth spending, never about what is permitted.
This module returns only a Decision; it never grants or withdraws capability.
"""

from collections import namedtuple
from typing import Dict, Iterable, List, Optional, Tuple

VALID_TIERS = frozenset({"local", "light", "heavy", "coordinator"})
AUTO_TIERS = frozenset({"local", "light", "heavy"})
TIER_ORDER = {"local": 0, "light": 1, "heavy": 2}

Decision = namedtuple("Decision", ["tier", "reason", "matched", "confident"])


def _validate_rules(rules: dict) -> None:
    if "default_tier" not in rules:
        raise ValueError("missing default_tier")
    default = rules["default_tier"]
    if default not in AUTO_TIERS:
        raise ValueError(
            f"default_tier must be one of local|light|heavy, got {default!r}"
        )

    for section in ("label_tiers", "path_tiers"):
        mapping = rules.get(section) or {}
        for key, tier in mapping.items():
            if tier not in VALID_TIERS:
                raise ValueError(f"unknown tier {tier!r} in {section}")
            if tier == "coordinator":
                raise ValueError(f"coordinator in rules: {section}[{key!r}]")


def _longest_path_match(
    path: str, path_tiers: Dict[str, str]
) -> Optional[Tuple[str, str]]:
    """Return (prefix, tier) for the longest prefix that path starts with, or None."""
    best: Optional[Tuple[str, str]] = None
    best_len = -1
    for prefix, tier in path_tiers.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best = (prefix, tier)
            best_len = len(prefix)
    return best


def route(labels: Iterable[str], paths: Iterable[str], rules: dict) -> Decision:
    """Return a Decision saying which tier should take this task, and why.

    Never returns "coordinator". Raises ValueError for invalid rules tables.
    """
    _validate_rules(rules)

    label_tiers = rules.get("label_tiers") or {}
    path_tiers = rules.get("path_tiers") or {}
    escalate = set(rules.get("escalate_labels") or [])
    default_tier = rules["default_tier"]

    labels_list = list(labels)
    paths_list = list(paths)

    # Escalate forces heavy regardless of other signals.
    for label in labels_list:
        if label in escalate:
            return Decision(
                tier="heavy",
                reason=f"escalate label {label!r}",
                matched=(("label", label),),
                confident=True,
            )

    suggestions: List[Tuple[str, str, str]] = []  # (tier, kind, value)

    for label in labels_list:
        if label in label_tiers:
            suggestions.append((label_tiers[label], "label", label))

    for path in paths_list:
        match = _longest_path_match(path, path_tiers)
        if match is not None:
            prefix, tier = match
            suggestions.append((tier, "path", path))

    if not suggestions:
        return Decision(
            tier=default_tier,
            reason="no rule matched",
            matched=(),
            confident=False,
        )

    # Strongest tier wins: local < light < heavy.
    best_tier = max((s[0] for s in suggestions), key=lambda t: TIER_ORDER[t])
    # Deterministic matched order: labels before paths, then by value.
    matched_list = [
        (kind, value)
        for tier, kind, value in suggestions
        if tier == best_tier
    ]
    matched_list.sort(key=lambda kv: (0 if kv[0] == "label" else 1, kv[1]))
    matched = tuple(matched_list)

    # Reason names a specific label or path that decided it.
    reason_kind, reason_value = matched[0]
    reason = f"{reason_kind} {reason_value!r}"

    return Decision(
        tier=best_tier,
        reason=reason,
        matched=matched,
        confident=True,
    )
