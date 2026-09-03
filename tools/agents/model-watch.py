#!/usr/bin/env python3
"""מנטר שהמודלים שבקונפיג עדיין קיימים אצל הספקים.

**למה.** ביום החיבור הראשון זה קרה פעמיים: ‏groq/compound החליף שם,
ו-`llama-3.1-8b` של Cloudflare הוצא משימוש חודשים קודם — ואיש לא
ידע עד הקריאה הראשונה. ספק חינמי מחליף מודלים בלי לשאול, והכשל
מתגלה בדיוק כשמשהו חשוב רץ.

**שלושה מצבים, לא שניים** (אותו לקסיקון כמו quota-check):

    ok               המודל מופיע בקטלוג החי של הספק
    gone             היה בקונפיג ואיננו בקטלוג — זו ההתראה
    could-not-check  הקטלוג לא נשאל (אין מפתח/רשת). אינו "קיים"

רץ על מכונת בעל המפתחות (קורא .env, לעולם לא מדפיס ערכים).
‏free-fleet.ps1 -Check מריץ אותו אוטומטית — הניטור צמוד לנקודה
שבה מרימים את ה-proxy.

    python tools/agents/model-watch.py
    python tools/agents/model-watch.py --json
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
YAML = os.path.join(HERE, "litellm.yaml")

OK, GONE, NOCHK = "ok", "gone", "could-not-check"

# ‏urlopen פותח דרך הפותחן הגלובלי של urllib, שכולל גם FileHandler
# ו-FTPHandler — ולכן כתובת קטלוג שגויה היא `file:///etc/shadow`
# **שנקרא בהצלחה**, ומפתח ה-API נשלח אליה בכותרת. הפותחן להלן נבנה
# עם מטפלי HTTP בלבד, ולכן סכימה אחרת נכשלת מחוסר מטפל ולא מחוסר
# בדיקה. ‏UnknownHandler חובה: בלעדיו פותחן בלי מטפל מתאים מחזיר
# None **בשקט** (נמדד), וזה כשל פתוח.
_OPENER = urllib.request.OpenerDirector()
for _h in (urllib.request.ProxyHandler, urllib.request.UnknownHandler,
           urllib.request.HTTPHandler, urllib.request.HTTPSHandler,
           urllib.request.HTTPDefaultErrorHandler,
           urllib.request.HTTPRedirectHandler,
           urllib.request.HTTPErrorProcessor):
    _OPENER.add_handler(_h())


class UnsafeScheme(Exception):
    """כתובת שאינה http/https — הגדרה שגויה, לא תקלת רשת.

    מובחן מ-URLError בכוונה: תקלת רשת היא `could-not-check` לפי
    הלקסיקון, וזו טעות שחייבת להישמע ולא להיבלע לתוכו.
    """


def http_open(req, timeout):
    """‏http/https בלבד — בדיקה מפורשת, ומאחוריה פותחן שאוכף אותה.

    הבדיקה נותנת הודעה ברורה על הכתובת; הפותחן אוכף גם את מה שהבדיקה
    אינה רואה — הפניה אל סכימה אחרת באמצע הדרך, שאליה היו נשלחות
    הכותרות ובהן המפתח.
    """
    url = getattr(req, "full_url", req)
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise UnsafeScheme("כתובת שאינה http/https: %r" % url)
    return _OPENER.open(req, timeout=timeout)


def load_env():
    p = os.path.join(ROOT, ".env")
    if not os.path.isfile(p):
        return
    for line in io.open(p, encoding="utf-8"):
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if m and m.group(2).strip() and not line.lstrip().startswith("#"):
            os.environ.setdefault(m.group(1), m.group(2).strip())


def configured():
    """‏(ספק, מודל) מכל שורת model בקונפיג. טקסטואלי — אין yaml ב-CI."""
    body = io.open(YAML, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"^\s+model:\s*(\S+)", body, re.M):
        prov, model = m.group(1).split("/", 1)
        out.append((prov, model))
    return sorted(set(out))


def _get(url, headers):
    # ‏Groq מחזיר 403 ל-User-Agent של urllib — נמדד (‏curl עבר, urllib
    # נחסם עם אותו מפתח בדיוק). ‏UA מפורש פותר.
    headers = dict(headers, **{"User-Agent": "imagectl-model-watch/1.0"})
    req = urllib.request.Request(url, headers=headers)
    with http_open(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def catalog(provider):
    """שמות המודלים החיים אצל הספק, או None אם אי אפשר לשאול."""
    env = os.environ.get
    try:
        if provider == "groq":
            k = env("GROQ_API_KEY")
            if not k:
                return None
            d = _get("https://api.groq.com/openai/v1/models",
                     {"Authorization": "Bearer " + k})
            return {m["id"] for m in d.get("data", [])}
        if provider == "nvidia_nim":
            k = env("NVIDIA_NIM_API_KEY")
            if not k:
                return None
            d = _get("https://integrate.api.nvidia.com/v1/models",
                     {"Authorization": "Bearer " + k})
            return {m["id"] for m in d.get("data", [])}
        if provider == "mistral":
            k = env("MISTRAL_API_KEY")
            if not k:
                return None
            d = _get("https://api.mistral.ai/v1/models",
                     {"Authorization": "Bearer " + k})
            return {m["id"] for m in d.get("data", [])}
        if provider == "gemini":
            k = env("GEMINI1_API_KEY") or env("GEMINI_API_KEY")
            if not k:
                return None
            d = _get("https://generativelanguage.googleapis.com/v1beta/models",
                     {"x-goog-api-key": k})
            return {m["name"].removeprefix("models/")
                    for m in d.get("models", [])}
        if provider == "cloudflare":
            k, acct = env("CLOUDFLARE_API_KEY"), env("CLOUDFLARE_ACCOUNT_ID")
            if not (k and acct):
                return None
            names = set()
            for page in (1, 2):
                d = _get("https://api.cloudflare.com/client/v4/accounts/%s"
                         "/ai/models/search?per_page=100&page=%d" % (acct, page),
                         {"Authorization": "Bearer " + k})
                names |= {m["name"] for m in (d.get("result") or [])}
            return names
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
    return None


def scan():
    out, cats = [], {}
    for prov, model in configured():
        if prov not in cats:
            cats[prov] = catalog(prov)
        cat = cats[prov]
        if cat is None:
            out.append({"provider": prov, "model": model, "state": NOCHK,
                        "detail": "הקטלוג לא נשאל — אין מפתח או אין רשת"})
        elif model in cat:
            out.append({"provider": prov, "model": model, "state": OK,
                        "detail": "בקטלוג החי"})
        else:
            out.append({"provider": prov, "model": model, "state": GONE,
                        "detail": "בקונפיג אך איננו בקטלוג — הוסר או "
                                  "שונה שמו. זה מה שקרה ל-llama-3.1-8b"})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    load_env()
    rows = scan()
    gone = [r for r in rows if r["state"] == GONE]
    if a.json:
        json.dump({"results": rows, "gone": len(gone)}, sys.stdout,
                  ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1 if gone else 0
    for r in rows:
        mark = {OK: "✓", GONE: "✗", NOCHK: "?"}[r["state"]]
        print("%s %-11s %-45s %s" % (mark, r["provider"], r["model"],
                                     r["detail"] if r["state"] != OK else ""))
    if gone:
        print("\n**%d מודלים נעלמו מהקטלוג.** לשאול את הספק מה חי "
              "(model-watch עושה זאת) ולעדכן את litellm.yaml." % len(gone))
    return 1 if gone else 0


if __name__ == "__main__":
    raise SystemExit(main())
