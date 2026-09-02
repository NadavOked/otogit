#!/usr/bin/env bash
# יומן משימות — רשומה אחת לכל משימה, ב-logs/YYYY-MM-DD.md.
#
# הכלל חל על **כל** הסוכנים ועל המתאם. הסיבה אינה תיעוד לשמו: סוכן
# שנגמרו לו הטוקנים, מכסה שנסגרה, או סשן שנסגר — משאירים אחריהם רק
# את הקובץ הזה. מי שממשיך קורא אותו במקום לנחש מה קרה.
#
# הכתיבה היא append בלבד: רשומה שנכתבה אינה נמחקת ואינה נערכת.
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: task-log.sh --agent <שם> --task <#N|תיאור> --status <done|failed|blocked|partial> [שדות]

שדות (כולם אופציונליים חוץ מהחובה למעלה):
  --asked <טקסט>       מה המשתמש ביקש (בלשונו, לא בפרשנות)
  --changed <טקסט>     הפעולות המרכזיות שבוצעו
  --files <רשימה>      קבצים או מערכות ששונו
  --decided <טקסט>     החלטות והנחות משמעותיות, ולמה
  --failed <טקסט>      שגיאות וניסיונות שנכשלו  ← לא למחוק, זה המידע
  --tests <טקסט>       בדיקות ואימות שבוצעו, והיכן
  --unverified <טקסט>  מה לא אומת   ← שדה חובה, ראה למטה
  --automate <טקסט>    מה חזר על עצמו וכדאי להפוך לאוטומציה
  --next <טקסט>        הצעד הבא הצפוי
  --pr <#N>            PR שנפתח

דוגמה:
  tools/agents/task-log.sh --agent claude --task "#218" --status done \
    --changed "סימן היתר לשומר הפורטים" --tests "1415 עוברים ×2, מעבדת ה-VM" \
    --unverified "כשל id() לא שוחזר" --pr "#219"
EOF
}

AGENT=""; TASK=""; STATUS=""; ASKED=""; CHANGED=""; FILES=""; DECIDED=""
FAILED=""; TESTS=""; UNVERIFIED=""; AUTOMATE=""; NEXT=""; PR=""
while (($#)); do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --agent) AGENT="${2:-}"; shift 2 ;;
        --task) TASK="${2:-}"; shift 2 ;;
        --status) STATUS="${2:-}"; shift 2 ;;
        --asked) ASKED="${2:-}"; shift 2 ;;
        --changed) CHANGED="${2:-}"; shift 2 ;;
        --files) FILES="${2:-}"; shift 2 ;;
        --decided) DECIDED="${2:-}"; shift 2 ;;
        --failed) FAILED="${2:-}"; shift 2 ;;
        --tests) TESTS="${2:-}"; shift 2 ;;
        --unverified) UNVERIFIED="${2:-}"; shift 2 ;;
        --automate) AUTOMATE="${2:-}"; shift 2 ;;
        --next) NEXT="${2:-}"; shift 2 ;;
        --pr) PR="${2:-}"; shift 2 ;;
        *) echo "ארגומנט לא מוכר: $1" >&2; usage >&2; exit 2 ;;
    esac
done
[ -n "$AGENT" ] && [ -n "$TASK" ] && [ -n "$STATUS" ] \
    || { echo "חסר --agent / --task / --status" >&2; usage >&2; exit 2; }
case "$STATUS" in done|failed|blocked|partial) ;; *)
    echo "status חייב להיות done/failed/blocked/partial" >&2; exit 2 ;;
esac

# "לא אומת" ריק הוא הטענה החזקה ביותר שאפשר לטעון — ולכן היא דורשת
# מילים מפורשות. סוכן שמשאיר את השדה ריק כנראה לא שאל את עצמו.
if [ -z "$UNVERIFIED" ]; then
    echo "error: --unverified הוא שדה חובה. אם באמת הכול אומת — כתוב זאת ונמק." >&2
    exit 2
fi

# הריפו ציבורי. סוד שנכנס ליומן נשאר בהיסטוריה גם אחרי מחיקה, ולכן
# הסינון כאן ולא בזיכרון של מי שכותב. מתארים את **סוג** המידע, לא ערך.
ALL_TEXT="$ASKED $CHANGED $FILES $DECIDED $FAILED $TESTS $UNVERIFIED $AUTOMATE $NEXT"
if printf '%s' "$ALL_TEXT" | grep -qiE 'AQ\.[A-Za-z0-9_-]{20}|AIza[A-Za-z0-9_-]{20}|gh[pousr]_[A-Za-z0-9]{20}|github_pat_[A-Za-z0-9_]{30}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10}|sk_live_[0-9a-zA-Z]{20}|sk-[A-Za-z0-9]{20}|-----BEGIN [A-Z ]*PRIVATE KEY'; then
    echo "error: היומן מכיל מה שנראה כמו סוד. תאר את סוג המידע, לא את הערך." >&2
    exit 3
fi

# כל ערך משוטח לשורה אחת: שורה חדשה שוברת את רשימת ה-Markdown, וערך
# שמתחיל ב-## מזריק כותרת ומזייף רשומה. ממצא סקירת Gemini על #218.
flat() { printf '%s' "$1" | tr '
	' '   ' | sed 's/  */ /g; s/^ *//; s/ *$//'; }
ASKED=$(flat "$ASKED"); CHANGED=$(flat "$CHANGED"); FILES=$(flat "$FILES")
DECIDED=$(flat "$DECIDED"); FAILED=$(flat "$FAILED"); TESTS=$(flat "$TESTS")
UNVERIFIED=$(flat "$UNVERIFIED"); AUTOMATE=$(flat "$AUTOMATE"); NEXT=$(flat "$NEXT")

ROOT=$(git rev-parse --show-toplevel)
DAY=$(date -u +%Y-%m-%d)
FILE="$ROOT/logs/$DAY.md"
mkdir -p "$ROOT/logs"
[ -s "$FILE" ] || printf '# יומן משימות — %s\n\nרשומות נוספות בסוף. אין עריכה של רשומה שנכתבה.\n' "$DAY" > "$FILE"

{
    printf '\n## %s — %s — %s\n\n' "$(date -u +%H:%M:%SZ)" "$AGENT" "$TASK"
    printf -- '- **סטטוס:** %s
' "$STATUS"
    [ -n "$ASKED"      ] && printf -- '- **מה בוקש:** %s
' "$ASKED"
    [ -n "$CHANGED"    ] && printf -- '- **מה בוצע:** %s
' "$CHANGED"
    [ -n "$FILES"      ] && printf -- '- **קבצים:** %s
' "$FILES"
    [ -n "$DECIDED"    ] && printf -- '- **הוכרע:** %s
' "$DECIDED"
    [ -n "$FAILED"     ] && printf -- '- **נכשל בדרך:** %s
' "$FAILED"
    [ -n "$TESTS"      ] && printf -- '- **נבדק (והיכן):** %s
' "$TESTS"
    printf -- '- **לא אומת:** %s
' "$UNVERIFIED"
    [ -n "$AUTOMATE"   ] && printf -- '- **מועמד לאוטומציה:** %s
' "$AUTOMATE"
    [ -n "$NEXT"       ] && printf -- '- **הצעד הבא:** %s
' "$NEXT"
    [ -n "$PR"         ] && printf -- '- **PR:** %s
' "$PR"
} >> "$FILE"

echo "$FILE"
