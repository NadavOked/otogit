#!/usr/bin/env python3
"""מייצר את החלקים של providers.json שיש להם מקור אמת אחר.

**הבעיה.** ‏providers.json נכתב ביד — כלומר מתיישן בשקט, בדיוק כמו
זמני המודלים אחרי החלפת חומרה. ‏`in_use_by` הוא הדוגמה: שלושת
ה-workflows הועברו ל-flash-lite, והרשימה עודכנה ביד ובמזל.

**הקו המפריד.** מיוצר כאן רק מה שנגזר מהריפו עצמו — אילו workflows
קוראים לאיזה מודל. תקרות (rpm/rpd) הן **מדידות** מהקונסולה: אין להן
מקור בריפו, ולכן הן נשארות ידניות עם `source` ותאריך, והכלי אינו
נוגע בהן. לייצר מספר שאין לו מקור זה לא "אוטומציה", זה המצאה.

    python tools/agents/gen-manifest.py --check   # ‏CI: נכשל על drift
    python tools/agents/gen-manifest.py --write   # מעדכן את הקובץ
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
PROVIDERS = os.path.join(HERE, "providers.json")
WF_DIR = os.path.join(ROOT, ".github", "workflows")

MODEL_RE = re.compile(r"models/([\w.\-]+):generateContent")


def scan_usage(wf_dir=WF_DIR):
    """‏workflow → מודל, מתוך הקריאות בפועל. המקור, לא הזיכרון."""
    usage = {}
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        body = open(os.path.join(wf_dir, fn), encoding="utf-8").read()
        for m in MODEL_RE.finditer(body):
            usage.setdefault(m.group(1), []).append(fn[:-4].removesuffix(".yml")
                                                    if fn.endswith(".yaml")
                                                    else fn[:-4])
    return usage


def apply(data, usage):
    """מחזיר (עותק מעודכן, רשימת סטיות). אינו נוגע בשדות מדודים."""
    import copy
    d = copy.deepcopy(data)
    drift = []
    models = d.get("providers", {}).get("gemini", {}).get("models", {})
    for name, spec in models.items():
        want = sorted(usage.get(name, []))
        have = sorted(spec.get("in_use_by", []))
        if want != have:
            drift.append("%s: בקובץ %s, בפועל %s" % (name, have, want))
            spec["in_use_by"] = want
    # מודל שנקרא ב-workflow אך אינו רשום כלל — הסטייה המסוכנת ביותר:
    # אין לו תקרות רשומות, וה-before-spend לא יאכוף עליו כלום.
    for name in usage:
        if name.startswith("gemini") and name not in models:
            drift.append("%s: נקרא ב-%s אך אינו רשום במניפסט — אין לו "
                         "תקרה" % (name, usage[name]))
    return d, drift


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args()

    data = json.load(open(PROVIDERS, encoding="utf-8"))
    updated, drift = apply(data, scan_usage())

    if not drift:
        print("✓ אין drift — ‏in_use_by תואם את הקריאות בפועל")
        return 0
    for d in drift:
        print("✗ %s" % d)
    if a.check:
        print("\n‏drift בין המניפסט למציאות. להריץ: "
              "python tools/agents/gen-manifest.py --write")
        return 1
    with open(PROVIDERS, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    print("\nנכתב providers.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
