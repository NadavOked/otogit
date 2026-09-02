"""מפתח שלא הוגדר מעולם אינו מפתח שנשבר.

‏GitHub אינו מבחין ביניהם — סוד שנמחק וסוד שלא היה נראים זהים. לכן
הכוונה מוצהרת בנפרד (`REVIEW_ENABLED`), ולכל צירוף יש תוצאה אחרת:

    אין מפתח, אין הצהרה  → דילוג גלוי (absent) — ריפו שאימץ את
                            התבנית בלי מפתח אינו אדום לנצח
    אין מפתח, יש הצהרה   → אדום (broken) — הובטחה סקירה ואין
    יש מפתח               → הסקירה רצה

הסכנה שהטסט שומר ממנה: מחיקת ההצהרה או שינוי הסדר יהפכו מפתח
שנמחק בטעות לירוק שקט — בדיוק הקיפול שעיקרון 5 אוסר.
"""
from pathlib import Path

WF = (Path(__file__).resolve().parent.parent
      / ".github" / "workflows" / "agent-review.yml")


def test_intent_is_declared_separately_from_the_secret():
    body = WF.read_text(encoding="utf-8")
    assert "vars.REVIEW_ENABLED" in body, (
        "בלי הצהרת כוונה נפרדת, סוד שנמחק בטעות נראה כמו 'לא הוגדר "
        "מעולם' — והאדום שהיה אמור להופיע נבלע")


def test_a_promised_review_with_no_key_is_red():
    body = WF.read_text(encoding="utf-8")
    i = body.index('"$EXPECTED" = "true"')
    assert "exit 1" in body[i:i + 400], (
        "‏REVIEW_ENABLED=true עם מפתח ריק חייב להאדים — הובטחה סקירה")


def test_an_unpromised_missing_key_skips_loudly_not_silently():
    body = WF.read_text(encoding="utf-8")
    assert "GITHUB_STEP_SUMMARY" in body and "לא נסקר" in body, (
        "הדילוג חייב להשאיר עקבה גלויה — 'לא נסקר' ו'נסקר ותקין' הם "
        "שני מצבים שונים")
    i = body.index("GITHUB_STEP_SUMMARY")
    assert "exit 0" in body[i:i + 200], "אחרי העקבה — יציאה נקייה"
