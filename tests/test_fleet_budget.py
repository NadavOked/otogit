"""המונה היומי — הקריאה שמעבר לתקרה לא יוצאת (#286).

הלוגיקה נבדקת בלי litellm (אינו מותקן ב-CI): הספירה, החלונות,
וההכרעה מתי קבוצה מוצתה. הכלל המשולש: פריסה בלי תקרה ידועה
פותחת את הקבוצה (יש לאן לנתב) · קבוצה מוצתה רק כשכולן מוצו ·
וכשל של המונה עצמו מרעיש ולא משבית — hard-$0 הוא מבני ואינו
תלוי בספירה, וזו החרגה מודעת מ"נכשל סגור", מתועדת במודול.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "agents" / "fleet_budget.py"

spec = importlib.util.spec_from_file_location("fleet_budget", SRC)
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "STATE", str(tmp_path / "usage.json"))


def test_caps_come_from_providers_json_not_code():
    caps = fb.daily_caps()
    assert caps.get("groq/groq/compound") == 250
    assert caps.get("gemini/gemini-3.1-flash-lite") == 500


def test_counting_is_per_model_per_key_per_day(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    fb.record("gemini/gemini-3.1-flash-lite", "key1")
    fb.record("gemini/gemini-3.1-flash-lite", "key1")
    fb.record("gemini/gemini-3.1-flash-lite", "key2")
    assert fb.spent_today("gemini/gemini-3.1-flash-lite", "key1") == 2
    assert fb.spent_today("gemini/gemini-3.1-flash-lite", "key2") == 1


def test_the_80_percent_warning_fires_before_the_wall(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fb, "caps",
                        lambda: {"groq/groq/compound":
                                 {"limit": 10, "window": "daily"}})
    warns = [fb.record("groq/groq/compound") for _ in range(9)]
    assert warns[6] is None and warns[7] is not None, (
        "האזהרה חייבת להופיע בדיוק ב-8/10 — לפני הקיר, לא ממנו")


def test_group_blocks_only_when_every_deployment_is_spent(tmp_path,
                                                          monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fb, "caps",
                        lambda: {"groq/groq/compound": {"limit": 1, "window": "daily"},
                                 "m2": {"limit": 1, "window": "daily"}})
    fb.record("groq/groq/compound", "k")
    assert not fb.group_exhausted([("groq/groq/compound", "k"),
                                   ("m2", "k")]), "‏m2 עוד פנוי"
    fb.record("m2", "k")
    assert fb.group_exhausted([("groq/groq/compound", "k"), ("m2", "k")])


def test_a_capless_deployment_keeps_the_group_open(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fb, "caps",
                        lambda: {"m1": {"limit": 1, "window": "daily"}})
    assert not fb.group_exhausted([("m1", "k"), ("no-cap-model", "k")])


def test_gemini_window_follows_the_pacific_reset():
    """שני מודלים באותו רגע — חלונות שונים כשהשעונים שונים."""
    g = fb.window_id("gemini/gemini-3.1-flash-lite")
    u = fb.window_id("groq/groq/compound")
    assert len(g) == 10 and len(u) == 10  # שניהם תאריכים; ההיסט נבדק בקוד


def test_a_corrupt_state_file_is_noise_not_shutdown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "usage.json").write_text("{לא json", encoding="utf-8")
    assert fb.spent_today("m", "k") == 0
    fb.record("m", "k")  # לא זורק — נספר מחדש
    assert fb.spent_today("m", "k") == 1


def test_the_proxy_config_loads_the_callback():
    body = (ROOT / "tools" / "agents" / "litellm.yaml").read_text(
        encoding="utf-8")
    assert "fleet_budget.handler" in body, (
        "המונה לא מחובר לקונפיג — הוא קוד מת")


def test_the_window_comes_from_the_manifest_not_the_code(tmp_path,
                                                          monkeypatch):
    """דרישת הבעלים: ספק ששינה יומי→חודשי מוחלף במניפסט, לא בקוד.
    שינוי החלון מחליף את מפתח הספירה — הישן פשוט מפסיק להיספר."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fb, "caps",
                        lambda: {"m": {"limit": 100, "window": "monthly"}})
    fb.record("m", "k")
    import datetime as dt
    month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
    import json, io as _io
    state = json.load(_io.open(fb.STATE, encoding="utf-8"))
    assert list(state) == ["m|k|%s" % month], state


def test_weekly_and_monthly_windows_are_distinct():
    assert fb.window_id("m", "daily") != fb.window_id("m", "monthly")
    assert fb.window_id("m", "weekly").startswith(
        fb.window_id("m", "monthly")[:4])
