"""המניפסט מיוצר ממה שיש לו מקור, ו-CI מפיל drift.

‏providers.json נכתב ביד — כלומר מתיישן בשקט. ‏`in_use_by` נגזר
מהקריאות בפועל ב-workflows, ולכן הוא מיוצר; תקרות הן מדידות
מהקונסולה ואין להן מקור בריפו — הכלי אינו נוגע בהן, כי לייצר
מספר בלי מקור זו המצאה, לא אוטומציה.

הטסט האחרון הוא האכיפה: ‏drift אמיתי מאדים כל CI מעכשיו.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "agents" / "gen-manifest.py"

spec = importlib.util.spec_from_file_location("gen_manifest", SRC)
gm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gm)


def test_scan_reads_the_actual_calls(tmp_path):
    (tmp_path / "a.yml").write_text(
        "run: curl .../models/gemini-x:generateContent", encoding="utf-8")
    (tmp_path / "b.yml").write_text("run: echo no model", encoding="utf-8")
    assert gm.scan_usage(str(tmp_path)) == {"gemini-x": ["a"]}


def test_a_stale_in_use_by_is_drift():
    """חיובי ידוע: הרשימה בקובץ אומרת א', הקריאות אומרות ב'."""
    data = {"providers": {"gemini": {"models": {
        "gemini-x": {"in_use_by": ["old-workflow"], "rpd": 5}}}}}
    updated, drift = gm.apply(data, {"gemini-x": ["new-workflow"]})
    assert drift, "‏in_use_by מיושן לא זוהה — הגלאי לא עובד"
    assert updated["providers"]["gemini"]["models"]["gemini-x"][
        "in_use_by"] == ["new-workflow"]


def test_an_unregistered_model_in_use_is_the_worst_drift():
    """מודל שנקרא ואינו רשום — אין לו תקרה, ו-before-spend עיוור לו."""
    data = {"providers": {"gemini": {"models": {}}}}
    _, drift = gm.apply(data, {"gemini-y": ["some-workflow"]})
    assert drift and "אינו רשום" in drift[0]


def test_measured_fields_are_never_touched():
    """הקו המפריד: הכלי מעדכן in_use_by ולא נוגע במדידות."""
    data = {"providers": {"gemini": {"models": {
        "gemini-x": {"in_use_by": [], "rpd": 5, "rpm": 15,
                     "source": "measured"}}}}}
    updated, _ = gm.apply(data, {"gemini-x": ["w"]})
    m = updated["providers"]["gemini"]["models"]["gemini-x"]
    assert (m["rpd"], m["rpm"], m["source"]) == (5, 15, "measured")


def test_matching_state_is_not_drift():
    data = {"providers": {"gemini": {"models": {
        "gemini-x": {"in_use_by": ["w"], "rpd": 5}}}}}
    _, drift = gm.apply(data, {"gemini-x": ["w"]})
    assert drift == []


def test_the_real_repo_has_no_drift():
    """האכיפה: מהיום, שינוי מודל ב-workflow בלי עדכון המניפסט מאדים."""
    import json
    data = json.load(open(gm.PROVIDERS, encoding="utf-8"))
    usage = gm.scan_usage()
    assert usage, "אפס קריאות מודל נמצאו — הסורק כנראה שבור, לא הריפו נקי"
    _, drift = gm.apply(data, usage)
    assert drift == [], "‏drift במניפסט: %r" % drift
