"""השער שבין "הסוכן סיים" ל"נפתח PR" — שלושה פסקי-דין, לא שניים.

‏--unverified היה שדה טקסט: הסוכן כותב מה שהוא רוצה, ואיש אינו
בודק שהראיות באמת רצו. השער הופך את זה לפסק-דין מכונה — והצד
שאי-אפשר להשתיק יושב ב-pr-gate.yml, שצובע אדום כל PR של סוכן
בלי פסק-דין תקף.

ההבחנה המשולשת היא הפואנטה: קיפול "לא רץ" ל-fail מזמין עקיפה,
וקיפולו ל-pass הוא שקר. ‏insufficient_evidence הוא שם למצב עצמו.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "tools" / "agents" / "gate-pr.sh"
VERDICT = ROOT / "tools" / "agents" / "gate_verdict.py"
WF = ROOT / ".github" / "workflows" / "pr-gate.yml"

BASH = shutil.which("bash")


def run_gate(*args):
    assert BASH, "אין bash — כשל סביבה, לא דילוג"
    return subprocess.run(
        [BASH, str(GATE), *args], capture_output=True, text=True,
        encoding="utf-8", timeout=120, stdin=subprocess.DEVNULL)


def verdict_of(text):
    p = subprocess.run([sys.executable, str(VERDICT)], input=text,
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=60, stdin=None)
    return p.returncode


def test_green_evidence_yields_pass():
    p = run_gate("--evidence-cmd", "true", "--unverified", "כלום")
    assert p.returncode == 0 and "gate-verdict: pass" in p.stdout


def test_failed_evidence_yields_no_body_at_all():
    """‏fail אינו מוטבע — הוא עוצר: אין body, אין PR."""
    p = run_gate("--evidence-cmd", "false", "--unverified", "כלום")
    assert p.returncode == 1
    assert p.stdout.strip() == "", "על fail אסור שיהיה body בכלל"
    assert "fail" in p.stderr


def test_a_command_that_cannot_run_is_not_a_fail_and_not_a_pass():
    """‏exit 127: הבדיקה לא רצה. לא אישור ולא כישלון של הקוד."""
    p = run_gate("--evidence-cmd", "no-such-command-xyz",
                 "--unverified", "כלום")
    assert p.returncode == 0
    assert "gate-verdict: insufficient_evidence" in p.stdout


def test_missing_unverified_refuses_like_task_log():
    p = run_gate("--evidence-cmd", "true")
    assert p.returncode == 2 and "unverified" in p.stderr


def test_the_verdict_reader_maps_all_three_states():
    assert verdict_of("gate-verdict: pass\n") == 0
    assert verdict_of("gate-verdict: insufficient_evidence\n") == 2
    assert verdict_of("gate-verdict: fail\n") == 1


def test_a_missing_or_unknown_verdict_is_red():
    """סוכן שדילג על השער — או המציא פסק-דין — נתפס כאן."""
    assert verdict_of("סתם body בלי פסק-דין\n") == 1
    assert verdict_of("gate-verdict: totally-fine\n") == 1


def test_the_gate_output_parses_by_the_gate_reader():
    """שני הצדדים חייבים לדבר אותו פורמט — נבדק על הפלט האמיתי."""
    p = run_gate("--evidence-cmd", "true", "--unverified", "כלום")
    assert verdict_of(p.stdout) == 0


def test_the_workflow_enforces_on_agent_branches():
    body = WF.read_text(encoding="utf-8")
    assert "startsWith(github.head_ref, 'auto/')" in body
    assert "gate_verdict.py" in body
    i = body.index('"$code" -eq 2')
    seg = body[i:i + 600]
    assert "gate:insufficient-evidence" in seg and "exit 0" in seg, (
        "‏insufficient חייב תווית+תגובה ולא אדום — ולא ירוק שקט")
    assert "exit 1" in body[body.index("::error::"):], (
        "פסק-דין חסר חייב להאדים")
