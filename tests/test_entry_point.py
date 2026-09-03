"""נקודת כניסה אחת, ושלושה מצביעים שמובילים אליה.

נמדד ב-2026-09-02, גשש עם קוד-מילה ייחודי לכל קובץ בספרייה ריקה:

    AGENTS.md  נקרא על ידי Codex ו-Grok
    CLAUDE.md  נקרא על ידי Claude Code ו-Grok
    GEMINI.md  נקרא על ידי Gemini CLI

אין קובץ יחיד שכל הסוכנים קוראים. לכן `START.md` הוא הקנוני, ושלושת
האחרים הם מצביעים דקים — לא עותקים. עותק מתבדר בשקט, ואז שני סוכנים
מקבלים שני חוקים שונים בלי שאיש יודע.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
START = ROOT / "START.md"
POINTERS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")


def test_the_canonical_file_exists_and_is_not_a_stub():
    assert START.is_file(), "אין START.md — לסוכן אין לאן להיכנס"
    body = START.read_text(encoding="utf-8")
    assert len(body) > 1500, "START.md קצר מדי מכדי להיות מספיק"


@pytest.mark.parametrize("name", POINTERS)
def test_each_pointer_points_at_the_canonical_file(name):
    p = ROOT / name
    assert p.is_file(), f"{name} חסר — סוכן שקורא אותו לא יגיע לכללים"
    body = p.read_text(encoding="utf-8")
    assert "START.md" in body, f"{name} אינו מפנה ל-START.md"


@pytest.mark.parametrize("name", POINTERS)
def test_a_pointer_is_thin_and_not_a_copy(name):
    """עותק מתבדר בשקט. מצביע לא יכול."""
    body = (ROOT / name).read_text(encoding="utf-8")
    assert len(body) < 600, (
        f"{name} ארוך מדי — נראה כמו עותק ולא כמו מצביע. "
        f"שני עותקים מתבדרים, ואז לכל סוכן חוק אחר.")


def test_the_two_absolutes_are_stated_in_the_canonical_file():
    """מיזוג וסודות אינם ניתנים להתרה על ידי שום קובץ."""
    body = START.read_text(encoding="utf-8")
    assert "אינך ממזג" in body
    assert "סודות" in body


def test_the_visibility_section_tells_the_agent_to_check_and_not_assume():
    body = START.read_text(encoding="utf-8")
    assert "visibility" in body, "אין הנחיה לבדוק אם הריפו ציבורי או פרטי"
    assert "לא אומת" in body, (
        "סעיף הנראות מציג מספרים בלי להצהיר מה מהם לא נמדד")


def test_no_personal_data_leaked_into_the_public_entry_point():
    """הריפו ציבורי. הקובץ הזה הוא הראשון שכל אדם יקרא."""
    blob = "\n".join((ROOT / n).read_text(encoding="utf-8")
                     for n in (["START.md"] + list(POINTERS)))
    for bad in ("נדב", "NadavOked", "ImageCtl", "10.10.10.8", "lab_key"):
        assert bad not in blob, f"פרט אישי דלף לנקודת הכניסה: {bad}"
