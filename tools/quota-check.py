#!/usr/bin/env python3
"""בודק אם מקור המכסה של כל ספק עדיין עובד — ומדווח על שינוי.

**הבעיה שזה פותר.** ‏"לא ידוע" נשאר "לא ידוע" לנצח, כי אף אחד לא
בודק שוב. מקור שנשבר בעדכון נראה בדיוק כמו מקור שמעולם לא היה, ומקור
שנפתח לא מתגלה. שניהם שקטים.

**שלושה מצבים, ולא שניים:**

    ok       — נבדק, החזיר נתון
    broken   — **היה עובד ועכשיו לא.** זו הרעה, ומפילה את הריצה
    absent   — אין מקור ידוע. לא כישלון, אבל גם לא "אין מכסה"

ההבחנה בין `broken` ל-`absent` היא כל הפואנטה. בלעדיה, ‏endpoint לא
מתועד שנשבר בעדכון יידווח כ"מעולם לא היה", וההתראה תאבד.

**סודות.** הכלי קורא טוקנים מקבצי האימות המקומיים כדי לשאול, ו**לעולם
אינו מדפיס אותם**. הוא רץ על המכונה של בעל המנוי — לא ב-Actions.

    python tools/quota-check.py
    python tools/quota-check.py --json
    python tools/quota-check.py --write    # מעדכן providers.json
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDERS = os.path.join(HERE, "..", "knowledge", "providers.example.json")
HOME = os.path.expanduser("~")

OK, BROKEN, ABSENT, EXPIRED = "ok", "broken", "absent", "expired"


def _result(state, detail, data=None):
    return {"state": state, "detail": detail, "data": data}


def check_codex():
    """‏codex app-server, ‏JSON-RPC על stdio.

    ‏stdin חייב להישאר פתוח עד שהתשובה חוזרת: הזנה מקובץ גורמת
    לתהליך לצאת לפני התשובה האסינכרונית, וזה **נראה** כמו מתודה
    שאינה קיימת. זו בדיוק הטעות שהמדידה הזאת נועדה לא לעשות.
    """
    from shutil import which
    exe = which("codex")
    if not exe:
        return _result(ABSENT, "‏codex אינו ב-PATH")
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"clientInfo": {"name": "quota-check", "title": "quota-check",
                                   "version": "0.0.1"}}},
        {"jsonrpc": "2.0", "method": "initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read",
         "params": {}},
    ]
    try:
        # בווינדוס ה-CLI הוא shim מסוג .CMD, ו-Popen בלי shell נכשל
        # ב-WinError 2. הנתיב המלא מ-which פותר את זה בכל מערכת.
        p = subprocess.Popen([exe, "app-server"],
                             shell=(os.name == "nt" and exe.lower().endswith(
                                 (".cmd", ".bat"))),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             encoding="utf-8", bufsize=1)
    except OSError as exc:
        return _result(BROKEN, "‏codex app-server לא עלה: %s" % exc)
    try:
        for m in msgs:
            p.stdin.write(json.dumps(m) + "\n")
            p.stdin.flush()
        deadline = 60
        import time
        t0 = time.time()
        while time.time() - t0 < deadline:
            line = p.stdout.readline()
            if not line:
                break
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("id") == 2:
                if "error" in obj:
                    return _result(BROKEN, "המתודה החזירה שגיאה: %s"
                                   % str(obj["error"])[:120])
                # התשובה יושבת תחת result.rateLimits, לא תחת result.
                # קריאה ישירה מ-result מחזירה {} — וזה **נראה** כמו
                # מתודה שהשתנתה, בזמן שרק המעטפת שונה.
                r = (obj.get("result") or {}).get("rateLimits") or {}
                out = {}
                for key in ("primary", "secondary"):
                    w = r.get(key) or {}
                    if "usedPercent" in w:
                        out[key] = {"used_percent": w.get("usedPercent"),
                                    "resets_at": w.get("resetsAt"),
                                    "window_minutes": w.get("windowDurationMins")}
                if not out:
                    return _result(BROKEN, "תשובה בלי usedPercent")
                out["plan"] = r.get("planType")
                return _result(OK, "‏account/rateLimits/read", out)
        return _result(BROKEN, "לא חזרה תשובה ל-id=2 תוך %ds" % deadline)
    finally:
        try:
            p.kill()
        except Exception:                              # noqa: BLE001
            pass


def _grok_token():
    """הטוקן מקובץ האימות המקומי. לעולם אינו מוחזר החוצה.

    המבנה הוא {issuer::client-id: {key: ..., refresh_token: ...}} —
    נבדק על ידי קריאת **שמות** המפתחות בלבד, לא ערכיהם.
    """
    path = os.path.join(HOME, ".grok", "auth.json")
    if not os.path.isfile(path):
        return None, None
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    for entry in d.values():
        if not isinstance(entry, dict):
            continue
        for k in ("key", "access_token", "accessToken", "token"):
            v = entry.get(k)
            if isinstance(v, str) and len(v) > 20:
                return v, entry.get("expires_at")
    return None, None


def _expired(stamp):
    """‏True רק כשנמדד שפג. ‏None או פורמט לא מוכר אינם 'תקף'."""
    if not isinstance(stamp, str):
        return None
    try:
        t = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")[:32])
    except ValueError:
        return None
    return t < dt.datetime.now(dt.timezone.utc)


def check_grok():
    """‏endpoint לא מתועד, שנקרא מקוד של צד שלישי.

    לכן הכישלון שלו חייב להיקרא **"נשבר"** ולא "אין מכסה" — הוא
    עלול להשתנות בכל עדכון, וזו בדיוק הסיבה שהבדיקה הזאת קיימת.
    """
    tok, exp = _grok_token()
    if not tok:
        return _result(ABSENT, "לא נמצא טוקן ב-~/.grok/auth.json")
    # טוקן שפג אינו מקור שנשבר. שני מצבים שונים, שני טיפולים שונים:
    # ‏401 על טוקן פג פירושו "הרץ grok פעם אחת", לא "ה-endpoint מת".
    if _expired(exp):
        return _result(EXPIRED, "הטוקן פג ב-%s — הריצו `grok` פעם אחת "
                       "כדי לחדש. אין כאן ראיה על ה-endpoint." % exp[:19])
    url = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tok, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return _result(EXPIRED, "‏HTTP %s — אימות. הריצו `grok` "
                           "לחידוש הטוקן." % exc.code)
        return _result(BROKEN, "‏HTTP %s מה-endpoint" % exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _result(BROKEN, "הקריאה נכשלה: %s" % type(exc).__name__)
    keys = [k for k in body if isinstance(body, dict)][:8]
    return _result(OK, "‏cli-chat-proxy /v1/billing", {"fields": keys})


CHECKS = {"codex": check_codex, "grok": check_grok}
NO_METHOD = {
    "gemini": "אין מקור תוכנתי. התקרות ידועות מהקונסולה.",
    "claude": "אין תת-פקודה למכסה. ‏/cost אינטראקטיבי בלבד.",
    "ollama": "מקומי — אין מכסה.",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="מעדכן את providers.json בתוצאה")
    a = ap.parse_args()

    prev = {}
    if os.path.isfile(PROVIDERS):
        try:
            prev = json.load(open(PROVIDERS, encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}

    out, regressed = {}, []
    for name, fn in CHECKS.items():
        try:
            r = fn()
        except Exception as exc:                       # noqa: BLE001
            r = _result(BROKEN, "הבדיקה עצמה קרסה: %s" % type(exc).__name__)
        was = ((prev.get("providers", {}).get(name) or {})
               .get("quota_check", {}) or {}).get("state")
        # ‏"היה עובד ועכשיו לא" הוא המצב היחיד שמפיל את הריצה.
        if was == OK and r["state"] != OK:
            regressed.append(name)
            r["regressed_from"] = OK
        out[name] = r
    for name, why in NO_METHOD.items():
        out[name] = _result(ABSENT, why)

    stamp = dt.datetime.now().isoformat(timespec="seconds")
    if a.json:
        json.dump({"checked_at": stamp, "results": out,
                   "regressed": regressed},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        print("נבדק: %s\n" % stamp)
        for name, r in out.items():
            mark = {"ok": "✓", "broken": "✗", "absent": "·",
                    "expired": "⌛"}[r["state"]]
            print("%s %-8s %-8s %s" % (mark, name, r["state"], r["detail"]))
            if r.get("data"):
                print("      %s" % json.dumps(r["data"], ensure_ascii=False))
        if regressed:
            print("\n**הרעה: %s היה עובד ועכשיו לא.**" % ", ".join(regressed))
            print("זה שונה מ'אין מקור' — משהו נשבר, וכדאי לדעת מה.")

    if a.write and os.path.isfile(PROVIDERS):
        d = prev or {"providers": {}}
        for name, r in out.items():
            d.setdefault("providers", {}).setdefault(name, {})
            d["providers"][name]["quota_check"] = {
                "state": r["state"], "detail": r["detail"],
                "checked_at": stamp}
        io_path = PROVIDERS
        with open(io_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
        print("\nנכתב %s" % os.path.basename(io_path))

    # הרעה מפילה; "אין מקור" לא.
    return 1 if regressed else 0


if __name__ == "__main__":
    raise SystemExit(main())
