"""‏limits-watch — ספק שמשנה את תנאי החינמי נתפס לפני הקיר.

הלוגיקה נבדקת על גוף דף סינתטי — בלי רשת, כי CI לא תלוי בזמינות
דפי ספקים. החיובי הידוע: עוגן שנעלם חייב לצאת changed.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "agents" / "limits-watch.py"

spec = importlib.util.spec_from_file_location("limits_watch", SRC)
lw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lw)


def test_anchor_present_is_same():
    r = lw.check("p", "http://x", [r"10,?000\s+Neurons"],
                 body="you get 10,000 Neurons per day")
    assert r["state"] == lw.SAME


def test_a_vanished_anchor_is_changed_and_loud():
    """החיובי הידוע: בדיוק מה שקרה עם Cerebras באוגוסט."""
    r = lw.check("p", "http://x", [r"10,?000\s+Neurons"],
                 body="pricing has moved to credits, see FAQ")
    assert r["state"] == lw.CHANGED
    assert "לבדוק" in r["detail"]


def test_every_fleet_provider_with_a_public_page_has_an_anchor():
    provs = {a[0] for a in lw.ANCHORS}
    for need in ("cloudflare", "gemini", "groq", "openrouter", "mistral"):
        assert need in provs, "‏%s בלי עוגן — שינוי אצלו יעבור בשקט" % need


def test_the_three_states_are_distinct():
    assert len({lw.SAME, lw.CHANGED, lw.NOCHK}) == 3
