#!/usr/bin/env bash
# הקצאה עצמית של משימה לסוכן — הצד המכני של AGENTS.md.
#
# הסוכן אינו בוחר: הסקריפט בוחר לפי הסדר הקבוע (חוסמי פריסה → bug →
# ‏enhancement → המספר הנמוך), תובע ב-`agent:claimed` + assignee, קורא
# **בחזרה**, ונסוג אם מישהו אחר תבע באותו רגע. ל-GitHub אין
# compare-and-swap על תוויות — זו נעילה מייעצת, והקריאה-בחזרה מצמצמת
# את החלון אך אינה סוגרת אותו. שובר שוויון: השם הקטן לקסיקוגרפית.
set -euo pipefail

# אין ברירת מחדל בכוונה: שם ריפו שהשתנה = תביעת Issues במקום הלא
# נכון, ובשקט. חסר ערך = עצירה, לא ניחוש.
REPO="${IMAGECTL_REPO:?IMAGECTL_REPO אינו מוגדר — אין ברירת מחדל}"

usage() {
    cat <<'EOF'
Usage:
  agent-claim.sh <agent-name>              תבע את המשימה הבאה בתור
  agent-claim.sh <agent-name> --release N  שחרר את Issue מספר N

שם הסוכן: ‏ASCII בלבד, למשל claude-pituach / codex-1 / gemini-a.
מודפס: מספר ה-Issue, הכותרת, וקבצים שכבר בבעלות PRs פתוחים (אסורים).
EOF
}

die() { echo "error: $*" >&2; exit 1; }

[ $# -ge 1 ] || { usage >&2; exit 2; }
case "$1" in -h|--help) usage; exit 0;; esac
AGENT="$1"; shift
[[ "$AGENT" =~ ^[A-Za-z0-9._-]{2,32}$ ]] || die "שם סוכן: ‏ASCII בלבד, 2-32 תווים"

if [ "${1:-}" = "--release" ]; then
    [ $# -eq 2 ] || { usage >&2; exit 2; }
    [[ "$2" =~ ^[0-9]+$ ]] || die "מספר Issue חייב להיות ספרות"
    gh issue edit "$2" --repo "$REPO" --remove-label "agent:claimed" >/dev/null
    gh issue comment "$2" --repo "$REPO" \
        --body "🔓 שוחרר על ידי הסוכן \`$AGENT\` — חוזר לתור." >/dev/null
    echo "released #$2"
    exit 0
fi
[ $# -eq 0 ] || { usage >&2; exit 2; }

# ‏python3 לא קיים בווינדוס — שם הוא python. כשל בפענוח חייב להיות
# רועש: פייתון שנפל בצינור נראה בדיוק כמו "תור ריק" (עיקרון 5;
# נתפס בפועל בבדיקה הראשונה של הסקריפט הזה).
PY_BIN=$(command -v python3 || command -v python) || die "אין python בנתיב"

# --- בחירה: ready, לא claimed, לפי הסדר של AGENTS.md ------------------
pick() {
    gh issue list --repo "$REPO" --label "agent:ready" --state open \
        --json number,title,labels,milestone --limit 100 \
    | "$PY_BIN" -c '
import json, sys
issues = json.load(sys.stdin)
def rank(i):
    labels = {l["name"] for l in i["labels"]}
    if "agent:claimed" in labels or "agent:blocked" in labels:
        return None
    ms = (i.get("milestone") or {}).get("title", "")
    kind = 0 if "bug" in labels else 1 if "enhancement" in labels else 2
    return (0 if "חוסמי פריסה" in ms else 1, kind, i["number"])
ranked = sorted((r, i) for i in issues if (r := rank(i)) is not None)
if ranked:
    i = ranked[0][1]
    print("PICK", i["number"], i["title"])
else:
    print("EMPTY")
'
}

PICKED=$(pick) || die "הבורר עצמו נכשל — זה אינו תור ריק"
case "$PICKED" in
    EMPTY) echo "התור ריק — אין Issue עם agent:ready פנוי."; exit 3 ;;
    PICK\ *) read -r _ NUM TITLE <<< "$PICKED" ;;
    *) die "פלט לא צפוי מהבורר: $PICKED" ;;
esac

# --- תביעה, ואז קריאה בחזרה (עיקרון 5: לא סומכים על שהפקודה הצליחה) ---
gh issue edit "$NUM" --repo "$REPO" --add-label "agent:claimed" >/dev/null
gh issue comment "$NUM" --repo "$REPO" \
    --body "🔒 נתבע על ידי הסוכן \`$AGENT\`. שובר שוויון: השם הקטן לקסיקוגרפית מנצח." >/dev/null

sleep 2   # חלון קצר כדי שתביעה מקבילה תספיק להירשם לפני הקריאה-בחזרה

# רק תביעות מאז השחרור (‏🔓) האחרון מצביעות. בלי זה, תגובת תביעה
# ישנה — שבעליה כבר שחרר — מנצחת תובע חדש לפי האלפבית, והחדש נסוג
# ממשימה פנויה (ממצא סקירת Gemini על PR #209, במנגנון מתוקן).
CLAIMANTS=$(gh issue view "$NUM" --repo "$REPO" --json comments     -q '[.comments[] | .body]'     | "$PY_BIN" -c '
import json, re, sys
names = []
for b in json.load(sys.stdin):
    if b.startswith("🔓"):        # 🔓 שחרור — תביעות קודמות מתות
        names = []
    elif b.startswith("🔒") and (m := re.search(r"`([A-Za-z0-9._-]+)`", b)):
        names.append(m.group(1))
print("
".join(dict.fromkeys(names)))
')
WINNER=$(printf '%s\n' "$CLAIMANTS" | sort | head -1)
[ -n "$WINNER" ] || die "לא נמצאה תביעה אחרי כתיבה — קריאת ה-API נכשלה"

if [ "$WINNER" != "$AGENT" ]; then
    echo "‏#$NUM כבר נתבע על ידי '$WINNER' — נסוג." >&2
    gh issue comment "$NUM" --repo "$REPO" \
        --body "↩️ ‏\`$AGENT\` נסוג — '\''$WINNER'\'' תבע ראשון לפי שובר השוויון." >/dev/null
    exit 4
fi

# --- הפלט: המשימה + הקבצים האסורים ------------------------------------
echo "CLAIMED  #$NUM  $TITLE"
echo
echo "קבצים בבעלות PRs פתוחים — אסור לגעת בהם:"
gh pr list --repo "$REPO" --state open --json number,files \
    -q '.[] | .number as $n | .files[] | "  \(.path)  (PR #\($n))"' | sort -u
echo
echo "לפני עבודה: קרא AGENTS.md · CLAUDE.md · CONTRIBUTING.md · gh issue view $NUM"
echo "בסיום: gh pr create, דוח ב-tools/discuss.sh, ולא למזג."
