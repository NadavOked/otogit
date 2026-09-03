"""טוקן שלא הוגדר מעולם אינו טוקן שנשבר.

הסנכרון ל-otogit האדים על כל מיזוג ל-main מרגע שנוצר, כי
‏OTOGIT_TOKEN טרם הוגדר. אדום קבוע מפסיק להיות אות — וזה מסוכן
יותר מהיעדר סנכרון, כי הוא מרגיל את העין להתעלם מאדום.

‏GitHub אינו מבחין בין סוד שנמחק לסוד שלא היה, ולכן הכוונה
מוצהרת בנפרד: ‏vars.OTOGIT_SYNC_ENABLED. אין הצהרה → דילוג גלוי
עם עקבה. יש הצהרה ואין טוקן → אדום, כי הובטח ונשבר.
"""
from pathlib import Path

WF = (Path(__file__).resolve().parent.parent
      / ".github" / "workflows" / "otogit-sync.yml")


def test_intent_is_declared_separately_from_the_secret():
    body = WF.read_text(encoding="utf-8")
    assert "vars.OTOGIT_SYNC_ENABLED" in body, (
        "בלי הצהרה נפרדת, טוקן שנמחק בטעות נראה כמו 'לא הוגדר מעולם' "
        "והאדום נבלע")


def test_a_promised_sync_with_no_token_is_red():
    body = WF.read_text(encoding="utf-8")
    i = body.index('"${EXPECTED:-}" = "true"')
    assert "exit 1" in body[i:i + 400], (
        "הובטח סנכרון ואין טוקן — חייב להאדים")


def test_an_unpromised_missing_token_skips_loudly():
    body = WF.read_text(encoding="utf-8")
    assert "GITHUB_STEP_SUMMARY" in body and "לא סונכרן" in body, (
        "הדילוג חייב עקבה גלויה — 'לא סונכרן' ו'סונכרן' הם שני מצבים")
    i = body.index("GITHUB_STEP_SUMMARY")
    assert "exit 0" in body[i:i + 200]
