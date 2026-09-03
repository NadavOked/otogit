"""‏`routing.order` אוכף בפועל — לא מוצהר.

הכלל של הבעלים (02/09): משימה הולכת לשכבה הראשונה שמסוגלת לה ויורדת
ברשימה רק כשהיא **אינה מסוגלת**, לא כשנוח יותר. בלילה שאחריו נשרפו
~65K טוקנים של Codex על טריאז' וסיווג. הטסטים כאן שומרים על ההפרש
בין הכלל לבין מה שקורה.

כמו ב-test_guard_bash: הכלי מורץ כ**תהליך**, מול stdin, בדיוק כפי
שה-harness מריץ אותו. מה שנבדק הוא החוזה — קוד היציאה והפלט — כי זה
מה שקובע אם הפקודה תרוץ, ולא האם הפונקציה הפנימית מחזירה את הדבר
הנכון.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "agents" / "route-task.py"
PROVIDERS = ROOT / "tools" / "agents" / "providers.json"

ALLOW, REFUSE, USAGE = 0, 1, 2


def run(*args):
    return subprocess.run([sys.executable, str(TOOL)] + list(args),
                          input="", capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def hook(command):
    """מריץ את מצב ה-hook ומחזיר את ההחלטה, או None (=מותר)."""
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": command}})
    p = subprocess.run([sys.executable, str(TOOL), "--hook"], input=payload,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, "‏hook שיוצא לא-אפס אינו נקרא כהחלטה"
    out = (p.stdout or "").strip()
    return json.loads(out)["hookSpecificOutput"] if out else None


# ---- הפסיקה עצמה ---------------------------------------------------

REFUSED = [
    "triage the open issues and label them bug or enhancement",
    "classify these 40 issues into buckets",
    "לסווג 40 issues לתוויות",
    "please relabel the backlog",
]


@pytest.mark.parametrize("task", REFUSED)
def test_a_declared_low_tier_task_is_refused_to_a_high_tier(task):
    p = run("--task", task, "--tier", "codex_or_grok")
    assert p.returncode == REFUSE, (
        "‏%r עבר ל-codex_or_grok. זו בדיוק ההפרה שנמדדה בלילה של "
        "02/09: ‏65K טוקנים על עבודה ש-ollama מצהיר עליה.\n%s"
        % (task, p.stdout))
    assert "route-verdict: refuse" in p.stdout
    assert "ollama" in p.stdout, "סירוב שאינו אומר לאן ללכת אינו שימושי"


def test_the_same_task_is_allowed_to_the_tier_that_declares_it():
    """הכלל אינו 'תמיד לסרב' — הוא 'לא לעלות מעל המסוגל'."""
    p = run("--task", "classify these issues", "--tier", "ollama")
    assert p.returncode == ALLOW, p.stdout
    assert "route-verdict: allow" in p.stdout


def test_work_that_must_stay_on_the_subscription_is_never_pushed_down():
    """‏never_delegate_down מגן מפני הנזק ההפוך — מנגנון שדוחף ניפוי
    או מיזוג למודל 3B."""
    p = run("--task", "classify these issues but debug the root cause",
            "--tier", "codex_or_grok")
    assert p.returncode == ALLOW, p.stdout
    assert "never_delegate_down" in p.stdout


def test_a_label_name_is_not_a_veto_word():
    """בקרה על הבאג שנמדד בטיוטה: ‏'bug' ברשימת הווטו הפך את המשימה
    'תייג issues כ-bug או enhancement' ל-allow — שם של תווית ביטל
    את הסירוב. מילת וטו מעידה על אופי העבודה, לא על תוכנה."""
    data = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    words = []
    for k, v in data["routing"]["never_delegate_down"].items():
        if not k.startswith("_"):
            words.extend(w.lower() for w in v)
    for banned in ("bug", "fix", "issue", "label", "task"):
        assert banned not in words, (
            "‏%r ברשימת הווטו — הוא מופיע כתוכן של משימות תיוג "
            "ויבטל כל סירוב" % banned)


def test_no_evidence_is_reported_as_itself_and_not_as_approval():
    """עיקרון 5: "לא נבדק" אינו "נבדק ותקין". הפלט חייב לומר זאת."""
    p = run("--task", "refactor the wave logic in the sender",
            "--tier", "codex_or_grok")
    assert p.returncode == ALLOW
    assert "route-verdict: no-evidence" in p.stdout
    assert "לא נבדק" in p.stdout, (
        "מסלול חוסר-הראיה מוצג כ-allow בלי לומר שהוא לא נבדק")


def test_an_unknown_tier_is_a_usage_error_not_a_silent_pass():
    p = run("--task", "classify things", "--tier", "gpt9")
    assert p.returncode == USAGE, "שכבה לא מוכרת עברה בשקט"


# ---- מצב ה-hook: האכיפה בפועל --------------------------------------

def test_the_hook_denies_a_high_tier_call_for_low_tier_work():
    d = hook('codex exec "triage the backlog and label each issue"')
    assert d is not None, "הקריאה הייתה רצה — זה הכסף שנשרף"
    assert d["permissionDecision"] == "deny"
    assert d["permissionDecisionReason"].strip()


def test_the_hook_output_is_ascii_only():
    """‏stdout של ווינדוס הוא cp1252. הגרסה הראשונה של guard-bash מתה
    בדיוק כאן — הלוגיקה עבדה והכתיבה קרסה, כלומר לא נחסם דבר."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {
        "command": 'codex exec "classify and label the issues"'}})
    p = subprocess.run([sys.executable, str(TOOL), "--hook"],
                       input=payload.encode("utf-8"), capture_output=True,
                       timeout=60)
    assert p.stdout.strip(), "לא יצאה החלטה"
    p.stdout.decode("ascii")            # נכשל אם נכתבו בתים לא-ASCII


MENTIONS = [
    'git commit -m "codex burned tokens on triage and labelling"',
    'grep -rn "triage" tools/agents/',
    'python -m pytest tests -q',
    'echo "classify" > notes.txt',
]


@pytest.mark.parametrize("command", MENTIONS)
def test_mentioning_an_agent_is_not_calling_it(command):
    """הריפו הזה **כותב** על codex ועל grok. שומר שנחסם על אזכור
    בהודעת קומיט הוא שומר שמכבים אחרי יומיים."""
    assert hook(command) is None, "‏%r נחסם — זה אזכור, לא קריאה" % command


def test_a_piped_call_is_still_a_call():
    assert hook('echo x | codex exec "label the issues"') is not None


@pytest.mark.parametrize("stdin_text", [
    "not json at all", "", "{}", '{"tool_input": {}}',
    '{"tool_input": {"command": 42}}',
])
def test_the_hook_fails_open_on_garbage(stdin_text):
    """**בכוונה הפוך מ-guard-bash.** שם ספק = חסימה, כי המחיר הוא
    דיסק מחוק. כאן הגַּיְס רץ על כל פקודת מעטפת, וחסימה על ספק הייתה
    עוצרת את העבודה כולה. הקביעה שדורשת ראיה כאן היא ה**סירוב**."""
    p = subprocess.run([sys.executable, str(TOOL), "--hook"],
                       input=stdin_text, capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0
    assert not (p.stdout or "").strip(), "קלט לא מובן חסם עבודה לגיטימית"


def test_the_hook_is_actually_registered():
    """כלי שאינו רשום אינו רץ — אותו לקח כמו ב-test_guard_bash."""
    settings = json.loads((ROOT / ".claude" / "settings.json")
                          .read_text(encoding="utf-8"))
    commands = [h["command"]
                for e in settings["hooks"]["PreToolUse"]
                if e.get("matcher") == "Bash"
                for h in e["hooks"] if h.get("type") == "command"]
    assert any("route-task.py" in c and "--hook" in c for c in commands), (
        "‏route-task אינו רשום כ-hook — הקובץ קיים ושום דבר אינו קורא "
        "לו, וזה מחזיר אותנו בדיוק ל'הסדר קיים כמסמך'")


def test_the_order_and_its_inputs_live_in_the_manifest_not_in_code():
    """הכרעה של הבעלים משתנה בקובץ, לא ב-if."""
    src = TOOL.read_text(encoding="utf-8")
    data = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    for tier in data["routing"]["order"]:
        assert '"%s"' % tier not in src and "'%s'" % tier not in src, (
            "שם השכבה %r מקודד ב-route-task.py — הסדר חייב להיקרא "
            "מ-providers.json" % tier)
    for key in ("task_kinds", "never_delegate_down", "tier_commands"):
        assert key in data["routing"], "‏routing.%s נעלם מהמניפסט" % key
