---
name: bakara-shlilit
description: נוהל הבקרה השלילית — איך מוכיחים שטסט באמת תופס את הבאג. הפעל לפני כל PR שמשנה התנהגות, וכשצריך למלא את סעיף "בקרה שלילית" בגוף ה-PR.
model: opus
effort: medium
user-invocable: true
---

# בקרה שלילית — הנוהל

## English summary (for agents that do not read Hebrew)

**"Negative control" (bakara shlilit) is mandatory in this repo before any
behaviour-changing PR.** A test you have never watched fail is not a test.

Procedure: (1) write the test; (2) revert ONLY the fix, back to the base
commit; (3) prove the fix is gone with positive evidence — `grep -c` on the
removed symbol must print `0`; (4) run the suite and capture the literal
failure output; (5) restore the fix and run again.

Hard rules:
- The failure must be **behavioural** — an `ImportError`, a missing file or a
  collection error is **NOT** a negative control. It proves the test did not
  run, not that it checks anything. This has happened twice here.
- **Never** use `git checkout -- <path>` after `git add`: it restores from the
  index, so the fix is silently still there and the test prints `passed`.
  Use `git checkout <base-sha> -- <path>`.
- Also report **how many tests pass in BOTH states**. Those are the guards
  against an over-broad "fix" that rejects everything.
- If the control did not fail, the test is void. Fix the test — do not report
  "passed".
- Docs/CI/comment-only changes: write "no behaviour change" and say why.
- Put the result table in the PR body (format below).

---

<div dir="rtl">

## מתי זה חל

| מצב | בקרה שלילית |
|---|---|
| תיקון באג | **חובה** |
| טסט חדש על קוד קיים | **חובה** — אחרת אינך יודע שהוא בודק משהו |
| יכולת חדשה | חובה על הטסט שמגן עליה |
| תיעוד / הערות / `.github` בלבד | כותבים "אין שינוי התנהגות" **ולמה** |

**‏PR בלי בקרה שלילית שאין לו את הפטור הזה אינו עובר.** לפי
`tools/agents/POLICY.md`, "כל דבר שאין לו בקרה שלילית" יוצא מסמכות המתאם
ועובר להכרעת הבעלים.

## ארבעת השלבים

1. **כותבים את הטסט.**
2. **מחזירים את הקוד למצב שלפני התיקון** — ורק אותו.
3. **מריצים, ומראים את פלט הכישלון המילולי.**
4. **מחזירים, ומריצים שוב.**

```bash
base=$(git merge-base HEAD origin/main)

# 2 — החזרה. שים לב לצורה, לא ל-`--`.
git checkout "$base" -- projects/imagectl/server/agentctl/validator.py

# 3 — ראיה חיובית שהתיקון באמת איננו, לפני שמריצים בכלל
grep -c '_is_substantiated' projects/imagectl/server/agentctl/validator.py     # חייב 0

TMPDIR=/root/<שלך>-tmp python3 -m pytest tests/test_agentctl.py -q   # חייב לכשול

# 4 — שחזור
git checkout HEAD -- projects/imagectl/server/agentctl/validator.py
grep -c '_is_substantiated' projects/imagectl/server/agentctl/validator.py     # חייב > 0
TMPDIR=/root/<שלך>-tmp python3 -m pytest tests/test_agentctl.py -q   # חייב לעבור
```

## הכישלון חייב להיות התנהגותי

‏`ImportError`, קובץ חסר, או שגיאת collection — **אינם בקרה שלילית**. הם
מוכיחים שהטסט **לא רץ**, לא שהוא בודק משהו. זה קרה כאן פעמיים, ובשתי
הפעמים הטסט היה חסר ערך.

מה שכן נחשב: `AssertionError` עם הערכים בפועל, קוד תשובה שגוי, מונה שלא
זז, ערך שנקרא בחזרה ואינו מה שנכתב.

```
E  AssertionError: assert True is False
   double_check_satisfied(..., RiskLevel.CRITICAL, checks={}, checks={})
FAILED test_two_empty_results_are_not_a_double_check
```

## סופרים גם את מה שעובר בשני המצבים

זה החצי שנשכח. אם תחת המוטציה **הכול** נכשל — התיקון שלך כנראה דוחה
הכול, וה"טסט" רק מאשר שהמתג כבוי. ‏PR ‏#232 מדד `11 passed` תחת מוטציה
A, כולל הצד החיובי — וזו הראיה שאין תיקון-יתר.

## שתי המלכודות שכבר עלו כאן ביוקר

### 1. ‏`git checkout -- <path>` אחרי `git add` משחזר מה-index

לא מ-HEAD. התיקון **נשאר במקומו**, הבקרה מדפיסה `passed`, והדוח יוצא
משכנע ושקרי.

**הצורה הנכונה:** ‏`git checkout <base-sha> -- <path>`, ואחריה
**`grep -c` על הסמל שהוסר** כראיה חיובית שהוא באמת איננו. היעדר שגיאה
מ-`git checkout` אינו ראיה — עיקרון 5.

### 2. עבודה גמורה שנשארת staged ולא נדחפת

שני PRs כאן הראו קוד ישן בזמן שהתיקון היה staged. **אחרי `push`, בודקים
את ה-remote** ולא את עץ העבודה:

```bash
git show origin/<ענף>:<קובץ> | grep -c '<הסמל>'
```

## מוטציות — כשאין "לפני" נקי

כשהטסט מגן על קוד שאתה כותב עכשיו, אין קומיט קודם להחזיר אליו. אז
**מנטרלים ידנית**, מוטציה אחת בכל פעם, ומודדים כל אחת בנפרד. ‏PR ‏#227
החליף `if ($afterBytes -lt $minFreeBytes)` ב-`if ($false)` וקיבל כשל
התנהגותי אחד ומדויק.

לכל מוטציה: מה נוטרל · ‏`grep -c` לפני ואחרי · אילו טסטים נכשלו · כמה
עברו בכל זאת.

## פורמט הטבלה ל-PR

זה הפורמט שבו נכתבו ‏#219, ‏#227 ו-#232. שלוש עמודות, כשיש יותר ממוטציה
אחת:

```markdown
## בקרה שלילית — N מוטציות, כשל התנהגותי בכולן

| מוטציה | ראיה חיובית שהוסרה | תוצאה |
|---|---|---|
| ‏A. `_is_substantiated` מנוטרל | ‏4→1 מופעים | **4 failed**, 11 passed |
| ‏B. `bool(results)` הוסר | ‏1→0 | **1 failed**, 14 passed |
| ‏C. `try/except` הוסר | ‏1→0 | **1 failed**, 14 passed |
```

ומתחתיה **פלט הכישלון המילולי** בבלוק קוד, ומשפט שאומר כמה עברו בכל
המצבים ולמה זה מרגיע.

כשיש מוטציה אחת בלבד, שתי עמודות מספיקות — כך נכתב #219:

```markdown
| מה | תוצאה |
|---|---|
| השומר, על main הלא-מתוקן | **נכשל** — בבידוד ובחבילה המלאה (`1 failed, 1414 passed`) |
| השומר, עם התיקון | עובר |
| חבילה מלאה עם התיקון | **`1415 passed` × 2**, מעבדת ה-VM, אפס דילוגים |
```

## מה מדווחים בשרשור

בחוזה הפלט של `AGENTS.md`, השדה `בקרה שלילית` מקבל את **פלט הכישלון
המילולי**, או את המילים `לא רצה` **ולמה**. שדה ריק אינו דוח.

## מדיניות כישלון

| מצב | מה עושים |
|---|---|
| הבקרה לא נכשלה | **הטסט פסול.** לתקן אותו, לא לדווח "עבר" |
| הכישלון הוא ImportError | לא בקרה. הטסט לא רץ — לבדוק למה |
| ‏`grep -c` החזיר > 0 אחרי ההחזרה | התיקון לא הוסר. כנראה מלכודת 1 |
| אין דרך להריץ | **לא מדווחים "עבר".** לומר "לא רצה" ולמה |

</div>
