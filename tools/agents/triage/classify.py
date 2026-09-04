# tools/agents/triage/classify.py
"""Classifier module for proposing automated agent triage labels for issues."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Verdict:
    """Proposes triage labels and rationale for an issue."""

    labels: Tuple[str, ...]
    reason: str
    evidence: Tuple[str, ...]
    confident: bool
    needs_human: bool


def _validate_rules(rules: dict) -> None:
    """Validate rules parameter structure and types."""
    if not isinstance(rules, dict):
        raise ValueError("rules must be a dict")
    if "solo_ok_prefixes" not in rules or not isinstance(
        rules["solo_ok_prefixes"], list
    ):
        raise ValueError("rules must contain solo_ok_prefixes list")
    if (
        "ci_check_names" not in rules
        or not isinstance(rules["ci_check_names"], list)
        or not rules["ci_check_names"]
    ):
        raise ValueError("rules must contain non-empty ci_check_names list")
    if "blocked_reasons" not in rules or not isinstance(rules["blocked_reasons"], dict):
        raise ValueError("rules must contain blocked_reasons dict")


def classify(issue: dict, rules: dict) -> Verdict:
    """Return a Verdict proposing labels for one issue.

    Refuses to overrule human labels.
    """
    _validate_rules(rules)

    existing_labels = issue.get("labels", [])

    # Rule 1 outranks rule 5: a human-only label blocks "no exceptions", even
    # when an agent label is already on the issue. Checked first for that
    # reason — the reverse order hands a security issue to an autonomous agent.
    human_only_labels = rules.get("human_only_labels", [])
    for hl in human_only_labels:
        if hl in existing_labels:
            labels = tuple(sorted(list(set(["agent:blocked", "blocked"]))))
            return Verdict(
                labels=labels,
                reason=f"Issue carries human-only label '{hl}'",
                evidence=(),
                confident=True,
                needs_human=True,
            )

    agent_labels = {"agent:solo-ok", "agent:ready", "agent:blocked"}
    existing_agent_labels = sorted(
        set(label for label in existing_labels if label in agent_labels)
    )

    if existing_agent_labels:
        return Verdict(
            labels=tuple(existing_agent_labels),
            reason=(
                "Issue already has agent label assigned: "
                f"{existing_agent_labels[0]}"
            ),
            evidence=(),
            confident=True,
            needs_human=False,
        )

    title = issue.get("title", "")
    body = issue.get("body", "")
    full_text = f"{title}\n{body}"
    full_text_lower = full_text.lower()

    blocked_reasons = rules.get("blocked_reasons", {})
    matched_reason_label = None
    matched_phrases = []

    for reason_label, phrases in blocked_reasons.items():
        for phrase in phrases:
            if phrase.lower() in full_text_lower:
                # Find exact casing substring from full_text
                start_idx = full_text_lower.find(phrase.lower())
                exact_substring = full_text[start_idx : start_idx + len(phrase)]
                matched_phrases.append(exact_substring)
                if matched_reason_label is None:
                    matched_reason_label = reason_label

    if matched_phrases:
        if matched_reason_label == "blocked":
            labels = tuple(sorted(list(set(["agent:blocked", "blocked"]))))
            return Verdict(
                labels=labels,
                reason="Issue matches blocked reason",
                evidence=tuple(matched_phrases),
                confident=True,
                needs_human=True,
            )
        labels = tuple(sorted(list(set(["agent:blocked", matched_reason_label]))))
        return Verdict(
            labels=labels,
            reason=f"Issue requires blocked reason: {matched_reason_label}",
            evidence=tuple(matched_phrases),
            confident=True,
            needs_human=False,
        )

    blocked_keywords = ["blocked", "blocker", "cannot proceed", "waiting on"]
    found_generic_blocked = [
        full_text[full_text_lower.find(kw) : full_text_lower.find(kw) + len(kw)]
        for kw in blocked_keywords
        if kw in full_text_lower
    ]
    if found_generic_blocked:
        return Verdict(
            labels=("agent:blocked",),
            reason="Detected blocked signal but no specific reason phrase matched",
            evidence=tuple(found_generic_blocked),
            confident=False,
            needs_human=True,
        )

    paths = issue.get("paths", [])
    if not paths:
        return Verdict(
            labels=("agent:ready",),
            reason="File list is unknown",
            evidence=(),
            confident=False,
            needs_human=False,
        )

    solo_ok_prefixes = tuple(rules["solo_ok_prefixes"])
    all_paths_allowed = all(p.startswith(solo_ok_prefixes) for p in paths)

    ci_checks = rules["ci_check_names"]
    matched_ci_checks = []
    for check in ci_checks:
        if check.lower() in full_text_lower:
            idx = full_text_lower.find(check.lower())
            matched_ci_checks.append(full_text[idx : idx + len(check)])

    has_ci_check = len(matched_ci_checks) > 0

    if all_paths_allowed and has_ci_check:
        return Verdict(
            labels=("agent:solo-ok",),
            reason="Paths lie under allowed prefixes and CI check is named",
            evidence=tuple(matched_ci_checks),
            confident=True,
            needs_human=False,
        )

    reasons = []
    if not all_paths_allowed:
        reasons.append("paths touch outside allowed prefixes")
    if not has_ci_check:
        reasons.append("no CI check named")

    return Verdict(
        labels=("agent:ready",),
        reason=f"Ready for review: {', '.join(reasons)}",
        evidence=tuple(matched_ci_checks) if has_ci_check else (),
        confident=True,
        needs_human=False,
    )
