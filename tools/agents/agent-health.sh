#!/usr/bin/env bash
# בדיקת בריאות לצי הסוכנים — מי עונה, מי מקורר, ומי פשוט לא שם.
#
# **למה זה לא "רשימה":** סוכן שאינו מותקן וסוכן שהמכסה שלו נגמרה
# נראים אותו דבר מבחוץ — שניהם לא עונים. הכלי הזה מפריד ביניהם, כי
# התגובה שונה: הראשון דורש התקנה, השני דורש להמתין.
set -euo pipefail

STATE="${OTOGIT_STATE:-$HOME/.otogit-agents.json}"

check() {   # $1 = שם, $2 = נתיב לבינארי (ריק = לא רלוונטי)
    local name="$1" bin="$2" status
    if [ -n "$bin" ] && [ ! -x "$bin" ]; then
        status="לא מותקן"
    elif [ -r "$STATE" ] && grep -q "cooldown_$name" "$STATE" 2>/dev/null; then
        # קירור פעיל אינו כשל — הוא מצב זמני שיפוג מעצמו.
        status="מקורר (מכסה)"
    else
        status="זמין"
    fi
    printf '%-12s %s\n' "$name" "$status"
}

echo "בריאות הצי — $(date -u +%H:%M:%SZ)"
check grok   "${GROK_BIN:-$HOME/.grok/bin/grok.exe}"
check codex  "${CODEX_BIN:-$APPDATA/npm/codex.cmd}"
check gemini ""
echo
if [ -r "$STATE" ]; then
    echo "קובץ מצב: $STATE"
else
    # היעדר קובץ מצב אינו שגיאה — הוא נוצר בכיבוי/קירור ראשון.
    echo "קובץ מצב: אינו קיים עדיין (אף סוכן לא כובה ולא קורר)"
fi
