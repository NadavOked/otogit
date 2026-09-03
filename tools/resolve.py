#!/usr/bin/env python3
"""מרכיב לסוכן את מה שהוא צריך לקרוא — כללי, ואז ספציפי לפרויקט.

**המבנה.** שלוש קטגוריות, בשתי שכבות:

    agents/  skills/  knowledge/          ← כללי, שייך לכל פרויקט
    projects/<שם>/{agents,skills,knowledge}/  ← של אותו פרויקט בלבד

**הכלל.** סוכן שעובד על פרויקט קורא **את שתיהן**: קודם הכללי, ואז
הספציפי. קובץ באותו שם בשכבה הספציפית **גובר** — כי פרויקט יודע על
עצמו יותר מהכלל. כל דריסה מדווחת, כי דריסה שקטה היא בדיוק הדרך שבה
מישהו מקבל חוק שהוא לא יודע שהוחלף.

**מה זה לא.** זה אינו מחליף את `.otogit/` שבריפו של הפרויקט עצמו.
שם הפרויקט מצהיר על **עצמו** — אילו נתיבים אסורים, לפי אילו כללים
לסקור. כאן יושב מה שהצי **למד** עליו. שני מקורות, שתי משמעויות.

**נכשל סגור.** ספרייה חסרה מדווחת; פרויקט שאין לו תיקייה כלל הוא
שגיאה ולא "אין לו כלום" — כי אלה שני מצבים שונים.

    python resolve.py --project imagectl
    python resolve.py --project imagectl --json
    python resolve.py --list
"""
import argparse
import json
import os
import re
import subprocess
import sys

KINDS = ("agents", "skills", "knowledge")
# שורש הריפו, לא תיקיית הכלי. הגרסה הראשונה חישבה את tools/
# ואז דיווחה "אין תיקיית projects" בזמן שהיא קיימת שכבה מעל.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def detect_repo(cwd=None):
    """‏owner/repo מה-remote של תיקיית העבודה, או None.

    ‏65 פרויקטים פירושם שאי אפשר לדרוש `--project` ידנית. מה שאפשר
    לגזור — גוזרים. מה שלא — אומרים שלא ידוע, לא מנחשים.
    """
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=20,
                           cwd=cwd, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    url = (r.stdout or "").strip()
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    return "%s/%s" % (m.group(1), m.group(2)) if m else None


def visibility(full_name):
    """‏public / private / unknown. כישלון אינו 'public'."""
    if not full_name:
        return "unknown"
    try:
        r = subprocess.run(["gh", "api", "repos/" + full_name,
                            "--jq", ".visibility"],
                           capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    v = (r.stdout or "").strip()
    return v if r.returncode == 0 and v in ("public", "private") else "unknown"


def _files(d):
    if not os.path.isdir(d):
        return {}
    out = {}
    for base, _dirs, names in os.walk(d):
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.join(base, n)
            out[os.path.relpath(p, d).replace(os.sep, "/")] = p
    return out


def projects(root=ROOT):
    d = os.path.join(root, "projects")
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d)
                  if os.path.isdir(os.path.join(d, n)) and not n.startswith("."))


def resolve(project, root=ROOT):
    pdir = os.path.join(root, "projects", project)
    if not os.path.isdir(pdir):
        raise SystemExit(
            "אין תיקייה לפרויקט %r תחת projects/. זו שגיאה ולא 'אין לו "
            "כלום' — פרויקט בלי תיקייה ופרויקט עם תיקייה ריקה הם שני "
            "מצבים שונים. קיימים: %s"
            % (project, ", ".join(projects(root)) or "אף אחד"))
    out = {"project": project, "kinds": {}, "overrides": [], "missing": []}
    for kind in KINDS:
        gen_dir, spec_dir = os.path.join(root, kind), os.path.join(pdir, kind)
        for d, what in ((gen_dir, "כללי"), (spec_dir, "של הפרויקט")):
            if not os.path.isdir(d):
                out["missing"].append("%s (%s)" % (
                    os.path.relpath(d, root).replace(os.sep, "/"), what))
        gen, spec = _files(gen_dir), _files(spec_dir)
        merged = dict(gen)
        for name, path in spec.items():
            if name in gen:
                out["overrides"].append("%s/%s" % (kind, name))
            merged[name] = path
        out["kinds"][kind] = {
            "general": sorted(gen),
            "project": sorted(spec),
            "effective": [{"name": n, "path": os.path.relpath(p, root)
                           .replace(os.sep, "/")}
                          for n, p in sorted(merged.items())],
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="ברירת מחדל: נגזר מה-remote")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.list:
        ps = projects()
        print("\n".join(ps) if ps else "אין תיקיית projects/ או שהיא ריקה")
        return 0
    repo = detect_repo()
    vis = visibility(repo)
    project = a.project or (repo.split("/")[-1].lower() if repo else None)
    if not project:
        raise SystemExit(
            "לא הצלחתי לגזור פרויקט מה-remote ולא נמסר --project. "
            "זו עצירה, לא ברירת מחדל — פרויקט לא ידוע ופרויקט ללא "
            "הגדרות הם שני מצבים שונים.")
    r = resolve(project)
    r["repo"] = repo
    r["visibility"] = vis
    if a.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    note = {"private": "   ← בפרטי כל ריצה עולה מתקציב, ואין CodeQL",
            "unknown": "   ← נראות לא ידועה: התנהג כאילו פרטי"}.get(
                r.get("visibility"), "")
    print("פרויקט: %s" % r["project"])
    print("ריפו: %s · נראות: %s%s\n"
          % (r.get("repo") or "לא נגזר", r.get("visibility"), note))
    for kind in KINDS:
        k = r["kinds"][kind]
        print("%s — כללי %d · של הפרויקט %d · בתוקף %d"
              % (kind, len(k["general"]), len(k["project"]),
                 len(k["effective"])))
        for e in k["effective"]:
            mark = " ←דורס" if "%s/%s" % (kind, e["name"]) in r["overrides"] else ""
            print("   %-34s %s%s" % (e["name"], e["path"], mark))
    if r["overrides"]:
        print("\nדריסות (הספציפי גובר): %s" % ", ".join(r["overrides"]))
    if r["missing"]:
        print("\nספריות שאינן קיימות — לא 'ריקות', פשוט אין:")
        for m in r["missing"]:
            print("   %s" % m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
