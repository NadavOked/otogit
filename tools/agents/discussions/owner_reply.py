# tools/agents/discussions/owner_reply.py

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Judgement:
    actionable: bool
    reason: str
    author: str
    matched_on: Tuple[str, ...]


def _validate_config(config: dict) -> None:
    if "owner_logins" not in config:
        raise ValueError("owner_logins is required")
    owner_logins = config["owner_logins"]
    if not isinstance(owner_logins, (list, tuple)):
        raise ValueError("owner_logins must be a list or tuple")
    if not owner_logins:
        raise ValueError("owner_logins must not be empty")

    categories = config.get("categories")
    discussion_numbers = config.get("discussion_numbers")
    if not categories and not discussion_numbers:
        raise ValueError(
            "categories and discussion_numbers must not both be empty"
        )

    if "min_body_chars" not in config:
        raise ValueError("min_body_chars is required")
    min_body_chars = config["min_body_chars"]
    if isinstance(min_body_chars, bool) or not isinstance(min_body_chars, int):
        raise ValueError("min_body_chars must be an integer")
    if min_body_chars < 1:
        raise ValueError("min_body_chars must be at least 1")


def _decision_fields_valid(comment: dict) -> bool:
    required = (
        "author",
        "author_type",
        "body",
        "category",
        "discussion_number",
    )
    if not isinstance(comment, dict):
        return False
    if any(field not in comment for field in required):
        return False

    if not isinstance(comment["author"], str):
        return False
    if not isinstance(comment["author_type"], str):
        return False
    if not isinstance(comment["body"], str):
        return False
    if not isinstance(comment["category"], str):
        return False

    number = comment["discussion_number"]
    if isinstance(number, bool) or not isinstance(number, int):
        return False

    return True


def is_actionable(comment, config):
    """Return a Judgement for one discussion comment.

    Malformed decision fields return ``undecidable`` rather than a
    permissive negative result; callers should treat that as a job
    failure, not as a comment to ignore.
    """
    _validate_config(config)

    if not _decision_fields_valid(comment):
        author = comment.get("author", "") if isinstance(comment, dict) else ""
        if not isinstance(author, str):
            author = ""
        return Judgement(False, "undecidable", author.strip().lower(), ())

    author = comment["author"].strip().lower()

    owners = {
        login.strip().lower()
        for login in config["owner_logins"]
        if isinstance(login, str)
    }
    if author not in owners:
        return Judgement(False, "not-owner", author, ())

    suffixes = config.get("bot_suffixes", [])
    if comment["author_type"] == "Bot" or any(
        author.endswith(suffix)
        for suffix in suffixes
    ):
        return Judgement(False, "bot-author", author, ())

    matched_on = []
    if comment["category"] in config.get("categories", []):
        matched_on.append("category")
    if comment["discussion_number"] in config.get("discussion_numbers", []):
        matched_on.append("discussion")

    if not matched_on:
        return Judgement(False, "wrong-thread", author, ())

    if len(comment["body"].strip()) < config["min_body_chars"]:
        return Judgement(False, "body-too-short", author, tuple(matched_on))

    return Judgement(True, "actionable", author, tuple(matched_on))
