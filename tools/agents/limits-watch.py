"""מנטר שתנאי החינמי שפורסמו לא השתנו מתחתינו.

**הדרישה (הבעלים, 2026-09-02):** "הבוט שבודק — נגיד משבועי לחודשי, אם
אותה חברה שינתה את הספירה של המנוי החינמי." ספק משנה תנאים בלי
לשאול — ‏Cerebras סגר את המסלול בלי-כרטיס באוגוסט, ו-CF המית מודל
במאי — ומי שנשען על תנאי אתמול מגלה את זה מול קיר.

**איך.** לכל ספק שמור בדף המכסות הציבורי שלו **עוגן**: המספר או
הביטוי שהתקרות שלנו נשענות עליו. הכלי מושך את הדף ובודק שהעוגן
עדיין שם. שלושה מצבים, הלקסיקון הקבוע:

    same             העוגן נמצא — התנאים כפי שנרשמו
    changed          הדף נקרא והעוגן איננו — **החברה שינתה משהו.**
                     זו ההתראה, והיא מפילה את הריצה
    could-not-check  הדף לא נקרא. אינו "אותו דבר"

עוגן שנעלם אינו אומר בהכרח שהתקרה השתנתה — אולי רק ניסוח הדף.
אבל זה בדיוק הרגע לבדוק ידנית ולעדכן את המניפסט, וזה כל התפקיד.

    python tools/agents/limits-watch.py
"""
import re
import urllib.error
import urllib.request

# העוגנים: מה בדיוק אנחנו מצפים למצוא בדף של כל ספק, נכון ל-2026-09-02.
# עוגן = הנתון שהתקרה במניפסט נשענת עליו, בצורתו בדף.
ANCHORS = [
    ("cloudflare", "https://developers.cloudflare.com/workers-ai/platform/pricing/",
     [r"10,?000\s+(free\s+)?[Nn]eurons"]),
    ("gemini", "https://ai.google.dev/gemini-api/docs/rate-limits",
     [r"[Ff]ree\s+[Tt]ier"]),
    ("groq", "https://console.groq.com/docs/rate-limits",
     [r"[Rr]ate\s+[Ll]imits"]),
    ("openrouter", "https://openrouter.ai/docs/api-reference/limits",
     [r":free", r"[Ff]ree"]),
    ("mistral", "https://help.mistral.ai/en/articles/450104-how-can-i-try-the-api-for-free-with-the-experiment-plan",
     [r"[Ee]xperiment"]),
]

SAME, CHANGED, NOCHK = "same", "changed", "could-not-check"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "imagectl-limits-watch/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def check(provider, url, patterns, body=None):
    if body is None:
        try:
            body = fetch(url)
        except (urllib.error.URLError, OSError, ValueError):
            return {"provider": provider, "state": NOCHK,
                    "detail": "הדף לא נקרא — רשת או חסימה. אינו 'אותו דבר'"}
    missing = [p for p in patterns if not re.search(p, body)]
    if missing:
        return {"provider": provider, "state": CHANGED,
                "detail": "העוגן %r איננו בדף — החברה שינתה משהו, או "
                          "ששכתבו את הדף. לבדוק ולעדכן את המניפסט"
                          % missing[0]}
    return {"provider": provider, "state": SAME, "detail": ""}


def main():
    rows = [check(p, u, pats) for p, u, pats in ANCHORS]
    changed = [r for r in rows if r["state"] == CHANGED]
    for r in rows:
        mark = {SAME: "✓", CHANGED: "✗", NOCHK: "?"}[r["state"]]
        print("%s %-11s %-16s %s" % (mark, r["provider"], r["state"],
                                     r["detail"]))
    if changed:
        print("\n**%d ספקים שינו את הדף שהתקרות נשענות עליו.** זה הרגע "
              "לבדוק ידנית — לפני שהקיר מגיע אלינו." % len(changed))
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
