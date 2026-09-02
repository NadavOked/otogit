<div dir="rtl">

# otogit — תשתית אוטומציה לסוכני AI

[![tests](https://github.com/NadavOked/otogit/actions/workflows/tests.yml/badge.svg)](https://github.com/NadavOked/otogit/actions/workflows/tests.yml)
[![gitleaks](https://github.com/NadavOked/otogit/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/NadavOked/otogit/actions/workflows/gitleaks.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

כלים שמאפשרים לסוכני AI לעבוד על ריפו **בלי שאדם יושב מעליהם** —
ובלי שהם יוכלו לשבור משהו בשקט.

**נולד בפרויקט אמיתי**, שם הוא רץ בייצור: רעיון בדיון נהיה Issue,
סוכן לוקח אותו מהתור, כותב, נסקר אוטומטית, ופותח PR — הכול בלי אדם
באמצע. הכלים כאן הם החלק שאינו יודע דבר על אותו פרויקט.

---

## מה יש כאן

| כלי | מה הוא עושה |
|---|---|
| `tools/agents/task-log.sh` | רשומת יומן לכל משימה. השדה **"לא אומת" הוא חובה** והכלי מסרב בלעדיו |
| `tools/agents/usage.sh` | כמה טוקנים נשרפו — ‏Codex / ‏Grok / ‏Gemini, בשורה אחידה |
| `tools/agents/quota-lib.ps1` | מכסה שנגמרה → קירור עצמי → **התעוררות אוטומטית** באיפוס |
| `tools/agents/agents-ctl.ps1` | מתג on/off לכל סוכן בנפרד |
| `tools/discuss.sh` | דיווח סוכן ללוח דיונים משותף |
| `tools/after-merge-check.sh` | **‏PR ירוק אינו main ירוק** — בודק את הריצה שאחרי המיזוג |
| `.github/workflows/agent-review.yml` | סקירה אדוורסרית אוטומטית לכל PR |
| `.github/workflows/idea-to-issue.yml` | רעיון בקטגוריית Ideas → Issue עם metadata מלא |
| `.github/workflows/agent-daily.yml` | דוח בוקר ללוח הדיונים |

## העיקרון שמאחורי הכול

> **פעולה שלא הצליחה לבדוק — נכשלה, לא ויתרה.**

"לא הצלחנו לבדוק" ו"בדקנו, הכל תקין" הם שני מצבים שונים, ואסור לקפל
אותם לאחד. כל כלי כאן מיישם את זה:

- ‏`usage.sh` יוצא **1** כשאין שדה `usage` — לא מדווח אפס
- ‏`after-merge-check.sh` יוצא **1** על **אפס** בדיקות — "לא מצאתי
  בדיקות" אינו "הכול עבר"
- ‏`task-log.sh` **מסרב** לרשומה בלי `--unverified`
- הסוקר האוטומטי **נכשל ברעש** כשה-API לא ענה — סקירה שלא רצה אינה
  סקירה שעברה

הכללים האלה לא נכתבו מראש. **כל אחד מהם נולד מכשל אמיתי בייצור.**

## מלכודות

[`PITFALLS.md`](PITFALLS.md) — שבע מלכודות שכל אחת עלתה בזמן אמת:
‏`
` בתוך heredoc · ‏`set -e` שאינו חל על `! cmd` · ‏PowerShell שמוחק
מרכאות · ‏`git checkout --` שמשחזר מה-index · עבודה שנשארת בלי push ·
קוד יציאה 0 שאינו אומר כלום · ‏`id()` ממוחזר.

## הגדרות

[`CONFIG.md`](CONFIG.md) — איפה כל דבר יושב: נתיבי הסוכנים, תיקיית
המודלים המקומיים, מספרי השרשורים, ואיזה מודל לאיזו משימה (לפי
מדידת מהירות, לא לפי גודל). ‏`config.example.json` הוא התבנית.

**שום מפתח אינו נכנס לשם** — רק **שם** משתנה הסביבה שמחזיק אותו.

## שימוש

```bash
export OTOGIT_REPO="owner/repo"     # חובה — הכלים אינם מנחשים ריפו

tools/agents/task-log.sh --agent grok --task "#42" --status done \
  --changed "..." --tests "..." --unverified "..."

tools/agents/usage.sh grok run.json
tools/after-merge-check.sh
```

לסקירה האוטומטית: הסוד `GEMINI_API_KEY` בהגדרות הריפו. כללי הפרויקט
המארח נקראים מ-`.otogit/review-rules.txt` אם הוא יצר אותו — התשתית
אינה יודעת מה אסור אצלך, אתה אומר לה.

## מה שאין כאן, בכוונה

**קוד שמכיר פרויקט מסוים.** ‏`lab-work-checkout.sh` (מכיר שרת מסוים
ספציפי), ‏`pull-model.ps1` (‏Ollama מקומי) ו-`server/agentctl/` נשארו
בפרויקט המקור. כלי שמנחש ריפו או נתיב יכתוב למקום הלא נכון, ובשקט.

</div>
