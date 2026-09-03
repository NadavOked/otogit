#!/usr/bin/env python3
"""שומר PreToolUse: חוסם פקודות מעטפת הרסניות ואת הגישה למעבדה.

**למה זה קיים.** עד עכשיו ההגבלות על סוכנים היו טקסט בפרומפט —
`tools/agents/POLICY.md` ו-`.otogit/agent-policy.txt`. זו בקשה למודל,
לא אכיפה, וסוכן יכול פשוט לא לציית. הכלל של הפרויקט הוא ששומר שאפשר
רק לבקש ממנו אינו שומר.

**כיצד הוא נכשל.** סגור. כל מסלול שאינו "הפקודה נבדקה ונמצאה נקייה"
מסתיים בחסימה: JSON שבור, שדה חסר, חריגה לא צפויה. "לא הצלחנו לבדוק"
ו"בדקנו והכל תקין" הם שני מצבים שונים (עיקרון 5), וכאן ההבדל ביניהם
הוא בין חסימה לבין `rm -rf`.

**מה הוא אינו.** הוא אינו מחליף את POLICY.md — הוא רשת ביטחון לפקודות
שאסור להריץ לעולם בלי אדם. גבולות נתיבים ותוכן נשארים במדיניות.
"""
import json
import os
import re
import sys

# כל דפוס: (regex, ההסבר שיוצג). ההסבר נכתב לבן אדם שקורא לוג בלילה.
RULES = [
    (r"\bmkfs(\.|\b)",              "יצירת מערכת קבצים מוחקת דיסק"),
    (r"\bwipefs\b",                 "מחיקת חתימות מחיצות"),
    (r"\bsgdisk\b.*(-Z|--zap)",     "איפוס טבלת מחיצות"),
    (r"\bdd\b[^|;&]*\bof=\s*/dev/", "כתיבה גולמית להתקן בלוק"),
    (r"\brm\b[^|;&]*-[a-zA-Z]*r[a-zA-Z]*f?[^|;&]*\s+/(\s|$)",
                                    "מחיקה רקורסיבית של שורש מערכת הקבצים"),
    (r"\bgh\s+repo\s+delete\b",     "מחיקת ריפו"),
    (r"\bgh\s+secret\b",            "סודות שייכים להבעלים בלבד"),
    (r"\bgh\s+auth\s+(token|logout)\b",
                                    "הדפסה או ביטול של טוקן ההזדהות"),
    (r"\bgit\s+push\b[^|;&]*(--force|-f\b)[^|;&]*\b(main|master)\b",
                                    "דחיפה כפויה לענף הראשי"),
    (r"\bgit\s+push\b[^|;&]*--delete\b",
                                    "מחיקת ענף או תג מרוחק"),
    (r"\bgit\s+push\b[^|;&]*\brefs/tags/",
                                    "תג שפורסם אינו נמחק ואינו נדרס"),
    (r"\bschtasks\b[^|;&]*/(Delete|Change)\b",
                                    "שינוי משימות מתוזמנות"),
    (r"\bsc\b\s+(delete|stop)\b",   "עצירה או מחיקה של שירות ווינדוס"),
    (r"\bStop-Service\b",           "עצירת שירות ווינדוס"),
]

# דפוסים ספציפיים לאתר — כתובת מעבדה, שם קובץ מפתח וכדומה. הם אינם
# יושבים בקוד כי הם שונים בכל פרויקט, והם **מתווספים** לרשימה שלמעלה
# ולא מחליפים אותה. פורמט: שורה לכל דפוס, "regex|נימוק".
# חסר ערך = אין תוספת. זו הרחבה, לא מתג כיבוי.
for _line in (os.environ.get("OTOGIT_SITE_DENY") or "").splitlines():
    _line = _line.strip()
    if not _line:
        continue
    _rx, _, _why = _line.partition("|")
    if not _rx or not _why:
        print("OTOGIT_SITE_DENY: %r אינו בפורמט regex|נימוק" % _line,
              file=sys.stderr)
        sys.exit(2)
    RULES.append((_rx, _why))

DENY = "deny"


def _emit(decision, reason):
    # ‏json.dumps בברירת המחדל בורח לתווי ASCII, וזה מכוון: על ווינדוס
    # ‏stdout הוא cp1252, ועברית מפילה את הכתיבה. במדידה, גם מטפל
    # הקריסה קרס על אותו דבר — כלומר השומר מת בלי לחסום. פלט ASCII
    # עובר בכל קידוד, וה-JSON נשאר תקין.
    payload = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def check(command):
    """מחזיר את ההסבר לחסימה, או None אם הפקודה נקייה."""
    for pattern, why in RULES:
        if re.search(pattern, command, re.IGNORECASE):
            return why
    return None


def main(stdin=None):
    stream = stdin if stdin is not None else sys.stdin
    try:
        payload = json.load(stream)
    except Exception as exc:                       # noqa: BLE001 — נכשל סגור
        _emit(DENY, "השומר לא הצליח לקרוא את הבקשה (%s) — חוסם. "
                    "כישלון בבדיקה אינו אישור." % type(exc).__name__)
        return 0
    command = None
    if isinstance(payload, dict):
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            command = tool_input.get("command")
    if not isinstance(command, str):
        _emit(DENY, "אין שדה tool_input.command — השומר אינו יודע מה נבדק, "
                    "ולכן חוסם.")
        return 0
    why = check(command)
    if why:
        _emit(DENY, "נחסם על ידי guard-bash: %s. אם זה נחוץ באמת — "
                    "הבעלים מריץ ידנית." % why)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                       # noqa: BLE001
        _emit(DENY, "השומר עצמו קרס (%s) — חוסם." % type(exc).__name__)
        sys.exit(0)
