#!/usr/bin/env python3
"""קורא פסק-דין שער מתוך body של PR. הצד השני של gate-pr.sh.

רץ ב-pr-gate.yml על כל PR מענף auto/* — זו האכיפה שאי-אפשר
להשתיק: סוכן שדילג על השער פשוט לא ייצר פסק-דין, וזה אדום.

    exit 0 — pass
    exit 1 — fail, פסק-דין חסר, או פסק-דין לא מוכר
    exit 2 — insufficient_evidence: אינו pass ואינו fail. הקורא
             (ה-workflow) מתייג ומגיב — לא ממזג בשקט ולא מאדים
"""
import re
import sys

VALID = ("pass", "fail", "insufficient_evidence")


def read_verdict(text):
    m = re.search(r"^gate-verdict:\s*(\S+)", text, re.M)
    return m.group(1) if m else None


def main():
    text = sys.stdin.read()
    v = read_verdict(text)
    if v is None:
        print("אין פסק-דין שער ב-body — הסוכן דילג על השער. זה בדיוק "
              "המצב שהאכיפה קיימת בשבילו.")
        return 1
    if v not in VALID:
        print("פסק-דין לא מוכר: %r" % v)
        return 1
    print("gate-verdict: %s" % v)
    if v == "pass":
        return 0
    if v == "insufficient_evidence":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
