"""‏`providers.json` הוא מקור אמת, ולא קובץ שמתיישן בשקט.

הוא נולד מהערה של הבעלים: היה מסמך מגבלות לבני אדם, ושום כלי לא ידע
ש-Gemini חינמי ורגיש לקצב. קובץ שאיש אינו קורא הוא הבטחה, לא מקור
אמת — ולכן הטסט הזה קושר אותו למה שקורה בפועל ב-workflows.

**מה הוא שומר:**

1. שכל מודל שנמצא בשימוש ב-workflow באמת מוצהר בקובץ. ‏workflow
   שקורא למודל שאיש לא הצהיר עליו הוא בדיוק המצב שהוליד את #261.
2. שערך מספרי נושא `source: measured`. ערך מנוחש שנראה כמו מדידה
   הוא גרוע מ-`unknown` — הוא מזמין להחליט לפיו.
3. ש-`billing_enabled` הוא `false` בכל הספקים. זו ההגנה של הבעלים מפני
   חיוב, והיא לא תשתנה בלי שמישהו יראה את זה ב-diff.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "tools" / "agents" / "providers.json")
                  .read_text(encoding="utf-8"))
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

MODEL_IN_URL = re.compile(r"/models/([A-Za-z0-9.\-]+):generateContent")


def _declared():
    out = {}
    for pname, p in DATA["providers"].items():
        for m in p.get("models", {}):
            out[m] = (pname, p)
    return out


def test_billing_is_off_everywhere():
    """הגנת הבעלים מפני חיוב. שינוי כאן חייב להיראות ב-diff."""
    for name, p in DATA["providers"].items():
        assert p.get("billing_enabled") is False, (
            f"{name}: billing_enabled אינו false — חריגה תעלה כסף")


def test_every_model_a_workflow_calls_is_declared():
    used = set()
    for wf in WORKFLOWS:
        used |= set(MODEL_IN_URL.findall(wf.read_text(encoding="utf-8")))
    assert used, "אף workflow אינו קורא למודל — הבדיקה לא רצה באמת"
    missing = sorted(used - set(_declared()))
    assert not missing, (
        f"מודלים שנקראים ואינם מוצהרים ב-providers.json: {missing}. "
        f"כלי שאינו יודע את המגבלה אינו יכול לכבד אותה — זה #261.")


def test_a_model_in_use_is_marked_as_such():
    """‏`in_use_by` חייב לשקף את המציאות, אחרת הוא מטעה."""
    used = {}
    for wf in WORKFLOWS:
        for m in MODEL_IN_URL.findall(wf.read_text(encoding="utf-8")):
            used.setdefault(m, set()).add(wf.stem)
    for model, wfs in used.items():
        declared = set(_declared()[model][1]["models"][model].get("in_use_by", []))
        assert wfs <= declared, (
            f"{model}: בשימוש ב-{sorted(wfs - declared)} ולא מוצהר שם")


@pytest.mark.parametrize("model", sorted(_declared()))
def test_numeric_limits_carry_a_source(model):
    spec = _declared()[model][1]["models"][model]
    numeric = [k for k in ("rpm", "rpd", "tpm", "tokens_per_day",
                           "neurons_per_day", "context")
               if spec.get(k) is not None]
    if not numeric:
        src = spec.get("source") or ""
        assert src in {"unknown", "n/a"} or src.startswith(
            ("owner-reported", "read-third-party-source")), (
            f"{model}: אין ערכים אך גם אין הצהרה מאיפה בא מה שכן ידוע")
        return
    # שלוש רמות ביטחון לגיטימיות — נמדד, דיווח-בעלים, ומקור-צד-שלישי
    # (עם תאריך). מה שנשאר אסור: מספר בלי שום מקור, שנראה כמו מדידה.
    src = spec.get("source") or ""
    ok = src == "measured" or src.startswith(
        ("owner-reported", "read-third-party-source"))
    assert ok, (
        f"{model}: יש ערכים מספריים ({numeric}) עם source={src!r}. "
        f"ערך מנוחש שנראה כמו מדידה מזמין להחליט לפיו.")


def test_the_model_actually_in_use_has_the_widest_daily_ceiling():
    """אם עברנו למודל בגלל התקרה היומית — שהבחירה תישאר נכונה.

    ה"בשימוש" נגזר מכתובות ה-API ב-workflows ולא משדה `in_use_by`
    ב-JSON. הגרסה הראשונה קראה את ה-JSON, ולכן החזרת ה-workflow
    למודל צר **לא הפילה אותה** — הטסט אישר את מה שהקובץ מצהיר,
    לא את מה שקורה.
    """
    gem = DATA["providers"]["gemini"]["models"]
    used = set()
    for wf in WORKFLOWS:
        used |= set(MODEL_IN_URL.findall(wf.read_text(encoding="utf-8")))
    in_use = sorted(used & set(gem))
    assert in_use, "אף workflow אינו קורא למודל Gemini מוצהר"
    best = max(gem, key=lambda m: gem[m].get("rpd") or 0)
    for m in in_use:
        assert gem[m].get("rpd") == gem[best].get("rpd"), (
            f"{m} בשימוש עם {gem[m].get('rpd')} בקשות ליום, בעוד ל-{best} "
            f"יש {gem[best].get('rpd')}. זו הסיבה שעברנו — ר' #261.")
