"""‏`guard-bash.py` חוסם בפועל, ונכשל סגור.

הטסט מריץ את השומר כתהליך אמיתי מול stdin, כפי שה-harness מריץ אותו —
ולא מייבא את הפונקציות. מה שנבדק הוא **החוזה**: מה נכתב ל-stdout,
כי זה מה שקובע אם הפקודה תרוץ.

הבדיקה של הפלט חשובה במיוחד כאן: בגרסה הראשונה השומר זיהה נכון כל
פקודה הרסנית, אבל `json.dump` ל-stdout של ווינדוס (cp1252) קרס על
העברית שבהסבר — **וגם מטפל הקריסה קרס**. כלומר השומר מת בלי לחסום,
בזמן שהלוגיקה שלו הייתה נכונה לחלוטין. לכן לא נבדק "האם הדפוס תואם"
אלא "האם יצאה החלטת deny תקינה".
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / "tools" / "agents" / "guard-bash.py"

BLOCKED = [
    "mkfs.ext4 /dev/sda1",
    "wipefs -a /dev/nvme0n1",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "sgdisk -Z /dev/sda",
    "gh repo delete owner/repo",
    "gh secret set OTOGIT_TOKEN --body x",
    "gh auth token",
    "git push --force origin main",
    "git push origin --delete v0.18.0",
    "schtasks /Delete /TN AgentRunner /F",
]

ALLOWED = [
    "ls -la",
    "git status",
    "git push origin feat/some-branch",
    "python -m pytest tests -q",
    "gh pr list --repo owner/repo",
    "grep -rn foo tools/",
    "rm -rf build/",
]


def _run(stdin_text):
    """מריץ את השומר ומחזיר (returncode, ההחלטה או None)."""
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin_text, capture_output=True, text=True,
        encoding="utf-8", timeout=30,
    )
    out = (proc.stdout or "").strip()
    if not out:
        return proc.returncode, None
    return proc.returncode, json.loads(out)["hookSpecificOutput"]


def _payload(command):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


@pytest.mark.parametrize("command", BLOCKED)
def test_destructive_commands_are_denied(command):
    code, decision = _run(_payload(command))
    assert code == 0, "השומר חייב לצאת 0 — קוד אחר אינו נקרא כהחלטה"
    assert decision is not None, f"{command!r} עבר בלי החלטה — הפקודה הייתה רצה"
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"].strip(), "חסימה בלי נימוק"


@pytest.mark.parametrize("command", ALLOWED)
def test_ordinary_commands_pass(command):
    code, decision = _run(_payload(command))
    assert code == 0
    assert decision is None, f"{command!r} נחסם בטעות: {decision}"


@pytest.mark.parametrize("stdin_text", [
    "not json at all",
    "",
    "{}",
    '{"tool_input": {}}',
    '{"tool_input": null}',
    '{"tool_input": {"command": 42}}',
])
def test_the_guard_fails_closed(stdin_text):
    """קלט שהשומר אינו מבין = חסימה. 'לא הצלחנו לבדוק' אינו אישור."""
    code, decision = _run(stdin_text)
    assert code == 0
    assert decision is not None, "קלט לא תקין עבר — זה כשל שנראה כמו הצלחה"
    assert decision["permissionDecision"] == "deny"


def test_the_reason_survives_a_non_utf8_stdout():
    """הפלט חייב להיות ASCII נקי — זה הבאג שהפיל את הגרסה הראשונה."""
    code, decision = _run(_payload("mkfs.ext4 /dev/sda1"))
    assert decision is not None
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=_payload("mkfs.ext4 /dev/sda1").encode("utf-8"),
        capture_output=True, timeout=30,
    )
    proc.stdout.decode("ascii")   # נכשל אם נכתבו בתים לא-ASCII


def test_the_hook_is_actually_registered():
    """שומר שאינו רשום ב-settings.json אינו רץ, וזה בדיוק #198 שוב."""
    settings = json.loads(
        (GUARD.parent.parent.parent / ".claude" / "settings.json")
        .read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    commands = [h["command"] for e in entries if e.get("matcher") == "Bash"
                for h in e["hooks"] if h.get("type") == "command"]
    assert any("guard-bash.py" in c for c in commands), \
        "ה-hook אינו רשום — הקובץ קיים אבל שום דבר אינו קורא לו"


# --- הדפוסים הספציפיים לאתר ---------------------------------------
#
# כתובת מעבדה ושם קובץ מפתח שונים בכל פרויקט, ולכן הם אינם בקוד אלא
# ב-OTOGIT_SITE_DENY. שני הכיוונים נבדקים: **בלי** המשתנה הפקודה
# עוברת, ו**איתו** היא נחסמת. בדיקה של כיוון אחד בלבד אינה מוכיחה
# שהמנגנון עובד — היא מוכיחה רק שמשהו קרה.

SITE_CMD = "ssh -i /c/lab/site_key root@198.51.100.8 uptime"
SITE_DENY = "site_key|מפתח האתר — גישה שמורה למתאם"


def _run_env(stdin_text, env_extra):
    import os
    env = dict(os.environ); env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(GUARD)], input=stdin_text,
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env)
    out = (proc.stdout or "").strip()
    return proc.returncode, (json.loads(out) if out else None)


def test_site_pattern_blocks_only_when_configured():
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": SITE_CMD}})
    _, without = _run_env(payload, {"OTOGIT_SITE_DENY": ""})
    assert without is None, "בלי OTOGIT_SITE_DENY הפקודה נחסמה — הדפוס דלף לקוד"
    _, with_ = _run_env(payload, {"OTOGIT_SITE_DENY": SITE_DENY})
    assert with_ is not None, "OTOGIT_SITE_DENY מוגדר והפקודה לא נחסמה"
    assert with_["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_malformed_site_deny_fails_closed():
    """שורה בלי '|' היא תקלת הגדרה. השומר עוצר, לא מתעלם בשקט."""
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "ls -la"}})
    rc, _ = _run_env(payload, {"OTOGIT_SITE_DENY": "בלי מפריד"})
    assert rc == 2, f"הגדרה שבורה לא עצרה את השומר (rc={rc})"
