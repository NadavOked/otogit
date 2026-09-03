#!/usr/bin/env python3
"""‏`routing.order` כמנגנון — לא כמסמך.

**מה נמדד.** בלילה שבין 01/09 ל-02/09 נשרפו ~65K טוקנים של Codex
וקריאת Grok על **טריאז' וסיווג** — משימות ש-`ollama.recommended_for`
מצהיר עליהן במפורש, וכל אחת מהן הייתה רצה מקומית בכמה שניות בלי
לגעת באף מכסה. ‏`routing.order` היה כתוב, מנומק, והופר.

**הכלל של הבעלים (02/09):** משימה הולכת לשכבה הראשונה שמסוגלת לה,
ויורדת ברשימה רק כשהיא **אינה מסוגלת** — לא כשנוח יותר.

**איך זה נכשל — וזו הנקודה העדינה.** ‏`guard-bash.py` נכשל **סגור**:
כל ספק חוסם, כי המחיר של טעות שם הוא דיסק מחוק. כאן ההפך, ובכוונה:
**סירוב דורש ראיה חיובית.** טקסט שלא התאים לשום סוג מוצהר עובר, כי
הגַּיְס הזה רץ על כל פקודת מעטפת — שומר שחוסם על ספק היה חוסם את
העבודה כולה. זה אינו ויתור על עיקרון 5 אלא היישום הנכון שלו: העיקרון
דורש ראיה חיובית לפני שקובעים "בדקנו והכל תקין", וכאן הקביעה שדורשת
ראיה היא **הסירוב**. היעדר ראיה נאמר במפורש בפלט (`no-evidence`)
ואינו מוצג כאישור.

**מה מגן מפני נזק.** ‏`never_delegate_down` ב-providers.json מבטל
סירוב כשהטקסט נוגע במיזוג, ניפוי, חוזים, סודות או פריסה — הרשימה
של AGENTS.md, כדי שהמנגנון לא ידחוף למודל 3B משימה שאסור לה לרדת.

הנתונים — הסדר, מילות הראיה, פקודות השכבות — יושבים ב-providers.json
ולא כאן: הכרעה של הבעלים משתנה בקובץ, לא ב-if.

    python tools/agents/route-task.py --task "לסווג 40 issues לתוויות"
    python tools/agents/route-task.py --task "..." --tier codex_or_grok
    ... --hook            # מצב PreToolUse: קורא JSON מ-stdin

יציאה:  0 = מותר · 1 = סורב (שכבה נמוכה מסוגלת) · 2 = שגיאת שימוש
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDERS = os.path.join(HERE, "providers.json")

ALLOW, REFUSE, USAGE = 0, 1, 2


def load(path=None):
    with io.open(path or PROVIDERS, encoding="utf-8") as fh:
        return json.load(fh)


def _words(block):
    """כל מילות הראיה בגוש, בלי שדות ה-_he התיעודיים."""
    out = []
    for key, val in (block or {}).items():
        if key.startswith("_"):
            continue
        if isinstance(val, list):
            out.extend(val)
        elif isinstance(val, dict):
            out.extend(_words(val))
    return out


def matched_kinds(text, routing):
    """אילו סוגי משימה מוצהרים נמצאו בטקסט. ראיה חיובית בלבד."""
    low = text.lower()
    found = []
    for kind, block in (routing.get("task_kinds") or {}).items():
        if kind.startswith("_"):
            continue
        if any(w.lower() in low for w in _words(block)):
            found.append(kind)
    return sorted(found)


def blocked_from_descending(text, routing):
    """מילה מ-never_delegate_down — הסירוב מבוטל."""
    low = text.lower()
    hits = [w for w in _words(routing.get("never_delegate_down") or {})
            if w.lower() in low]
    return sorted(hits)


def lowest_capable(kinds, data):
    """השכבה הראשונה בסדר שמצהירה על אחד מהסוגים שנמצאו."""
    routing = data["routing"]
    for tier in routing["order"]:
        declared = set(data["providers"].get(tier, {}).get(
            "recommended_for") or [])
        if declared & set(kinds):
            return tier
    return None


def rank(tier, routing):
    order = routing["order"]
    return order.index(tier) if tier in order else len(order)


def decide(text, requested_tier=None, data=None):
    """מחזיר dict: verdict / tier / reason / kinds.

    verdict: allow · refuse · no-evidence
    """
    data = data or load()
    routing = data["routing"]
    kinds = matched_kinds(text, routing)
    if not kinds:
        return {"verdict": "no-evidence", "tier": None, "kinds": [],
                "reason": "לא נמצאה מילת ראיה לאף סוג משימה מוצהר. "
                          "אין בסיס להפנות למטה, ואין כאן אישור שהשכבה "
                          "הגבוהה נכונה — פשוט לא נבדק."}
    veto = blocked_from_descending(text, routing)
    if veto:
        return {"verdict": "allow", "tier": None, "kinds": kinds,
                "reason": "הטקסט נוגע ב-%s — ‏never_delegate_down "
                          "ב-AGENTS.md משאיר את זה על המנוי, גם עם "
                          "סימני %s." % (", ".join(veto), ", ".join(kinds))}
    low = lowest_capable(kinds, data)
    if low is None:
        return {"verdict": "no-evidence", "tier": None, "kinds": kinds,
                "reason": "נמצאו סימני %s, אך אף שכבה בסדר אינה מצהירה "
                          "על הסוגים האלה ב-recommended_for."
                          % ", ".join(kinds)}
    where = (routing.get("tier_endpoints") or {}).get(low, "")
    if requested_tier is None:
        return {"verdict": "allow", "tier": low, "kinds": kinds,
                "reason": "משימת %s → שכבה %s. %s"
                          % (", ".join(kinds), low, where)}
    if rank(requested_tier, routing) <= rank(low, routing):
        return {"verdict": "allow", "tier": requested_tier, "kinds": kinds,
                "reason": "‏%s אינה מעל %s בסדר." % (requested_tier, low)}
    return {"verdict": "refuse", "tier": low, "kinds": kinds,
            "reason": "משימת %s מוצהרת ב-%s.recommended_for, ו-%s נמצאת "
                      "מעליה ב-routing.order. הכלל של הבעלים: יורדים ברשימה "
                      "רק כשהשכבה אינה מסוגלת — לא כשנוח יותר. הפנה ל-%s"
                      % (", ".join(kinds), low, requested_tier, where or low)}


def argv_heads(command):
    """מילת הפקודה של כל קטע בשורה, בלי נתיב ובלי סיומת.

    ‏`codex` בתוך הודעת קומיט אינו קריאה ל-Codex. הריפו הזה כותב על
    הסוכנים שלו, ושומר שנחסם על אזכור הוא שומר שמכבים — ולכן
    ההתאמה היא במיקום הפקודה, לא במחרוזת חופשית.
    """
    heads = []
    for seg in re.split(r"\|\||&&|[;|\n&]", command):
        for tok in seg.strip().split():
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
                continue                    # השמות סביבה שלפני הפקודה
            tok = tok.strip("'\"")
            tok = re.split(r"[\\/]", tok)[-1].lower()
            if tok.endswith(".exe"):
                tok = tok[:-4]
            if tok:
                heads.append(tok)
            break
    return heads


def tier_of_command(command, routing):
    """איזו שכבה נקראת בשורת הפקודה, אם בכלל. הגבוהה ביותר מנצחת."""
    low = command.lower()
    heads = argv_heads(command)
    best = None
    for tier, spec in (routing.get("tier_commands") or {}).items():
        if tier.startswith("_"):
            continue
        if isinstance(spec, list):          # תאימות לצורה הישנה
            spec = {"argv": [], "anywhere": spec}
        hit = (any(a.lower() in heads for a in spec.get("argv") or [])
               or any(n.lower() in low for n in spec.get("anywhere") or []))
        if hit and (best is None or rank(tier, routing) > rank(best, routing)):
            best = tier
    return best


# ---- מצב hook: PreToolUse ------------------------------------------
def _emit(reason):
    """‏ASCII בלבד — ‏stdout של ווינדוס הוא cp1252, ועברית מפילה את
    הכתיבה. זה הבאג שהרג את הגרסה הראשונה של guard-bash."""
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}) + "\n")
    sys.stdout.flush()


def hook(stream=None, data=None):
    """חוסם קריאת CLI לשכבה גבוהה כשהטקסט נושא ראיה לשכבה נמוכה.

    שקט = מותר. בניגוד ל-guard-bash, כאן ספק אינו חסימה: הגַּיְס הזה
    רץ על כל פקודה, והחסימה שמורה לראיה חיובית בלבד.
    """
    try:
        payload = json.load(stream or sys.stdin)
        command = payload["tool_input"]["command"]
        if not isinstance(command, str):
            return 0
        data = data or load()
    except Exception:                                  # noqa: BLE001
        return 0
    routing = data["routing"]
    tier = tier_of_command(command, routing)
    if tier is None:
        return 0
    v = decide(command, tier, data)
    if v["verdict"] != "refuse":
        return 0
    _emit("route-task: refused. A lower tier already declares this work. "
          "kinds=%s lowest-capable=%s requested=%s. Nadav's rule (02/09): "
          "a task goes to the first tier able to do it and descends only "
          "when that tier CANNOT - not when it is more convenient. Send it "
          "to %s instead. If this really needs the higher tier, say why in "
          "the task text (words like debug/merge/contract lift the block)."
          % (",".join(v["kinds"]), v["tier"], tier,
             (routing.get("tier_endpoints") or {}).get(v["tier"], v["tier"])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="ניתוב משימה לפי routing.order")
    ap.add_argument("--task", help="תיאור המשימה")
    ap.add_argument("--tier", help="השכבה שמבקשים להריץ בה")
    ap.add_argument("--hook", action="store_true", help="מצב PreToolUse")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)
    if args.hook:
        return hook()
    if not args.task:
        ap.error("--task חובה (או --hook)")
    # ‏stdout של ווינדוס הוא cp1252 והנימוקים כאן עבריים. בלי זה
    # הכלי **קרס בזמן שהפסיקה כבר הייתה נכונה** — נמדד. זה אותו באג
    # שהרג את הגרסה הראשונה של guard-bash, ולכן מסלול ה-hook כותב
    # ‏ASCII בלבד ואינו תלוי בשורה הזאת.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    data = load()
    if args.tier and args.tier not in data["routing"]["order"]:
        sys.stderr.write("שכבה לא מוכרת: %r. הסדר: %s\n"
                         % (args.tier, ", ".join(data["routing"]["order"])))
        return USAGE
    v = decide(args.task, args.tier, data)
    if args.as_json:
        sys.stdout.write(json.dumps(v, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write("route-verdict: %s\n" % v["verdict"])
        sys.stdout.write("route-tier: %s\n" % (v["tier"] or "—"))
        sys.stdout.write("route-kinds: %s\n" % (", ".join(v["kinds"]) or "—"))
        sys.stdout.write("route-reason: %s\n" % v["reason"])
    return REFUSE if v["verdict"] == "refuse" else ALLOW


if __name__ == "__main__":
    sys.exit(main())
