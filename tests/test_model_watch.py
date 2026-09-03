"""‏model-watch — ספק חינמי מחליף מודלים בלי לשאול.

ביום החיבור זה קרה פעמיים: ‏groq/compound בשם אחר, ו-llama-3.1-8b
של Cloudflare מת חודשים לפני שמישהו שם לב. הכלי משווה את הקונפיג
לקטלוג החי; הטסטים כאן בודקים את הלוגיקה על נתונים מזויפים —
בלי רשת ובלי מפתחות, כי CI לא מחזיק אותם.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "agents" / "model-watch.py"

spec = importlib.util.spec_from_file_location("model_watch", SRC)
mw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mw)


def test_configured_reads_every_deployment():
    got = mw.configured()
    assert len(got) >= 6, "‏%d בלבד — הסורק כנראה שבור" % len(got)
    assert all(len(t) == 2 for t in got)


def test_a_model_missing_from_the_catalog_is_gone(monkeypatch):
    """החיובי הידוע: בדיוק המקרה של llama-3.1-8b."""
    monkeypatch.setattr(mw, "configured",
                        lambda: [("groq", "dead-model"), ("groq", "live")])
    monkeypatch.setattr(mw, "catalog", lambda p: {"live"})
    states = {r["model"]: r["state"] for r in mw.scan()}
    assert states == {"dead-model": mw.GONE, "live": mw.OK}


def test_an_unqueryable_catalog_is_not_ok_and_not_gone(monkeypatch):
    """‏"לא שאלנו" אינו "קיים" ואינו "נעלם" — עיקרון 5."""
    monkeypatch.setattr(mw, "configured", lambda: [("groq", "m")])
    monkeypatch.setattr(mw, "catalog", lambda p: None)
    assert mw.scan()[0]["state"] == mw.NOCHK


def test_the_three_states_are_distinct():
    assert len({mw.OK, mw.GONE, mw.NOCHK}) == 3


def test_no_secret_value_can_reach_the_output(monkeypatch):
    """הכלי קורא מפתחות; הפלט לעולם לא מכיל אותם."""
    import json
    secret = "SECRETVALUE" + "x" * 40
    monkeypatch.setenv("GROQ_API_KEY", secret)
    monkeypatch.setattr(mw, "configured", lambda: [("groq", "m")])
    monkeypatch.setattr(mw, "catalog", lambda p: None)
    blob = json.dumps(mw.scan(), ensure_ascii=False)
    assert secret not in blob and secret[:12] not in blob
