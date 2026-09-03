"""שלושת החורים במונה התקציב — כל אחד וההוכחה שהוא סגור.

המונה נבנה ב-#286 כדי שקריאה מעבר לתקרה לא תצא. במדידה ב-03/09
התברר שהוא סופר **ארבע פריסות מתוך עשר**, סופר את היחידה הלא-נכונה,
ואי-אפשר בכלל לקרוא אותו:

‏(א) ‏`caps()` הייתה **רשימה ידנית** בקוד. ‏NIM, ‏Mistral, ‏OpenRouter
    ו-`compound-mini` לא הופיעו בה — ולכן `group_exhausted` ראה אותם
    כ"פריסה בלי תקרה = יש לאן לנתב" ופתח את הקבוצה תמיד. **"לא
    נספר" ו"אין לו תקרה" הם שני מצבים שונים** (עיקרון 5), והם היו
    מקופלים לאחד ובלתי נראים.

‏(ב) נספרו **בקשות בלבד**. ל-flash-lite יש `tpm: 250000`, וקריאה
    אחת שנמדדה שקלה 10,208 טוקנים — כלומר מונה בקשות מדווח "רחוק
    מהקיר" עד הרגע שבו נחסמים.

‏(ג) **לא היה CLI.** ‏`--report` ו-`--help` החזירו אפס פלט. המסירה
    קבעה שכשל המונה "מרעיש ולא משבית" — אבל מונה שאיש אינו יכול
    לקרוא אינו שונה בהרבה ממונה שאינו רץ.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "agents" / "fleet_budget.py"
CLI = ROOT / "tools" / "agents" / "fleet-report.py"

spec = importlib.util.spec_from_file_location("fleet_budget", SRC)
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "STATE", str(tmp_path / "usage.json"))


def _fake_fleet(tmp_path, monkeypatch, model_line, provider_block):
    """מניפסט וקונפיג מזויפים — כדי לבדוק את הגזירה עצמה."""
    (tmp_path / "litellm.yaml").write_text(
        "model_list:\n  - model_name: g\n    litellm_params:\n"
        "      model: %s\n" % model_line, encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({
        "providers": provider_block,
        "free_fleet": {"litellm_prefix_to_provider": {"acme": "acme"}},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(fb, "YAML", str(tmp_path / "litellm.yaml"))
    monkeypatch.setattr(fb, "PROVIDERS", str(tmp_path / "providers.json"))


def run_cli(*args):
    return subprocess.run([sys.executable, str(CLI)] + list(args),
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=120, stdin=subprocess.DEVNULL)


# ---- (א) שום פריסה אינה נעלמת בשקט --------------------------------

def test_every_deployed_model_is_either_capped_or_declared_uncounted():
    """הטענה המרכזית: כל מודל בקונפיג מופיע באחת משתי הרשימות.
    פריסה שאינה באף אחת מהן היא בדיוק החור — היא לא נספרת ואיש
    אינו יודע זאת."""
    covered = set(fb.caps()) | {m for m, _ in fb.uncounted()}
    missing = sorted(set(fb.deployed_models()) - covered)
    assert not missing, "פריסות שנעלמו מהמונה ומהדוח כאחד: %s" % missing


def test_the_uncounted_list_is_not_empty_and_says_why():
    """אם הרשימה ריקה — או שכל התקרות ידועות (ואז לעדכן את הטסט),
    או שהגלאי שבור. ריק בשקט הוא בדיוק מה שהיה כאן קודם."""
    unc = fb.uncounted()
    assert unc, ("אין אף פריסה לא-נאכפת — בדוק שהגלאי עובד לפני "
                 "שמאמינים לזה")
    for model, why in unc:
        assert why.strip(), "%s ברשימה בלי סיבה" % model


def test_every_deployed_model_is_declared_in_the_manifest():
    """סחף בין הקונפיג למניפסט: ‏`deepseek-v4-pro` היה מוצהר בזמן
    ש-`deepseek-ai/deepseek-v4-pro-0813` נפרס, ו-`compound-mini` לא
    היה מוצהר כלל. שניהם נראו למונה כמודלים שאינם קיימים."""
    man = fb._manifest()
    undeclared = [m for m in fb.deployed_models()
                  if fb._spec_for(m, man)[0] is None]
    assert not undeclared, (
        "מודלים שנפרסים ואינם מוצהרים ב-providers.json: %s. כלי שאינו "
        "יודע שהמודל קיים אינו יכול לספור אותו." % undeclared)


def test_a_new_limit_in_the_manifest_is_enforced_without_a_code_change(
        tmp_path, monkeypatch):
    """הדרישה שמאחורי החור: ‏`caps()` הייתה קוד, ולכן `rpd` שהבעלים
    יוסיף ל-mistral לא היה משנה דבר."""
    _fake_fleet(tmp_path, monkeypatch, "acme/thing",
                {"acme": {"models": {"thing": {}}}})
    assert "acme/thing" not in fb.caps()
    assert ("acme/thing", ) in [(m, ) for m, _ in fb.uncounted()]
    _fake_fleet(tmp_path, monkeypatch, "acme/thing",
                {"acme": {"models": {"thing": {"rpd": 7}}}})
    assert fb.caps()["acme/thing"]["limit"] == 7, (
        "‏rpd שנוסף למניפסט לא נאכף — התקרות עדיין בקוד")


def test_an_unmapped_prefix_is_reported_not_assumed_limitless(
        tmp_path, monkeypatch):
    _fake_fleet(tmp_path, monkeypatch, "whoisthis/x",
                {"acme": {"models": {}}})
    why = dict(fb.uncounted()).get("whoisthis/x", "")
    assert "מיפוי" in why, why


# ---- (ב) טוקנים, לא רק בקשות ---------------------------------------

def test_tokens_are_recorded_alongside_requests(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    fb.record("m", "k", 10208)
    fb.record("m", "k", 300)
    assert fb.spent_today("m", "k") == 2
    assert fb.tokens_today("m", "k") == 10508, (
        "טוקנים לא נספרו — המונה סופר את היחידה הלא-נכונה")


def test_a_token_ceiling_blocks_on_tokens_not_on_call_count(tmp_path,
                                                            monkeypatch):
    """שתי קריאות בלבד — ותקרת טוקנים שנחצתה. מונה בקשות היה מדווח
    ‏2/500 ומרשה להמשיך."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fb, "caps", lambda: {
        "m": {"limit": 20000, "window": "daily", "unit": "tokens"}})
    fb.record("m", "k", 10208)
    assert not fb.group_exhausted([("m", "k")])
    fb.record("m", "k", 10208)
    assert fb.group_exhausted([("m", "k")]), (
        "‏20,416 טוקנים מתוך 20,000 ועוד עוברים — התקרה נספרת בבקשות")


def test_the_80_percent_warning_counts_tokens_when_that_is_the_unit(
        tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fb, "caps", lambda: {
        "m": {"limit": 1000, "window": "daily", "unit": "tokens"}})
    assert fb.record("m", "k", 700) is None
    assert fb.record("m", "k", 200) is not None, "‏900/1000 בלי אזהרה"


def test_an_old_integer_state_file_still_counts(tmp_path, monkeypatch):
    """שדרוג שמאפס מונים הוא שדרוג שמסתיר חריגה."""
    _isolate(tmp_path, monkeypatch)
    key = "m|k|%s" % fb.window_id("m", "daily")
    (tmp_path / "usage.json").write_text(json.dumps({key: 5}),
                                         encoding="utf-8")
    assert fb.spent_today("m", "k") == 5
    fb.record("m", "k", 100)
    assert fb.spent_today("m", "k") == 6
    assert fb.tokens_today("m", "k") == 100


def test_an_undeclared_token_count_reads_as_zero_not_as_cheap(tmp_path,
                                                              monkeypatch):
    """ספק שאינו מדווח usage משאיר 0 — וזה נקרא בדוח כ'לא דווח'."""
    _isolate(tmp_path, monkeypatch)
    fb.record("m", "k")
    assert fb.tokens_today("m", "k") == 0


# ---- (ג) אפשר לקרוא את המונה ---------------------------------------

def test_the_report_prints_both_halves():
    p = run_cli("--report")
    assert p.returncode == 0, p.stderr
    assert "נספר בחלון הנוכחי" in p.stdout
    assert "אינו נאכף" in p.stdout, (
        "הדוח אינו מציג את מה שאינו נאכף — זה החצי החשוב")


def test_the_uncounted_flag_lists_deployments_with_reasons():
    p = run_cli("--uncounted")
    assert p.returncode == 0, p.stderr
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    assert lines, "אין פלט"
    for line in lines:
        assert "\t" in line, "שורה בלי סיבה: %r" % line


def test_bare_invocation_prints_help_instead_of_nothing():
    """זה החור עצמו: פקודה שמחזירה אפס פלט נראית כמו הצלחה שקטה."""
    p = run_cli()
    assert p.returncode == 0
    assert p.stdout.strip(), "אפס פלט — בדיוק המצב שהטסט הזה נועד למנוע"
    assert "--report" in p.stdout


def test_help_is_not_silent():
    p = run_cli("--help")
    assert p.returncode == 0 and "--uncounted" in p.stdout


def test_running_the_library_directly_says_so_and_fails():
    """‏`python fleet_budget.py --report` החזיר אפס פלט ויציאה 0 —
    כלומר נראה כאילו עבד."""
    p = subprocess.run([sys.executable, str(SRC), "--report"],
                       capture_output=True, timeout=120,
                       stdin=subprocess.DEVNULL)
    assert p.returncode != 0, "יצא 0 בלי לעשות דבר"
    both = p.stdout + p.stderr
    assert b"Traceback" not in both, (
        "התרסקות אינה הסבר — כנראה עברית ב-stderr של cp1252:\n%s"
        % both.decode("utf-8", "replace"))
    both.decode("ascii")          # נכשל אם נכתבו בתים לא-ASCII
    assert b"fleet-report.py" in both, "לא מפנה לכלי"
