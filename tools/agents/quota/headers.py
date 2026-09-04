# tools/agents/quota/headers.py
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional, Tuple

RE_DURATION = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?(?:(\d+)ms)?$")


@dataclass(frozen=True)
class Reading:
    provider: str
    state: str
    limit_requests: Optional[int]
    remaining_requests: Optional[int]
    limit_tokens: Optional[int]
    remaining_tokens: Optional[int]
    reset_at: Optional[datetime]
    reason: str


def _parse_int(val: Optional[str]) -> Tuple[Optional[int], bool]:
    if val is None:
        return None, True
    val = val.strip()
    if not val.isdigit():
        return None, False
    return int(val), True


def _parse_iso(val: str) -> Optional[datetime]:
    if val.endswith("Z") or val.endswith("z"):
        val = val[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_duration(val: str, now: datetime) -> Optional[datetime]:
    val = val.strip()
    if val.isdigit():
        return now + timedelta(seconds=int(val))

    match = RE_DURATION.match(val)
    if not match or not any(match.groups()):
        return None

    h, m, s, ms = (int(g) if g else 0 for g in match.groups())
    total_sec = h * 3600 + m * 60 + s
    delta = timedelta(seconds=total_sec, milliseconds=ms)
    if ms > 0:
        # Sub-second components round up to the next whole second
        delta = timedelta(seconds=total_sec + 1)
    return now + delta


def _parse_reset(val: Optional[str], now: datetime) -> Optional[datetime]:
    if not val:
        return None
    res = _parse_duration(val, now)
    if res is not None:
        return res
    return _parse_iso(val)


def parse_rate_limit_headers(
    provider: Optional[str],
    headers: Optional[Mapping[str, str]],
    now: datetime,
) -> Reading:
    """Return a Reading for one HTTP response header mapping."""
    if not provider or not isinstance(provider, str):
        return Reading("", "unknown", None, None, None, None, None, "unknown-provider")

    provider_clean = provider.lower().strip()
    valid_providers = {"anthropic", "xai", "groq", "google", "openai"}

    if provider_clean not in valid_providers:
        return Reading(
            provider_clean,
            "unknown",
            None, None, None, None, None,
            "unknown-provider",
        )

    if provider_clean == "google":
        return Reading(
            "google",
            "estimated",
            None, None, None, None, None,
            "provider-sends-no-headers",
        )

    norm_headers = {}
    if headers:
        for k, v in headers.items():
            if k is not None and v is not None:
                norm_headers[str(k).lower()] = str(v)

    req_lim_str = norm_headers.get("x-ratelimit-limit-requests")
    req_rem_str = norm_headers.get("x-ratelimit-remaining-requests")
    tok_lim_str = norm_headers.get("x-ratelimit-limit-tokens")
    tok_rem_str = norm_headers.get("x-ratelimit-remaining-tokens")
    req_res_str = norm_headers.get("x-ratelimit-reset-requests")
    tok_res_str = norm_headers.get("x-ratelimit-reset-tokens")

    has_any = any(
        x is not None
        for x in (
            req_lim_str,
            req_rem_str,
            tok_lim_str,
            tok_rem_str,
            req_res_str,
            tok_res_str,
        )
    )

    req_lim, req_lim_ok = _parse_int(req_lim_str)
    req_rem, req_rem_ok = _parse_int(req_rem_str)
    tok_lim, tok_lim_ok = _parse_int(tok_lim_str)
    tok_rem, tok_rem_ok = _parse_int(tok_rem_str)

    if not (req_lim_ok and req_rem_ok and tok_lim_ok and tok_rem_ok):
        return Reading(
            provider_clean,
            "unknown",
            None,
            None,
            None,
            None,
            None,
            "unparseable-remaining",
        )

    if not has_any and provider_clean != "openai":
        return Reading(
            provider_clean,
            "unknown",
            None,
            None,
            None,
            None,
            None,
            "no-headers",
        )

    res_req_dt = _parse_reset(req_res_str, now)
    res_tok_dt = _parse_reset(tok_res_str, now)

    reset_at = None
    if res_req_dt and res_tok_dt:
        reset_at = max(res_req_dt, res_tok_dt)
    else:
        reset_at = res_req_dt or res_tok_dt

    if provider_clean == "openai":
        return Reading(
            "openai",
            "estimated",
            req_lim,
            req_rem,
            tok_lim,
            tok_rem,
            reset_at,
            "provider-numbers-untrusted",
        )

    if req_rem is None and tok_rem is None:
        return Reading(
            provider_clean,
            "unknown",
            None,
            None,
            None,
            None,
            None,
            "no-headers",
        )

    return Reading(
        provider_clean,
        "known",
        req_lim,
        req_rem,
        tok_lim,
        tok_rem,
        reset_at,
        "",
    )
