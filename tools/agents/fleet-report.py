#!/usr/bin/env python3
"""‏מה מונה התקציב סופר, ומה הוא **אינו** סופר.

‏`fleet_budget.py` ספר בשקט: ‏`--report` ו-`--help` החזירו אפס פלט,
ולא הייתה שום דרך לראות כמה נשרף או מול איזו תקרה. המסירה קבעה
שכשל של המונה "מרעיש ולא משבית" — אבל מונה שאיש אינו יכול לקרוא
אינו שונה בהרבה ממונה שאינו רץ.

**החלק החשוב בדוח הוא החצי השני:** אילו פריסות יוצאות מהקונפיג
ואין להן תקרה ידועה. עד עכשיו הן נראו בדיוק כמו פריסות בלי גבול —
‏"לא נספר" ו"אין לו תקרה" קופלו לאחד, וזה עיקרון 5.

    python tools/agents/fleet-report.py --report
    python tools/agents/fleet-report.py --uncounted
    python tools/agents/fleet-report.py --state

הקובץ נפרד מ-`fleet_budget.py` כדי לא לגרור argparse אל תוך ה-proxy
(‏litellm טוען אותו כ-`tools.agents.fleet_budget.handler`), ומטעין
אותו לפי נתיב — בדיוק כפי שהטסטים עושים.
"""
import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _budget():
    spec = importlib.util.spec_from_file_location(
        "fleet_budget", os.path.join(HERE, "fleet_budget.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def report(fb):
    """שורות הדוח: מה נספר, מול איזו תקרה, ומה אינו נאכף."""
    lines = ["== נספר בחלון הנוכחי =="]
    known = fb.caps()
    seen = {}
    for k, v in fb._load().items():
        parts = k.split("|")
        if len(parts) != 3:
            continue
        model, key, window = parts
        cur = fb.window_id(model, (known.get(model) or {}).get(
            "window", "daily"))
        if window != cur:
            continue                       # חלון שאינו הנוכחי
        n, tok = fb._cell(v)
        seen.setdefault(model, []).append((key, n, tok))
    if not seen:
        lines.append("  (אין רשומות — או שלא יצאה קריאה, או שהמצב אופס)")
    for model in sorted(seen):
        c = known.get(model)
        for key, n, tok in sorted(seen[model]):
            head = "  %-46s key…%-6s %5d בקשות %9d טוקנים" % (
                model, key or "-", n, tok)
            if not c:
                lines.append(head + "  ללא תקרה ידועה")
                continue
            used = tok if c.get("unit") == "tokens" else n
            pct = (100.0 * used / c["limit"]) if c["limit"] else 0
            lines.append("%s  %d/%d %s (%.0f%%)" % (
                head, used, c["limit"], c.get("unit", "requests"), pct))
    unc = fb.uncounted()
    lines += ["", "== מוגדר בקונפיג ואינו נאכף (%d) ==" % len(unc)]
    for model, why in unc:
        lines.append("  %-46s %s" % (model, why))
    if unc:
        lines += ["", "‏'אינו נאכף' אינו 'ללא גבול' — פירושו שהגבול אינו "
                      "ידוע לנו. ‏rpd או tokens_per_day שיתווספו למניפסט "
                      "ייאכפו בלי שינוי קוד."]
    return lines


def main(argv=None):
    # **לפני** parse_args: ‏argparse מדפיס את ה-help ויוצא בתוך
    # ‏parse_args, וההודעות כאן עבריות. ‏reconfigure שבא אחריו לא
    # רץ לעולם על המסלול הזה, ו-`--help` קרס ב-cp1252 בווינדוס —
    # נמדד. אותו באג של guard-bash, במקום שלישי.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(
        description="מונה התקציב של הצי החינמי — מה נספר ומה לא.")
    ap.add_argument("--report", action="store_true",
                    help="מה נספר בחלון הנוכחי, ומה אינו נאכף")
    ap.add_argument("--uncounted", action="store_true",
                    help="רק הפריסות שאין להן תקרה ידועה")
    ap.add_argument("--state", action="store_true", help="נתיב קובץ המצב")
    args = ap.parse_args(argv)
    fb = _budget()
    if args.state:
        print(fb.STATE)
    elif args.uncounted:
        for model, why in fb.uncounted():
            print("%s\t%s" % (model, why))
    elif args.report:
        print("\n".join(report(fb)))
    else:
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
