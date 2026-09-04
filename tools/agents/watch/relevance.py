# tools/agents/watch/relevance.py
"""Filter CI platform changelog entries for relevance to our repository."""

from collections import namedtuple
from typing import Any, Dict, List, Sequence, Tuple

Relevance = namedtuple(
    "Relevance",
    ["id", "verdict", "topics", "matches", "touches"],
)

def _validate_topics(topics: Dict[str, Dict[str, Any]]) -> None:
    for name, cfg in topics.items():
        terms = cfg.get("terms")
        if not terms:
            raise ValueError(f"topic {name!r} has empty terms")

def _word_matches(term: str, text: str) -> bool:
    """Case-insensitive whole-word match; term matches word or word+'s'."""
    term_l = term.lower()
    # Split on non-alphanumeric to approximate word boundaries.
    import re
    words = re.findall(r"[a-zA-Z0-9]+", text)
    for w in words:
        wl = w.lower()
        if wl == term_l or wl == term_l + "s":
            return True
    return False

def score_entry(entry: Dict[str, Any], topics: Dict[str, Dict[str, Any]]) -> Relevance:
    """Return a Relevance for one changelog entry.

    verdict is "relevant" when at least one topic matched, "not-relevant"
    when the entry was fully readable and no topic matched, or "undecidable"
    when the entry cannot be judged (missing/empty/non-string title+body
    or missing id). Never treats an unreadable entry as not-relevant.
    """
    _validate_topics(topics)

    eid = entry.get("id")
    if eid is None or not isinstance(eid, str):
        return Relevance(
            id=str(eid) if eid is not None else "",
            verdict="undecidable",
            topics=(),
            matches=(),
            touches=(),
        )

    title = entry.get("title")
    body = entry.get("body")

    title_ok = isinstance(title, str) and title.strip() != ""
    body_ok = isinstance(body, str) and body.strip() != ""

    if not title_ok and not body_ok:
        return Relevance(
            id=eid,
            verdict="undecidable",
            topics=(),
            matches=(),
            touches=(),
        )
    if not isinstance(title, str) or not isinstance(body, str):
        return Relevance(
            id=eid,
            verdict="undecidable",
            topics=(),
            matches=(),
            touches=(),
        )

    text = (title or "") + " " + (body or "")

    matched_topics: List[str] = []
    matched_terms: List[str] = []
    matched_touches: List[str] = []

    for tname, cfg in topics.items():
        terms = cfg.get("terms") or []
        t_touches = cfg.get("touches") or []
        topic_matched = False
        for term in terms:
            if _word_matches(term, text):
                topic_matched = True
                matched_terms.append(term.lower())
        if topic_matched:
            matched_topics.append(tname)
            matched_touches.extend(t_touches)

    if matched_topics:
        return Relevance(
            id=eid,
            verdict="relevant",
            topics=tuple(sorted(matched_topics)),
            matches=tuple(sorted(set(matched_terms))),
            touches=tuple(sorted(set(matched_touches))),
        )
    return Relevance(
        id=eid,
        verdict="not-relevant",
        topics=(),
        matches=(),
        touches=(),
    )

def filter_entries(
    entries: Sequence[Dict[str, Any]], topics: Dict[str, Dict[str, Any]]
) -> Tuple[List[Relevance], List[Relevance], Dict[str, Any]]:
    """Return (relevant, dropped, summary) for a batch.

    relevant contains Relevance objects with verdict "relevant", in input
    order. dropped contains the rest ("not-relevant" or "undecidable").
    Every input appears in exactly one of the two lists.

    summary counts scanned / relevant / not_relevant / undecidable and
    records earliest/latest published strings (compared as strings) or
    None when none present. An empty entries list yields scanned=0; the
    caller should treat that as a failed fetch rather than a calm week.
    """
    _validate_topics(topics)

    relevant: List[Relevance] = []
    dropped: List[Relevance] = []
    counts = {"relevant": 0, "not_relevant": 0, "undecidable": 0}
    published_dates: List[str] = []

    for entry in entries:
        rel = score_entry(entry, topics)
        if rel.verdict == "relevant":
            relevant.append(rel)
            counts["relevant"] += 1
        else:
            dropped.append(rel)
            if rel.verdict == "not-relevant":
                counts["not_relevant"] += 1
            else:
                counts["undecidable"] += 1

        pub = entry.get("published")
        if isinstance(pub, str) and pub:
            published_dates.append(pub)

    earliest = min(published_dates) if published_dates else None
    latest = max(published_dates) if published_dates else None

    summary = {
        "scanned": len(entries),
        "relevant": counts["relevant"],
        "not_relevant": counts["not_relevant"],
        "undecidable": counts["undecidable"],
        "topics_configured": len(topics),
        "earliest": earliest,
        "latest": latest,
    }
    return relevant, dropped, summary
