"""‏`resolve.py` מרכיב שתי שכבות, ונכשל סגור.

הכלל: סוכן קורא כללי + ספציפי, והספציפי גובר. הטסט שומר על שלושה
דברים שקל לאבד בשקט: שהדריסה **מדווחת**, שפרויקט חסר הוא **שגיאה**
ולא רשימה ריקה, ושספרייה שאינה קיימת נבדלת מספרייה ריקה.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESOLVE = ROOT / "tools" / "resolve.py"


def _run(args, cwd=None, expect_ok=True):
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, str(RESOLVE)] + args,
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=60, env=e, stdin=subprocess.DEVNULL,
                       cwd=str(cwd or ROOT))
    if expect_ok:
        assert p.returncode == 0, f"יצא {p.returncode}: {p.stderr[:300]}"
    return p


def test_the_tool_runs_and_lists_projects():
    out = _run(["--list"]).stdout
    assert out.strip(), "רשימת פרויקטים ריקה — הבדיקה לא רצה באמת"


def test_a_missing_project_is_an_error_not_an_empty_result():
    """'אין לו כלום' ו'אין לו תיקייה' הם שני מצבים שונים."""
    p = _run(["--project", "לא-קיים-בכלל"], expect_ok=False)
    assert p.returncode != 0, "פרויקט חסר החזיר הצלחה"
    assert "שגיאה" in (p.stderr + p.stdout)


def test_both_layers_are_reported_separately():
    proj = _run(["--list"]).stdout.split()[0]
    d = json.loads(_run(["--project", proj, "--json"]).stdout)
    for kind in ("agents", "skills", "knowledge"):
        assert kind in d["kinds"], f"חסרה קטגוריה {kind}"
        k = d["kinds"][kind]
        for f in ("general", "project", "effective"):
            assert f in k, f"{kind}: חסר {f}"


def test_the_project_layer_wins_and_the_override_is_reported(tmp_path):
    """דריסה שקטה היא הדרך לקבל חוק בלי לדעת שהוחלף."""
    for d in ("knowledge", "projects/p/knowledge", "tools"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "knowledge" / "x.md").write_text("כללי", encoding="utf-8")
    (tmp_path / "projects" / "p" / "knowledge" / "x.md").write_text(
        "ספציפי", encoding="utf-8")
    (tmp_path / "tools" / "resolve.py").write_text(
        RESOLVE.read_text(encoding="utf-8"), encoding="utf-8")
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, str(tmp_path / "tools" / "resolve.py"),
                        "--project", "p", "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=60, env=e, stdin=subprocess.DEVNULL)
    assert p.returncode == 0, p.stderr[:300]
    d = json.loads(p.stdout)
    eff = d["kinds"]["knowledge"]["effective"]
    hit = [e2 for e2 in eff if e2["name"] == "x.md"]
    assert hit, "הקובץ נעלם מהתוצאה"
    assert "projects/p" in hit[0]["path"], "השכבה הכללית גברה — הפוך"
    assert "knowledge/x.md" in d["overrides"], "הדריסה לא דווחה"


def test_a_directory_that_does_not_exist_is_named():
    proj = _run(["--list"]).stdout.split()[0]
    d = json.loads(_run(["--project", proj, "--json"]).stdout)
    assert isinstance(d["missing"], list)
