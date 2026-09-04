# tests/test_owner_reply.py

import pytest

import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "discussions" / "owner_reply.py"

)
_spec = _ilu.spec_from_file_location('owner_reply', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Judgement = _mod.Judgement
is_actionable = _mod.is_actionable


def config(**overrides):
    value = {
        "owner_logins": ["nadavoked"],
        "categories": ["decisions"],
        "discussion_numbers": [212, 215],
        "bot_suffixes": ["[bot]"],
        "min_body_chars": 3,
    }
    value.update(overrides)
    return value


def comment(**overrides):
    value = {
        "id": "c1",
        "author": "nadavoked",
        "author_type": "User",
        "body": "Yes",
        "category": "decisions",
        "discussion_number": 212,
        "created_at": "2026-09-04T12:00:00Z",
        "in_reply_to": None,
    }
    value.update(overrides)
    return value


def test_owner_comment_in_configured_category_is_actionable():
    result = is_actionable(comment(), config())
    assert result.actionable is True
    assert result.reason == "actionable"
    assert result.matched_on == ("category", "discussion")


def test_owner_comment_in_configured_discussion_number_is_actionable():
    result = is_actionable(
        comment(category="other", discussion_number=215), config()
    )
    assert result.actionable is True
    assert result.matched_on == ("discussion",)


def test_matched_on_records_both_when_both_apply():
    result = is_actionable(comment(), config())
    assert result.matched_on == ("category", "discussion")


def test_author_comparison_is_case_insensitive():
    result = is_actionable(comment(author="NaDaVoKeD"), config())
    assert result.actionable is True
    assert result.author == "nadavoked"


def test_author_is_stripped_of_surrounding_whitespace():
    result = is_actionable(comment(author="  nadavoked  "), config())
    assert result.actionable is True
    assert result.author == "nadavoked"


def test_non_owner_is_not_actionable_with_reason_not_owner():
    result = is_actionable(comment(author="someoneelse"), config())
    assert result.actionable is False
    assert result.reason == "not-owner"


def test_bot_author_type_is_rejected():
    result = is_actionable(comment(author_type="Bot"), config())
    assert result.actionable is False
    assert result.reason == "bot-author"


def test_bot_suffix_is_rejected_even_when_type_says_user():
    result = is_actionable(comment(author="nadavoked[bot]"), config(
        owner_logins=["nadavoked[bot]"]
    ))
    assert result.actionable is False
    assert result.reason == "bot-author"


def test_wrong_category_and_wrong_number_is_wrong_thread():
    result = is_actionable(
        comment(category="other", discussion_number=999), config()
    )
    assert result.actionable is False
    assert result.reason == "wrong-thread"
    assert result.matched_on == ()


def test_short_body_is_rejected():
    result = is_actionable(comment(body="ab"), config())
    assert result.actionable is False
    assert result.reason == "body-too-short"


def test_whitespace_only_body_is_rejected():
    result = is_actionable(comment(body="   "), config())
    assert result.actionable is False
    assert result.reason == "body-too-short"


def test_first_failing_rule_wins():
    result = is_actionable(
        comment(
            author_type="Bot",
            category="other",
            discussion_number=999,
            body="",
        ),
        config(),
    )
    assert result.actionable is False
    assert result.reason == "bot-author"


def test_missing_author_is_undecidable_not_not_owner():
    value = comment()
    del value["author"]
    result = is_actionable(value, config())
    assert result.actionable is False
    assert result.reason == "undecidable"


def test_non_string_body_is_undecidable():
    result = is_actionable(comment(body=123), config())
    assert result.actionable is False
    assert result.reason == "undecidable"


def test_missing_discussion_number_is_undecidable():
    value = comment()
    del value["discussion_number"]
    result = is_actionable(value, config())
    assert result.actionable is False
    assert result.reason == "undecidable"


def test_undecidable_is_never_actionable():
    result = is_actionable(comment(author=None), config())
    assert result.actionable is False
    assert result.reason == "undecidable"


def test_empty_owner_logins_raises():
    with pytest.raises(ValueError, match="owner_logins"):
        is_actionable(comment(), config(owner_logins=[]))


def test_missing_owner_logins_raises():
    value = config()
    del value["owner_logins"]
    with pytest.raises(ValueError, match="owner_logins"):
        is_actionable(comment(), value)


def test_both_categories_and_discussion_numbers_empty_raises():
    with pytest.raises(ValueError, match="categories.*discussion_numbers"):
        is_actionable(
            comment(),
            config(categories=[], discussion_numbers=[]),
        )


def test_min_body_chars_below_one_raises():
    with pytest.raises(ValueError, match="min_body_chars"):
        is_actionable(comment(), config(min_body_chars=0))


def test_normalised_author_is_returned_lowercased():
    result = is_actionable(comment(author="  NaDaVoKeD  "), config())
    assert result.author == "nadavoked"


def test_judgement_is_deterministic():
    first = is_actionable(comment(), config())
    second = is_actionable(comment(), config())
    assert first == second
    assert isinstance(first, Judgement)
    assert first.matched_on == ("category", "discussion")


def test_missing_any_decision_field_is_undecidable():
    for field in (
        "author_type",
        "body",
        "category",
        "discussion_number",
    ):
        value = comment()
        del value[field]
        result = is_actionable(value, config())
        assert result == Judgement(False, "undecidable", "nadavoked", ())


def test_wrong_decision_field_type_is_undecidable():
    invalid_values = {
        "author": 123,
        "author_type": None,
        "body": 123,
        "category": None,
        "discussion_number": "212",
    }
    for field, invalid_value in invalid_values.items():
        result = is_actionable(comment(**{field: invalid_value}), config())
        assert result.actionable is False
        assert result.reason == "undecidable"
