---
name: hariza-bemaabada
description: הרצת חבילת הבדיקות של ImageCtl על מעבדת ה-VM — עץ עבודה מאומת, TMPDIR משלך, ומה נחשב ריצה ירוקה. הפעל לפני כל טענת "הטסטים עוברים", ולפני מילוי סעיף האימות ב-PR.
model: opus
effort: medium
user-invocable: true
---

# הרצה על מעבדת ה-VM

## English summary (for agents that do not read Hebrew)

**The test suite runs on the VM lab, not on the Windows dev workstation.**
On Windows `test_fanout` is skipped and `WinError 50` breaks the multi-file
run (#14), so a Windows run is not evidence.

Three rules:
1. **Create the work tree with `tools/git/lab-work-checkout.sh <issue-number>`.**
   A plain `git clone --shared` can inherit a stale `main` and **succeed
   silently** — measured, 8 commits behind, exit code 0 (#190).
2. **`TMPDIR` of your own is mandatory.** `/tmp` on the lab is a 2 GB tmpfs
   that has already broken three runs.
   `TMPDIR=/root/<yours>-tmp python3 -m pytest tests -q`
3. **One green run is not evidence. Run twice minimum; ten times for a
   timing-dependent test.** A manager once reported "827 passing" for a test
   that failed 4 runs out of 5.

Always state WHERE it ran ("passes on the VM lab", never just "passes"), and
report skips: "N passed, zero skipped". A skip is not a pass.

---

<div dir="rtl">

## למה לא על תחנת הפיתוח

| | תחנת הפיתוח (ווינדוס) | מעבדת ה-VM |
|---|---|---|
| `test_fanout` | **מדולג** (אין gcc) | רץ |
| ריצה רב-קבצית | **‏`WinError 50`** (#14) | רצה |
| ‏Python | ‏3.12 | ‏3.13 — כמו הייצור |
| כרטיסי רשת וספריות | שונים | כמו דביאן 13 בייצור |

**"עובר במעבדה" אינו "עובר ב-CI", ו"עובר בווינדוס" אינו עובר.** אומרים
**היכן** נבדק, תמיד. הריצה על ווינדוס לגיטימית לקובץ בודד תוך כדי
עבודה — היא אינה טענת אימות.

## שלב 1 — עץ עבודה שאינו יכול לרשת ref מיושן

```bash
tools/git/lab-work-checkout.sh <מספר-Issue> [--host root@$IMAGECTL_LAB_HOST] [--key <נתיב>] [--force]
```

יוצר `/root/ic-<N>` **ו-`/root/ic-<N>-tmp`** על המעבדה, ומאמת שה-HEAD של
העץ החדש זהה בדיוק ל-`origin/main` שנמשך זה עתה. אם לא — יציאה שאינה
אפס, עם שני ה-sha בהודעה.

**למה לא `git clone` רגיל (#190):** ‏`/root/ImageCtl` פרוס לפי tag, ולכן
הוא ב-**HEAD מנותק** — וזה המצב התקין שלו. הענף `main` ה**מקומי** שלו
אינו זז עם `git fetch`. ‏`git clone --shared` מעתיק את `refs/heads/*` של
המקור אל `refs/remotes/origin/*` של העותק, כלומר `origin/main` **בעותק**
הוא ה-main המיושן.

נמדד ב-2026-08-31, על אותו ריפו ובאותו רגע:

| השיטה | ה-HEAD שהתקבל | קוד יציאה |
|---|---|---|
| `git clone --shared` ואז `git checkout main` | `d5b646f` ❌ | **0** |
| `lab-work-checkout.sh` | `58deb92` ✓ | 0 |

השיטה הנאיבית **לא נכשלה** — היא הצליחה ונתנה עץ שגוי, ‏8 קומיטים
אחורה, בלי שום סימן. זו בדיוק הצורה שעיקרון 5 אוסר.

הסקריפט מוודא גם שה-HEAD של **המקור** לא זז בזמן ה-fetch, כדי שלא יוריד
את השרת הפרוס מהתג שלו.

## שלב 2 — TMPDIR משלך. חובה.

```bash
TMPDIR=/root/ic-<N>-tmp python3 -m pytest tests -q
```

‏`/tmp` על המעבדה הוא **tmpfs של 2GB** שכבר הפיל שלוש ריצות. הסקריפט
מכין את `/root/ic-<N>-tmp` בדיוק בשביל זה ומדפיס אותו בסוף.

אם המעטפת איבדה את `TMPDIR`, הפסולת נוחתת בשורש הריפו — ‏`ic_cookies.txt`
ו-`cap*.json` מוחרגים ב-`.gitignore` בדיוק כי זה קרה.

## שלב 3 — פעמיים לפחות

**ריצה אחת ירוקה אינה ראיה.**

| סוג הטסט | כמה ריצות |
|---|---|
| רגיל | **‏2 לפחות** |
| תלוי-תזמון (מרוצים, טיימרים, תהליכונים) | **‏10** |

מנהל מסר כאן "827 עוברים" על טסט שנכשל ב-4 מתוך 5 ריצות. ריצה אחת מודדת
מזל, לא קוד.

מדווחים את **שתי** התוצאות ואת הזמנים — כך נכתב #232:
`1443 passed` פעמיים (‏351.0s / 351.9s), אפס דילוגים.

## דילוג אינו מעבר

‏`pytest` יוצא 0 גם כשחבילות שלמות דילגו (#52). על המעבדה, שבה הכלים
**אמורים** להיות, מדליקים את הדגל שהופך דילוג לכישלון:

```bash
IMAGECTL_REQUIRE_NATIVE=1 TMPDIR=/root/ic-<N>-tmp python3 -m pytest tests -q
```

הניסוח שמדווחים הוא `N עברו, אפס דילוגים` — ולא `N עברו`. אם היו
דילוגים, מונים אותם ואומרים למה.

## מה מדווחים

בסעיף האימות של ה-PR, ובשדה `ריצות` בחוזה הפלט של `AGENTS.md`:

```
`1443 passed` פעמיים (351.0s / 351.9s), אפס דילוגים — מעבדת ה-VM,
py3.13.5, TMPDIR ייעודי, checkout אומת מול origin/main בקריאה חוזרת.
```

**כמה · איפה · באיזה Python · אפס דילוגים או כמה.** משפט בלי אלה אינו
טענת אימות.

## אחרי המיזוג — ‏main ירוק אינו PR ירוק

לא חלק מההרצה, אבל אותו יום עבודה: ‏`tools/git/after-merge-check.sh [<sha>]`
בודק את הריצה **שאחרי** המיזוג. הוא מסרב לקרוא הצלחה ל-**אפס בדיקות**,
לבדיקות שעדיין רצות, ולכל תוצאה שאינה `success` — כולל `skipped`.

## מדיניות כישלון

| מצב | מה עושים |
|---|---|
| אין גישה למעבדה | **לא לדווח "עובר".** לומר איפה כן רץ, ומה לא נבדק |
| ‏`lab-work-checkout.sh` נכשל | לא לעקוף עם `git clone`. לקרוא את שני ה-sha ולהבין |
| ריצה שנייה אדומה | **הראשונה לא הייתה ראיה.** לחקור, לא להריץ שלישית ולבחור |
| דילוגים בריצה עם הדגל | כשל. לא "עבר עם הערה" |
| הריצה נתקעה | לבדוק תהליכי `udp-sender`/`partclone` יתומים (#79) לפני שמאשימים את הקוד |

</div>
