#!/usr/bin/env python3
"""אותה בקשה, תוכנית ריצה אחרת לפי מה שיש על המכונה.

**הבעיה שזה פותר.** אותה משימה מוגשת ממחשב עבודה בלי הרשאות, ממחשב
של חבר עם כרטיס מסך, וממכונה שיש עליה הכול. התוצאה צריכה להיות זהה;
**הדרך אליה — לא.**

`probe-machine.py` אומר **מה יש**. הקובץ הזה אומר **מה לעשות עם זה**.

**הכלל המוחלט:** הוא **אינו מתקין דבר**. אם התקנה הייתה משפרת, הוא
אומר זאת ומפרט מה — ועוצר. ההתקנה היא החלטה של בעל המכונה, לא של
הסוכן שרץ עליה.

**נכשל סגור.** שכבה נכללת רק אם נמדדה כזמינה. `unknown` אינו זמינות,
ומשימה שאין לה שכבה מתאימה מדווחת ככזאת — לא מנותבת ל"הכי קרוב".

    python tools/plan.py --task classify
    python tools/plan.py --task implement --json
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "probe-machine.py")

# מה כל סוג משימה באמת דורש. סדר השכבות הוא סדר ההעדפה.
TASKS = {
    "classify": {
        "he": "סיווג, תיוג, ניתוב — תשובה קצרה ודטרמיניסטית",
        "layers": ["ollama", "gemini", "codex", "grok", "claude"],
        "needs": "מודל כלשהו שעונה",
    },
    "review": {
        "he": "סקירת קוד או טקסט — דורש הבנה, לא רק סיווג",
        "layers": ["gemini", "codex", "grok", "claude"],
        "needs": "מודל בינוני ומעלה. מקומי קטן אינו מספיק",
    },
    "implement": {
        "he": "כתיבת קוד עם טסטים ובקרה שלילית",
        "layers": ["codex", "grok", "claude"],
        "needs": "סוכן עם גישה לקבצים ולגיט",
    },
    "judgement": {
        "he": "שיפוט, מיזוג, סודות, הכרעה",
        "layers": ["claude"],
        "needs": "המתאם. אינו מואצל",
    },
}


def probe():
    if not os.path.isfile(PROBE):
        raise SystemExit("אין %s — אי אפשר לתכנן בלי למדוד." % PROBE)
    e = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, PROBE, "--json"],
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=300, env=e, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise SystemExit("הגשש נכשל (%d). 'לא הצלחנו למדוד' אינו 'אין "
                         "כלום'.\n%s" % (r.returncode, r.stderr[:300]))
    return json.loads(r.stdout)


def plan(task, p):
    spec = TASKS[task]
    usable = p["verdict"]["usable_layers"]
    unusable = p["verdict"]["unusable"]
    chosen, skipped = None, []
    for layer in spec["layers"]:
        if layer in usable:
            chosen = layer
            break
        skipped.append({"layer": layer,
                        "why": unusable.get(layer, "לא נמדד כזמין")})
    out = {
        "task": task, "what": spec["he"], "needs": spec["needs"],
        "chosen": chosen, "skipped": skipped,
        "machine": {"os": p["hardware"]["os"], "gpu": p["hardware"]["gpu"],
                    "cpus": p["hardware"]["cpus"],
                    "admin": p["install"]["admin"],
                    "free_gb": p["install"]["free_gb"]},
        "would_help_if_installed": [], "install_allowed": None, "notes": [],
    }
    if chosen is None:
        out["notes"].append(
            "אין שכבה זמינה למשימה הזאת על המכונה הזאת. זו עצירה — "
            "לא ניתוב ל'הכי קרוב'.")
    # מה היה משתפר בהתקנה — אמירה בלבד, לעולם לא פעולה
    for layer in spec["layers"]:
        if layer in usable:
            continue
        why = unusable.get(layer, "")
        if "אינו מותקן" in why or "אין מודלים" in why:
            out["would_help_if_installed"].append(layer)
    out["install_allowed"] = bool(p["install"]["home_writable"]) and \
        isinstance(p["install"]["free_gb"], float) and p["install"]["free_gb"] > 3
    if out["would_help_if_installed"]:
        out["notes"].append(
            "התקנה עשויה לשפר — אבל **אינה מתבצעת כאן**. הצג לבעל "
            "המכונה מה חסר ובקש אישור.")
    if p["hardware"]["gpu"] and "ollama" not in usable:
        out["notes"].append(
            "יש כרטיס מסך במכונה הזאת ואין ollama. זו ההזדמנות הכי "
            "משתלמת — אבל רק באישור.")
    if not p["install"]["admin"]:
        out["notes"].append(
            "אין הרשאות admin. התקנה שדורשת אותן תיכשל, וכדאי לומר "
            "זאת מראש ולא באמצע.")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", choices=sorted(TASKS), required=True)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = plan(a.task, probe())
    if a.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0 if r["chosen"] else 1

    m = r["machine"]
    print("משימה: %s — %s" % (r["task"], r["what"]))
    print("דורשת: %s" % r["needs"])
    print("מכונה: %s · %s ליבות · GPU %s · admin=%s · פנוי %s GB\n"
          % (m["os"], m["cpus"], m["gpu"] or "אין", m["admin"], m["free_gb"]))
    if r["chosen"]:
        print("→ רץ על: %s" % r["chosen"])
    else:
        print("→ **אין שכבה זמינה.**")
    for s in r["skipped"]:
        print("   דילג על %-8s %s" % (s["layer"], s["why"]))
    if r["would_help_if_installed"]:
        print("\nהיה משתפר אם היה מותקן: %s"
              % ", ".join(r["would_help_if_installed"]))
        print("אפשר להתקין כאן טכנית: %s  (עדיין דורש אישור)"
              % r["install_allowed"])
    for n in r["notes"]:
        print("\n• %s" % n)
    return 0 if r["chosen"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
