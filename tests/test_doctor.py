"""‏doctor — הגלאי למחלקה שאף ריצה לא רואה.

שני חצאים, לפי הכלל: גלאי נבחן קודם מול **חיוביים ידועים** (קלט
סינתטי פגום שהוא חייב לתפוס), ורק אז ה"נקי" שלו על הריפו האמיתי
שווה משהו. בריצה הראשונה על הריפו הוא האשים שני קבצים תקינים —
‏false positive של allowlist חסרה — ולכן יש כאן גם בדיקות שלילה.

הטסט על הריפו האמיתי הוא האכיפה: הוא רץ תחת pytest בכל CI, ולכן
ל-doctor הסטטי אין דרך "לא לרוץ" — בניגוד למושא הבדיקה שלו.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "agents" / "doctor.py"

spec = importlib.util.spec_from_file_location("doctor", SRC)
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


def kinds(body):
    return [k for k, _ in doctor.check_text("t.yml", body)]


def test_unquoted_cron_is_caught():
    assert "cron-unquoted" in kinds(
        "on:\n  schedule:\n    - cron: 0 3 * * *\n")


def test_quoted_cron_is_clean():
    body = "on:\n  schedule:\n    - cron: '0 3 * * *'\n"
    assert "cron-unquoted" not in kinds(body)


def test_an_if_on_an_output_nobody_writes_is_caught():
    """התנאי תמיד false — וה-job מדולג בירוק לנצח. צורת ההמשך של #266."""
    body = ("on:\n  push:\n"
            "jobs:\n  a:\n    if: needs.gate.outputs.enabled == 'true'\n")
    assert "if-orphan-output" in kinds(body)


def test_an_output_that_is_written_is_clean():
    body = ("on:\n  push:\n"
            "jobs:\n  gate:\n    steps:\n"
            "      - run: echo \"enabled=true\" >> \"$GITHUB_OUTPUT\"\n"
            "  a:\n    if: needs.gate.outputs.enabled == 'true'\n")
    assert "if-orphan-output" not in kinds(body)


def test_a_workflow_with_no_firing_trigger_is_caught():
    assert "no-trigger" in kinds("name: x\njobs:\n  a:\n    steps: []\n")


def test_discussion_and_pull_request_target_are_valid_triggers():
    """שני ה-false positives מהריצה הראשונה — לא יחזרו."""
    assert "no-trigger" not in kinds("on:\n  discussion:\n    types: [created]\n")
    assert "no-trigger" not in kinds(
        "on:\n  pull_request_target:\n    types: [opened]\n")


def test_continue_on_error_is_reported():
    body = "on:\n  push:\n\njobs:\n  a:\n    continue-on-error: true\n"
    assert "continue-on-error" in kinds(body)


def test_the_real_repo_is_clean():
    """האכיפה עצמה: ממצא קשיח חדש ב-workflows יפיל את ה-CI כאן."""
    results = doctor.static_scan()
    hard = {n: [f for f in fs if f[0] != "continue-on-error"]
            for n, fs in results.items()}
    bad = {n: fs for n, fs in hard.items() if fs}
    assert not bad, "ממצאי doctor ב-workflows אמיתיים: %r" % bad
    # הסף אינו מספר קבוע: הוא **כל** קובץ workflow שקיים על הדיסק.
    # מספר קשיח נכון לריפו אחד בלבד, ומספיק שיירד קובץ כדי שהוא
    # יעבור בזמן שהגלאי דילג על חצי מהם. השוואה למה שקיים בפועל
    # תופסת גם את המקרה הזה וגם ריפו קטן יותר.
    on_disk = {p.name for p in
               (ROOT / ".github" / "workflows").glob("*.yml")}
    assert on_disk, "אין קבצי workflow כלל — הבדיקה אינה אומרת דבר"
    assert set(results) == on_disk, (
        "הגלאי סרק %r ועל הדיסק יש %r" % (sorted(results), sorted(on_disk)))
