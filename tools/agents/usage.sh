#!/usr/bin/env bash
# מונה שימוש אחיד לכל הסוכנים — כמה נשרף, ומה זה עלה.
#
# **למה זה לא נוחות:** "המנוי לא חורג" ו"ראינו כמה נשרף" הם שני
# דברים שונים. הראשון מגן מפני חשבונית; רק השני מאפשר לדעת שמכסה
# הולכת לאיבוד על משימות שלא היו שוות אותה, ולפני שנגמרת.
#
# שלושת הסוכנים מדווחים — פשוט לא באותו מקום ולא באותו שם:
#   Codex   `codex exec --json`        → turn.completed.usage
#   Grok    `grok --output-format json` → usage + total_cost_usd
#   Gemini  תשובת ה-API                 → usageMetadata
#
# שימוש:  usage.sh <codex|grok|gemini> <קובץ-פלט>
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }
[ $# -eq 2 ] || die "usage: usage.sh <codex|grok|gemini> <file>"
AGENT="$1"; FILE="$2"
[ -r "$FILE" ] || die "לא ניתן לקרוא: $FILE"

PY=$(command -v python3 || command -v python) || die "אין python בנתיב"

# הפרסור בפייתון ולא ב-jq: jq אינו מותקן בכל מקום, ומחרוזות בתוך
# ביטוי jq נשברות בדרך מ-PowerShell (נמדד — הפיל את agent-runner).
"$PY" - "$AGENT" "$FILE" <<'PY'
import io, json, sys
agent, path = sys.argv[1], sys.argv[2]
raw = io.open(path, encoding="utf-8", errors="replace").read()

def emit(inp, out, extra, cost=None):
    total = (inp or 0) + (out or 0)
    line = f"{agent}: input={inp} output={out} {extra} total={total}"
    if cost is not None:
        line += f" cost=${cost:.5f}"
    print(line)

if agent == "codex":
    # JSONL — הרשומה האחרונה מסוג turn.completed נושאת את הסיכום.
    u = None
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if o.get("type") == "turn.completed" and "usage" in o:
            u = o["usage"]
    if u is None:
        sys.exit("codex: לא נמצאה רשומת turn.completed — אין מדידה, ולא מניחים אפס")
    emit(u.get("input_tokens"), u.get("output_tokens"),
         f"cached={u.get('cached_input_tokens', 0)} reasoning={u.get('reasoning_output_tokens', 0)}")

elif agent == "grok":
    start = raw.find("{")
    if start < 0:
        sys.exit("grok: לא נמצא JSON בפלט")
    o = json.loads(raw[start:])
    u = o.get("usage") or {}
    if not u:
        sys.exit("grok: הפלט בלי שדה usage — אין מדידה")
    emit(u.get("input_tokens"), u.get("output_tokens"),
         f"cached={u.get('cache_read_input_tokens', 0)} reasoning={u.get('reasoning_tokens', 0)}",
         o.get("total_cost_usd"))

elif agent == "gemini":
    o = json.loads(raw)
    u = o.get("usageMetadata") or {}
    if not u:
        sys.exit("gemini: התשובה בלי usageMetadata — אין מדידה")
    emit(u.get("promptTokenCount"), u.get("candidatesTokenCount"),
         f"thoughts={u.get('thoughtsTokenCount', 0)}")

else:
    sys.exit(f"סוכן לא מוכר: {agent}")
PY
