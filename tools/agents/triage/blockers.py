# tools/agents/triage/blockers.py
import re


def _compiled_patterns(patterns):
    compiled = []
    for pattern in patterns:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            # The pattern is quoted verbatim, not repr()'d: it comes from a
            # config file, and a repr doubles every backslash, so the operator
            # cannot grep the message back to the line that caused it.
            raise ValueError(
                "invalid blocker pattern '{}': {}".format(pattern, exc)
            ) from exc
        if regex.groups < 1:
            raise ValueError(
                "blocker pattern has no capturing group: '{}'".format(pattern)
            )
        compiled.append(regex)
    return compiled


def _mask_code(text):
    """Replace fenced and inline code with spaces while preserving positions."""
    chars = list(text)
    in_fence = False
    in_inline = False
    i = 0

    while i < len(text):
        if not in_inline and text.startswith("```", i):
            in_fence = not in_fence
            chars[i:i + 3] = "   "
            i += 3
            continue

        if not in_fence and text[i] == "`":
            in_inline = not in_inline
            chars[i] = " "
            i += 1
            continue

        if in_fence or in_inline:
            if text[i] != "\n":
                chars[i] = " "
        i += 1

    return "".join(chars)


def cited_blockers(body, patterns):
    """Return deduplicated cited blocker issue numbers in first-appearance order."""
    regexes = _compiled_patterns(patterns)
    if body is None or body == "":
        return []

    text = _mask_code(body)
    matches = []

    for regex in regexes:
        for match in regex.finditer(text):
            try:
                number = int(match.group(1))
            except (IndexError, TypeError, ValueError) as exc:
                raise ValueError(
                    "blocker pattern group 1 must capture an issue number: {!r}".format(
                        regex.pattern
                    )
                ) from exc
            matches.append((match.start(), number))

    matches.sort(key=lambda item: item[0])

    result = []
    seen = set()
    for _, number in matches:
        if number not in seen:
            seen.add(number)
            result.append(number)
    return result


def stale_blocks(issues, states, patterns):
    """Return findings for issues that cite blockers, preserving unknown lookups."""
    findings = []

    for issue in sorted(issues, key=lambda item: item["number"]):
        blockers = cited_blockers(issue.get("body"), patterns)
        if not blockers:
            continue

        closed = [
            number for number in blockers
            if states.get(number) == "closed"
        ]
        unknown = [
            number for number in blockers
            if number not in states
        ]

        if unknown:
            verdict = "unknown"
        elif any(states.get(number) == "open" for number in blockers):
            verdict = "still-blocked"
        elif len(closed) == len(blockers):
            verdict = "unblock"
        else:
            verdict = "unknown"

        findings.append(
            {
                "number": issue["number"],
                "blockers": blockers,
                "closed_blockers": closed,
                "unknown_blockers": unknown,
                "verdict": verdict,
            }
        )

    return findings
