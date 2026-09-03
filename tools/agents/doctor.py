#!/usr/bin/env python3
"""גלאי למחלקת הכשל שאף ריצה לא רואה.

**הבעיה.** ‏workflow שמוגדר לא נכון לא נכשל — הוא **לא רץ**. אין
שגיאה, אין אדום, אין כלום בלשונית Actions. ‏`agent-daily` ישב כך
עם אפס ריצות אי-פעם, והתגלה במקרה. ריצה אדומה היא אות; היעדר
ריצה הוא שקט שנראה כמו שלום.

**שני חלקים:**

- **סטטי** — קורא את קובצי ה-workflow כטקסט (בכוונה בלי `yaml`,
  שאינו מותקן ב-CI): ‏cron מצוטט, כל `if:` שמפנה ל-output מפנה
  לאחד שקיים, לכל workflow יש טריגר, ו-`continue-on-error`
  מדווח. רץ תחת pytest בכל CI — ולכן אין לו איך "לא לרוץ".
- **דינמי** (`--runs`) — שואל את GitHub מתי כל workflow רץ
  לאחרונה. שלושה מצבים ולא שניים: ‏ran / **never-ran** /
  ‏could-not-check. "לא הצלחנו לבדוק" אינו "רץ" (עיקרון 5).

    python tools/agents/doctor.py            # סטטי בלבד
    python tools/agents/doctor.py --runs     # + שאילתת ריצות
"""
import argparse
import json
import os
import re
import subprocess
import sys

WF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "..", ".github", "workflows")

# הריצה הראשונה על הריפו האמיתי החזירה שני false positives —
# ‏discussion ו-pull_request_target חסרו. גלאי שמאשימים אותו על לא
# עוול חייב תיקון לפני שסומכים על ה"נקי" שלו.
FIRING_TRIGGERS = ("push", "pull_request", "pull_request_target", "schedule",
                   "workflow_dispatch", "workflow_run", "workflow_call",
                   "issues", "issue_comment", "discussion",
                   "discussion_comment", "release", "repository_dispatch",
                   "merge_group", "check_suite", "deployment", "status")


def check_text(name, body):
    """בדיקות סטטיות על קובץ workflow אחד. מחזיר רשימת ממצאים."""
    findings = []

    # 1. ‏cron לא מצוטט: ה-scheduler עלול לקרוא ערך ריק — והמשימה
    #    מדולגת לנצח בזמן שה-YAML נשאר תקין למראה.
    for m in re.finditer(r"-\s*cron:\s*(.+)", body):
        v = m.group(1).strip()
        if not (v.startswith("'") or v.startswith('"')):
            findings.append(("cron-unquoted",
                             "%s: ‏cron בלי מרכאות: %r" % (name, v)))

    # 2. ‏if: שמפנה ל-output שאיש לא כותב — תנאי שהוא תמיד false,
    #    וה-job מדולג בירוק לנצח. בדיוק הבאג של #266 בצורתו הבאה.
    written = set(re.findall(r"echo\s+\"?(\w+)=", body))
    written |= set(re.findall(r"^\s{4,}(\w+):\s*\$\{\{\s*steps\.", body, re.M))
    for m in re.finditer(r"\boutputs\.(\w+)", body):
        if m.group(1) not in written:
            findings.append(("if-orphan-output",
                             "%s: ‏`outputs.%s` שאיש אינו כותב — התנאי "
                             "תמיד false וה-job מדולג בירוק"
                             % (name, m.group(1))))

    # 3. ‏workflow בלי שום טריגר בר-הפעלה לא ירוץ לעולם.
    on_m = re.search(r"^(?:True|on):\s*$", body, re.M)
    on_inline = re.search(r"^on:\s*\[([^\]]*)\]", body, re.M)
    triggers = ""
    if on_inline:
        triggers = on_inline.group(1)
    elif on_m:
        tail = body[on_m.end():]
        block = []
        for line in tail.split("\n"):
            if line and not line.startswith((" ", "\t")):
                break
            block.append(line)
        triggers = "\n".join(block)
    if not any(re.search(r"\b%s\b" % t, triggers) for t in FIRING_TRIGGERS):
        findings.append(("no-trigger",
                         "%s: אין אף טריגר בר-הפעלה — לא ירוץ לעולם" % name))

    # 4. ‏continue-on-error מסתיר כישלון. לא בהכרח באג — אבל חייב
    #    להיות גלוי, כי הוא הופך אדום לירוק בשקט.
    for m in re.finditer(r"continue-on-error:\s*true", body):
        findings.append(("continue-on-error",
                         "%s: ‏continue-on-error: true — כישלון שם "
                         "ייראה ירוק" % name))
    return findings


def static_scan(wf_dir=WF_DIR):
    out = {}
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        body = open(os.path.join(wf_dir, fn), encoding="utf-8").read()
        out[fn] = check_text(fn, body)
    return out


def runs_scan(wf_dir=WF_DIR):
    """מתי כל workflow רץ לאחרונה. שלושה מצבים, לא שניים."""
    out = {}
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        try:
            r = subprocess.run(
                ["gh", "run", "list", "--workflow", fn, "--limit", "1",
                 "--json", "createdAt,conclusion"],
                capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            out[fn] = {"state": "could-not-check", "detail": "gh לא רץ"}
            continue
        if r.returncode != 0:
            out[fn] = {"state": "could-not-check",
                       "detail": (r.stderr or "").strip()[:120]}
            continue
        try:
            runs = json.loads(r.stdout or "[]")
        except ValueError:
            out[fn] = {"state": "could-not-check", "detail": "פלט לא JSON"}
            continue
        if not runs:
            # ‏"מעולם לא רץ" של קובץ בן שעות אינו ממצא — של קובץ בן
            # חודש הוא בדיוק המחלקה השקטה. הגיל הוא חלק מהנתון.
            age = "גיל לא ידוע"
            try:
                g = subprocess.run(
                    ["git", "log", "--format=%cs", "-1", "--",
                     os.path.join(wf_dir, fn)],
                    capture_output=True, text=True, timeout=30,
                    stdin=subprocess.DEVNULL)
                if g.returncode == 0 and g.stdout.strip():
                    age = "בריפו מאז " + g.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass
            out[fn] = {"state": "never-ran",
                       "detail": "אפס ריצות אי-פעם (%s)" % age}
        else:
            out[fn] = {"state": "ran",
                       "detail": "%s · %s" % (runs[0].get("createdAt"),
                                              runs[0].get("conclusion"))}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", action="store_true",
                    help="גם לשאול את GitHub מתי כל workflow רץ")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    static = static_scan()
    # ‏continue-on-error הוא אזהרה גלויה, לא כישלון — השאר מפילים.
    hard = {n: [f for f in fs if f[0] != "continue-on-error"]
            for n, fs in static.items()}
    bad = any(hard.values())
    runs = runs_scan() if a.runs else None

    if a.json:
        json.dump({"static": {n: fs for n, fs in static.items() if fs},
                   "runs": runs}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1 if bad else 0

    for name, fs in static.items():
        for kind, msg in fs:
            mark = "!" if kind == "continue-on-error" else "✗"
            print("%s %-22s %s" % (mark, kind, msg))
    if not any(static.values()):
        print("✓ סטטי: %d קבצים, אפס ממצאים" % len(static))
    if runs is not None:
        print()
        for name, r in runs.items():
            mark = {"ran": "✓", "never-ran": "✗",
                    "could-not-check": "?"}[r["state"]]
            print("%s %-24s %-16s %s" % (mark, name, r["state"], r["detail"]))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
