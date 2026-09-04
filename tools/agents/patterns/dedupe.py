# tools/agents/patterns/dedupe.py
"""Helpers for detecting duplicate automation candidates."""

import difflib
import unicodedata


def normalise(text):
    """Return the comparison form of a title or body."""
    if text is None:
        return ""

    text = str(text).lower()
    text = " ".join(text.split())

    # Remove a leading run of Unicode symbols (including common emoji
    # sequences), while deliberately leaving punctuation such as # and /.
    index = 0
    end_of_run = 0
    while index < len(text):
        char = text[index]
        if unicodedata.category(char).startswith("S") or char in "\ufe0e\ufe0f\u200d":
            index += 1
            end_of_run = index
        elif char == " " and index == end_of_run:
            # a space separating two symbols is part of the leading run
            index += 1
        else:
            break
    text = text[end_of_run:]

    return text.strip("`\"'*_").strip()


def fingerprint(candidate):
    """Return a stable string identifying what a candidate is about."""
    sequence = candidate.get("sequence")
    if not sequence:
        raise ValueError("candidate sequence must not be empty")

    return " | ".join(normalise(item) for item in sequence)


def _validate_existing(existing):
    for index, issue in enumerate(existing):
        if "number" not in issue:
            raise ValueError("existing issue %d is missing number" % index)
        if "title" not in issue:
            raise ValueError("existing issue %d is missing title" % index)
        if not isinstance(issue["number"], int):
            raise ValueError("existing issue %d has invalid number" % index)
        if not isinstance(issue["title"], str):
            raise ValueError("existing issue %d has invalid title" % index)


def classify_candidates(candidates, existing, threshold=0.85):
    """Split candidates into new, duplicate, and uncertain matches."""
    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0.0, 1.0]")

    _validate_existing(existing)

    result = {"new": [], "duplicate": [], "uncertain": []}

    normalised_issues = [
        (issue["number"], normalise(issue["title"]), normalise(issue.get("body", "")))
        for issue in existing
    ]

    for candidate in candidates:
        candidate_fp = fingerprint(candidate)

        # Exact fingerprints are checked before any fuzzy comparison.
        exact_issue = None
        for number, _, body in normalised_issues:
            if candidate_fp in body:
                exact_issue = number
                break

        if exact_issue is not None:
            result["duplicate"].append((candidate, exact_issue, 1.0))
            continue

        comparison_text = (
            normalise(candidate["title"])
            if candidate.get("title")
            else candidate_fp
        )

        best_number = None
        best_score = -1.0
        for number, title, _ in normalised_issues:
            score = difflib.SequenceMatcher(
                None, comparison_text, title
            ).ratio()
            if score > best_score:
                best_score = score
                best_number = number

        if best_number is None:
            result["new"].append(candidate)
        elif best_score >= threshold:
            result["duplicate"].append((candidate, best_number, best_score))
        elif best_score >= threshold - 0.10:
            result["uncertain"].append((candidate, best_number, best_score))
        else:
            result["new"].append(candidate)

    return result
