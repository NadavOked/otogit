# tools/agents/report/scan.py
import datetime
from typing import NamedTuple, Tuple, Optional, Any, List


class Report(NamedTuple):
    """Scan report summary."""
    status: str
    findings: int
    sources_ok: int
    sources_failed: int
    items_scanned: int
    generated_at: str
    sources: Tuple[dict, ...]


def source(
    name: str,
    ok: bool,
    count: int = 0,
    since: Optional[str] = None,
    detail: Optional[str] = None,
) -> dict:
    """Build one source record."""
    if not isinstance(name, str) or not name:
        raise ValueError("Name must be a non-empty string")
    if type(ok) is not bool:
        raise TypeError("ok must be a real boolean")
    if type(count) is bool or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer (booleans rejected)")

    return {
        "name": name,
        "ok": ok,
        "count": count,
        "since": since,
        "detail": detail,
    }


def build(sources: List[dict], findings: List[Any], now: datetime.datetime) -> Report:
    """Return a Report over what was scanned and what was found."""
    if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
        raise ValueError("now must be timezone-aware")

    sources_tuple = tuple(sources)
    num_findings = len(findings)

    # `ok` is compared identically to True, never truthiness: a record that did
    # not come through source() may carry the string "false", which is truthy.
    ok_count = sum(1 for s in sources_tuple if s["ok"] is True)
    failed_count = sum(1 for s in sources_tuple if s["ok"] is not True)
    scanned_count = sum(s["count"] for s in sources_tuple if s["ok"] is True)

    if not sources_tuple or ok_count == 0:
        status = "failed"
    elif failed_count > 0:
        status = "degraded"
    elif num_findings == 0:
        status = "empty"
    else:
        status = "ok"

    utc_now = now.astimezone(datetime.timezone.utc)
    generated_at = utc_now.isoformat()

    return Report(
        status=status,
        findings=num_findings,
        sources_ok=ok_count,
        sources_failed=failed_count,
        items_scanned=scanned_count,
        generated_at=generated_at,
        sources=sources_tuple,
    )


def render(report: Report) -> str:
    """Return the human-readable text of a report."""
    lines = [
        f"STATUS: {report.status.upper()}",
        f"Findings: {report.findings} | Sources OK: {report.sources_ok} | "
        f"Sources Failed: {report.sources_failed} | "
        f"Items Scanned: {report.items_scanned}",
    ]

    for s in report.sources:
        status_str = "OK" if s["ok"] is True else "FAILED"
        line = f"Source '{s['name']}': {status_str} | Count: {s['count']}"
        if s.get("since"):
            line += f" | Since: {s['since']}"
        if s.get("detail"):
            line += f" | Detail: {s['detail']}"
        lines.append(line)

    if report.status in ("degraded", "failed"):
        failed_names = [s['name'] for s in report.sources if s['ok'] is not True]
        if failed_names:
            names_str = ", ".join(failed_names)
            lines.append(
                "The scan was incomplete. Results do not represent a "
                f"complete picture. Failed sources: {names_str}."
            )
        else:
            lines.append(
                "The scan was incomplete. "
                "Results do not represent a complete picture."
            )

    return "\n".join(lines)
