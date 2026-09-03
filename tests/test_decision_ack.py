"""בוט אישור-הקבלה — התשובה של הבעלים לא מחכה יותר למזל (#282).

הבעיה שנמדדה: ארבע תשובות ב-05:27–05:32, אפס תגובות, אפס פעולה.
הבוט עונה "נקלט" ופותח Issue בתור. הטסטים שומרים על שלושת הדברים
שהופכים אותו לבטוח, לא רק לעובד.
"""
from pathlib import Path

WF = (Path(__file__).resolve().parent.parent
      / ".github" / "workflows" / "decision-ack.yml")


def test_only_the_owner_triggers_it():
    """לולאת בוט-עונה-לבוט שורפת מכסת Actions בלילה. המסנן הוא הגדר.

    השם עצמו אינו בקוד — הוא ב-`vars.OWNER_LOGIN`, כי הוא שונה בכל
    התקנה. מה שנבדק הוא שהמסנן **קיים ואינו ריק**: תנאי שהושמט
    נראה בדיוק כמו תנאי שעבר, ורק אחד מהם מגן.
    """
    body = WF.read_text(encoding="utf-8")
    assert "github.event.comment.user.login == vars.OWNER_LOGIN" in body


def test_only_the_decision_discussions():
    """אותו כלל: מספרי הדיון בהגדרה, אבל הסינון עצמו חייב להיות שם."""
    body = WF.read_text(encoding="utf-8")
    assert "discussion.number == fromJSON(vars.BOARD_DISCUSSION)" in body
    assert "discussion.number == fromJSON(vars.DECISIONS_DISCUSSION)" in body


def test_the_filter_is_not_silently_open():
    """‏`vars` שאינו מוגדר מחזיר מחרוזת ריקה, והתנאי פשוט לא יתקיים —
    כלומר הבוט לא ירוץ. זה הכיוון הבטוח, וזה מה שנבדק כאן: אין
    ברירת מחדל שפותחת את השער כשההגדרה חסרה."""
    body = WF.read_text(encoding="utf-8")
    assert "|| " not in body[body.index("if: >"):body.index("runs-on")], (
        "יש `||` בתנאי השער — ערך חסר עלול לפתוח אותו")


def test_the_answer_enters_the_agent_queue():
    """אישור בלי תור הוא נימוס בלי תוצאה — הפואנטה היא ה-Issue."""
    body = WF.read_text(encoding="utf-8")
    assert "agent:ready" in body and "issue create" in body


def test_comment_body_is_passed_as_data_not_interpolated():
    """תוכן תגובה הוא נתון. אינטרפולציה שלו לתוך script היא הזרקה."""
    body = WF.read_text(encoding="utf-8")
    assert "BODY: ${{ github.event.comment.body }}" in body
    run = body[body.index("run: |"):]
    assert "${{ github.event.comment.body }}" not in run, (
        "גוף התגובה מוזרק ישירות לתוך ה-script — הזרקת פקודות")
