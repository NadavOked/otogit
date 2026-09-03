#!/usr/bin/env bash
# השער שבין "הסוכן סיים" ל"נפתח PR" — פסק-דין מכונה, לא שדה טקסט.
#
# שלושה פסקי-דין, לא שניים:
#
#   pass                  — פקודת הראיות רצה והחזירה 0
#   fail                  — רצה והחזירה שגיאה. ‏PR לא נפתח: אין body
#   insufficient_evidence — לא ניתן היה להריץ אותה. אינו pass ואינו
#                           fail, ואינו ניתן להשתקה — הוא מוטבע ב-body
#
# ההבחנה השלישית היא הפואנטה: "לא הצלחנו לבדוק" ו"בדקנו ונכשל" הם
# שני מצבים שונים (עיקרון 5), וקיפולם ל-fail היה מזמין עקיפה, וקיפולם
# ל-pass היה שקר.
#
# שימוש (הפלט הוא ה-body; על fail אין פלט והשרשור נעצר):
#   body=$(tools/agents/gate-pr.sh \
#       --evidence-cmd "python -m pytest tests -q" \
#       --verified "..." --unverified "...") && gh pr create --body "$body" ...
#
# האכיפה שאי-אפשר להשתיק אינה כאן — היא ב-pr-gate.yml: ‏PR מענף
# ‏auto/* שה-body שלו בלי פסק-דין תקף נצבע אדום בצד השרת.
set -euo pipefail

EVIDENCE_CMD=""; VERIFIED=""; UNVERIFIED=""
while (($#)); do
    case "$1" in
        --evidence-cmd) EVIDENCE_CMD="${2:-}"; shift 2 ;;
        --verified) VERIFIED="${2:-}"; shift 2 ;;
        --unverified) UNVERIFIED="${2:-}"; shift 2 ;;
        *) echo "ארגומנט לא מוכר: $1" >&2; exit 2 ;;
    esac
done
# אותו כלל כמו ב-task-log: השדה חובה. ריק = לא נשאלה השאלה.
if [ -z "$UNVERIFIED" ]; then
    echo "error: --unverified חובה. אם הכול אומת — כתוב זאת ונמק." >&2
    exit 2
fi

VERDICT=""; EXIT_CODE=""; NOTE=""
if [ -z "$EVIDENCE_CMD" ]; then
    VERDICT="insufficient_evidence"
    NOTE="לא נמסרה פקודת ראיות"
else
    set +e
    bash -c "$EVIDENCE_CMD" > /dev/null 2>&1
    EXIT_CODE=$?
    set -e
    if [ "$EXIT_CODE" -eq 0 ]; then
        VERDICT="pass"
    elif [ "$EXIT_CODE" -eq 127 ]; then
        # הפקודה עצמה לא קיימת — הבדיקה לא רצה. זה אינו כישלון של
        # הקוד הנבדק, וזה גם אינו אישור שלו.
        VERDICT="insufficient_evidence"
        NOTE="פקודת הראיות אינה קיימת (exit 127) — הבדיקה לא רצה כלל"
    else
        # נבדק ונכשל. אין body, אין PR — והסיבה נאמרת בקול.
        echo "gate-verdict: fail (exit $EXIT_CODE) — ‏PR לא ייפתח עם קוד שנבדק ונכשל." >&2
        exit 1
    fi
fi

printf '## פסק-דין שער\n\n'
printf 'gate-verdict: %s\n' "$VERDICT"
[ -n "$EVIDENCE_CMD" ] && printf 'evidence-cmd: `%s`\n' "$EVIDENCE_CMD"
[ -n "$EXIT_CODE" ] && printf 'exit: %s\n' "$EXIT_CODE"
[ -n "$NOTE" ] && printf 'note: %s\n' "$NOTE"
printf 'verified: %s\n' "${VERIFIED:-—}"
printf 'unverified: %s\n' "$UNVERIFIED"
