"""מונה יומי בתוך ה-proxy — קריאה מעבר לתקרה לא יוצאת (#286).

**הפער שזה סוגר.** ‏rpm/tpm נאכפים ב-LiteLLM; התקרות **היומיות**
(‏250/יום ל-compound, ‏500/יום למפתח ג'מיני) היו מתועדות בלבד. רוב
הספקים אינם מדווחים יתרה (נמדד), ולכן הספירה חייבת להיות כאן.

**איך.** ‏callback של LiteLLM: כל הצלחה נספרת לפי הפריסה שנבחרה
(מודל+מפתח); לפני קריאה נבדקת הקבוצה — אם **כל** הפריסות בה מיצו
את היום, הקריאה נחסמת לפני שיצאה. פריסה בודדת שמיצתה מטופלת ממילא
על ידי ה-429 של הספק וה-cooldown של הראוטר.

**מפתח הספירה נגזר מ-`quota_scope` שבמניפסט, לא ממחרוזת המודל**
(‏otogit-lab#6). שני ספקים מגבילים **לפי חשבון**, וכל מודליהם
שואבים ממאגר אחד: ‏Cloudflare נמדד ב-04/09 עם 2.99 + 3.04 = 6.03
נוירונים מול תקרה **אחת** של 10K. עד אז התקרה הוצהרה תחת מודל
פסאודו `default`, ‏`_spec_for()` נפל אליה עבור **כל** מודל CF,
והמונה התיר 20,000 מול 10,000. ‏`scope: account` ⇒ מפתח אחד לספק.

**‏scope חסר הוא כישלון רועש.** ברירת מחדל שקטה כאן היא הבאג עצמו,
ולכן ספק שהצי סופר ואינו מצהיר `scope` (או `budget: none`) זורק
‏`ScopeUndeclared`.

**כשל ספירה אינו מפיל את הצי.** קובץ מצב פגום → אזהרה קולנית
והקריאה עוברת: ‏hard-$0 הוא מבני (אין למי לשלם) ולא תלוי במונה,
וספירה שנשברת עדיפה כרעש מאשר כהשבתה. זו החרגה מודעת מ"נכשל סגור",
והיא מתועדת כאן בכוונה — ומניפסט שבור אינו יוצא ממנה: הוא מרעיש
דרך ה-`except Exception` של ה-hook, ואינו חוסם.

התקרות נקראות מ-providers.json — לא מקודדות. חלון ג'מיני בשעון
האוקיינוס השקט (שם האיפוס), השאר UTC.
"""
import datetime as dt
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROVIDERS = os.path.join(HERE, "providers.json")
YAML = os.path.join(HERE, "litellm.yaml")
STATE = os.path.join(os.path.expanduser("~"), ".imagectl-fleet-usage.json")
WARN_AT = 0.8

# ערך תקציב שהספק מצהיר עליו כ"אין תקרה" — להבדיל משדה שלא הוצהר.
NO_LIMIT = "no-limit"
# קידומת מפתח הספירה כשההיקף הוא חשבון. אינה יכולה להתנגש במחרוזת
# מודל של LiteLLM, שתמיד מתחילה בקידומת ספק.
ACCOUNT_KEY = "@account:"
# (שדה, יחידה, מחלק) — לפי סדר עדיפות. ‏neurons אינם בקשות: ‏2.8
# לקריאה שנמדדה, ולכן חלוקה ב-3 היא תקרה שמרנית.
BUDGET_FIELDS = (("rpd", "requests", 1),
                 ("tokens_per_day", "tokens", 1),
                 ("neurons_per_day", "requests", 3))


class ScopeUndeclared(Exception):
    """ספק שהצי סופר בלי הצהרת `quota_scope` תקינה.

    זהו **קלט שגוי, לא כשל ריצה** — ולכן הוא נזרק ואינו נבלע. הוא
    אינו יורש מ-`ValueError` בכוונה: ‏`async_pre_call_hook` מרים
    ‏`ValueError` הלאה (וחוסם את הקריאה), ואילו כאן ההתנהגות הנכונה
    היא הרעש הרגיל של המונה — מניפסט שבור אינו סיבה לכבות את הצי.
    """


def _manifest():
    try:
        return json.load(io.open(PROVIDERS, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def deployed_models():
    """מחרוזות המודל שבאמת מוגדרות ב-litellm.yaml.

    הגרסה הראשונה של `caps()` הייתה **רשימה ידנית** של ארבעה מודלים.
    ספק שנוסף לקונפיג — ‏NIM, ‏Mistral, ‏OpenRouter — פשוט לא הופיע
    בה, ולכן לא נספר **ולא דווח שאינו נספר**: הוא נראה בדיוק כמו
    מודל בלי תקרה. "לא נספר" ו"אין לו תקרה" הם שני מצבים שונים
    (עיקרון 5), וכאן הם קופלו לאחד.
    """
    try:
        body = io.open(YAML, encoding="utf-8").read()
    except OSError:
        return []
    return sorted(set(re.findall(r"^\s+model:\s*(\S+)", body, re.M)))


def _provider_of(model, man):
    """(שם הספק, ההצהרה שלו) לפי קידומת LiteLLM. אינו זורק."""
    pmap = ((man.get("free_fleet") or {})
            .get("litellm_prefix_to_provider") or {})
    pname = pmap.get(model.split("/", 1)[0])
    if not pname:
        return None, None
    return pname, ((man.get("providers") or {}).get(pname) or {})


def _spec_for(model, man):
    """מוצא את הצהרת המודל במניפסט לפי מחרוזת LiteLLM.

    **אין כאן יותר נפילה למודל פסאודו `default`.** היא הייתה
    המנגנון של otogit-lab#6: תקרת ה-10K של cloudflare הוצהרה תחתיה,
    וכל אחד משני מודלי ה-CF קיבל אותה **במלואה**. תקרה שהיא של
    החשבון יושבת מהיום ב-`quota_scope.account_limits`, ומגיעה דרך
    מפתח ספירה אחד — לא דרך התאמה שנכשלה.
    """
    pname, prov = _provider_of(model, man)
    if prov is None:
        return None, None
    models = prov.get("models") or {}
    # התאמה לפי סיומת: "groq/groq/compound" ← "compound".
    best = None
    for name in models:
        if model == name or model.endswith("/" + name):
            if best is None or len(name) > len(best):
                best = name
    return (models.get(best) if best else None), prov


def _budget_field(spec, field):
    """(ערך, מצב) לשדה תקציב — **שלושה** מצבים ולא שניים:

    ‏`"number"` — הוצהר מספר · `"declared-none"` — הספק מצהיר
    במפורש `no-limit` · `"undeclared"` — לא הוצהר דבר. שני האחרונים
    נראים זהים ל-`spec.get()`, וזו בדיוק הקיפול שעיקרון 5 אוסר:
    ‏"אין תקרה" ו"לא יודעים מה התקרה" אינם אותו מצב.
    """
    value = spec.get(field) if isinstance(spec, dict) else None
    if value == NO_LIMIT:
        return None, "declared-none"
    if value is None:
        return None, "undeclared"
    return int(value), "number"


def _scope_of(pname, prov):
    """היקף הספירה המוצהר: ‏account / model / unknown / none.

    **אין ברירת מחדל.** ספק שהצי סופר ואינו מצהיר — זורק. ברירת
    מחדל שקטה כאן היא הבאג עצמו.
    """
    block = prov.get("quota_scope")
    if not isinstance(block, dict):
        raise ScopeUndeclared(
            "‏%s: אין quota_scope ב-providers.json. ספק שנספר חייב "
            "להצהיר scope (account/model/unknown) או budget: none."
            % pname)
    if block.get("budget") == "none":
        if "scope" in block:
            raise ScopeUndeclared(
                "‏%s: quota_scope מצהיר גם budget: none וגם scope — אין "
                "מפתח ספירה למה שאין לו תקציב." % pname)
        for name, spec in (prov.get("models") or {}).items():
            for field, _unit, _div in BUDGET_FIELDS:
                if _budget_field(spec, field)[1] == "number":
                    raise ScopeUndeclared(
                        "‏%s: quota_scope מצהיר budget: none, אך המודל %s "
                        "מצהיר %s. שתי ההצהרות אינן יכולות להיות נכונות."
                        % (pname, name, field))
        return "none"
    scope = block.get("scope")
    if scope not in ("account", "model", "unknown"):
        raise ScopeUndeclared(
            "‏%s: quota_scope.scope הוא %r — חייב להיות account, model "
            "או unknown, או במקומו budget: none." % (pname, scope))
    return scope


def counting_subject(model, man=None):
    """**מפתח הספירה** של הפריסה — נגזר מ-`scope`, לא ממחרוזת המודל.

    ‏`account` ⇒ כל מודלי הספק נספרים תחת מפתח אחד, כי הם שואבים
    ממאגר אחד. זו כל התיקון של otogit-lab#6.
    """
    man = _manifest() if man is None else man
    pname, prov = _provider_of(model, man)
    if prov is None:
        return model
    if _scope_of(pname, prov) == "account":
        return ACCOUNT_KEY + pname
    return model


# תקרות לפי מחרוזת המודל המלאה של LiteLLM, כולל **חלון** — יומי,
# שבועי או חודשי. נדרש על ידי הבעלים: ספק יכול לשנות את שיטת הספירה
# (יומי→חודשי), והחלון חייב לבוא מהמניפסט, לא מהקוד.
#
# נגזר עכשיו מהמניפסט + הקונפיג ולא מרשימה בקוד: ‏`rpd` שהבעלים יוסיף
# ל-mistral יתחיל להיאכף **בלי שינוי קוד**. עד אז המודל מדווח
# ב-`uncounted()` — לא נעלם.
def _cap_from(spec, window):
    """התקרה הראשונה שהוצהרה כ**מספר**, או None.

    ‏`no-limit` אינו תקרה ואינו אפס — מדלגים עליו לשדה הבא. ‏Groq
    מצהיר `tokens_per_day: no-limit` לצד `rpd: 250`, ובלי ההבחנה
    הזאת "אין תקרת טוקנים" היה נקרא כ"לא ידוע".
    """
    for field, unit, divisor in BUDGET_FIELDS:
        value, state = _budget_field(spec, field)
        if state == "number":
            return {"limit": int(value / divisor), "window": window,
                    "unit": unit}
    return None


def caps():
    man = _manifest()
    out = {}
    for model in deployed_models():
        pname, prov = _provider_of(model, man)
        if prov is None:
            continue
        scope = _scope_of(pname, prov)
        block = prov.get("quota_scope") or {}
        if scope in ("none", "unknown"):
            # אין תקציב · ההיקף לא נמדד. שניהם מדווחים ב-uncounted()
            # עם הסיבה שלהם, ואינם נאכפים על סמך ניחוש. אכיפה לפי
            # מודל על מאגר שהוא בעצם של החשבון מתירה פי מספר המודלים.
            continue
        if scope == "account":
            subject = ACCOUNT_KEY + pname
            spec = block.get("account_limits") or {}
            window = block.get("window") or "daily"
        else:
            subject = model
            spec = _spec_for(model, man)[0] or {}
            window = spec.get("window") or block.get("window") or "daily"
        cap = _cap_from(spec, window)
        if cap is None:
            continue
        cap["key"] = subject
        out[model] = cap
        # גם תחת מפתח הספירה עצמו: הדוח קורא את קובץ המצב, ושם
        # רשומה של ספק account ממופתחת בחשבון ולא במודל. בלעדי זה
        # היא הייתה מוצגת "ללא תקרה ידועה" דווקא במקום שבו התקרה
        # המשותפת היא כל הנקודה.
        out[subject] = dict(cap)
    return out


def uncounted():
    """פריסות שיוצאות מהקונפיג ואין להן תקרה ידועה — מדווחות, לא
    נבלעות. זה החור שהיה כאן: ‏NIM, ‏Mistral ו-OpenRouter נספרו
    כאילו אין להם גבול, בזמן שפשוט לא ידענו מהו."""
    known = caps()
    man = _manifest()
    out = []
    for model in deployed_models():
        if model in known:
            continue
        pname, prov = _provider_of(model, man)
        if prov is None:
            out.append((model, "אין מיפוי קידומת ב-free_fleet."
                               "litellm_prefix_to_provider"))
            continue
        scope = _scope_of(pname, prov)
        spec = _spec_for(model, man)[0]
        if scope == "none":
            why = ("‏%s מצהיר budget: none — נמדד שאין לו תקציב כלל. "
                   "אין מה לספור, וזו היעדרות **ידועה** ולא חוסר"
                   % pname)
        elif scope == "unknown":
            why = ("היקף הספירה (scope) של %s לא נמדד — התקרות שלו "
                   "אינן נאכפות עד שיימדד" % pname)
        elif spec is None:
            why = "הספק מוצהר אך המודל אינו מוצהר תחתיו"
        elif scope == "account":
            why = ("‏scope: account מוצהר, אך תקרת החשבון של %s אינה "
                   "מספר (‏source=%s)"
                   % (pname, (prov.get("quota_scope") or {}).get("source")))
        elif any(_budget_field(spec, f)[1] == "declared-none"
                 for f, _u, _d in BUDGET_FIELDS):
            why = ("כל שדות התקציב מוצהרים no-limit — אין תקרה, וזו "
                   "הצהרה ולא חוסר")
        else:
            why = "מוצהר בלי rpd/tokens_per_day — התקרה אינה ידועה"
        out.append((model, why))
    return out


def daily_caps():
    """תאימות לקוראים ישנים — התקרה בלבד, בלי החלון."""
    return {m: c["limit"] for m, c in caps().items()}


def window_id(model, window="daily"):
    """מזהה החלון הנוכחי. שינוי `window` במניפסט מחליף ספירה מיידית —
    המפתח בקובץ המצב כולל את הצורה, ולכן חלון ישן פשוט מפסיק להיספר."""
    now = dt.datetime.now(dt.timezone.utc)
    if model.startswith("gemini/"):
        # האיפוס של גוגל בחצות האוקיינוס השקט. ‏UTC-8 שמרני: לכל
        # היותר נספור חלון ארוך יותר, לא נפרוץ תקרה.
        now = now - dt.timedelta(hours=8)
    if window == "monthly":
        return now.strftime("%Y-%m")
    if window == "weekly":
        return now.strftime("%G-W%V")
    return now.strftime("%Y-%m-%d")


def _load():
    try:
        return json.load(io.open(STATE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(d):
    tmp = STATE + ".tmp"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(d))
    os.replace(tmp, STATE)


def _cell(v):
    """ערך רשומה → (בקשות, טוקנים). הצורה הישנה הייתה int בלבד, וקובץ
    מצב קיים חייב להמשיך להיקרא — שדרוג שמאפס מונים הוא שדרוג
    שמסתיר חריגה."""
    if isinstance(v, dict):
        return int(v.get("n", 0)), int(v.get("tokens", 0))
    try:
        return int(v), 0
    except (TypeError, ValueError):
        return 0, 0


def _cap_of(model):
    """התקרה של הפריסה **כולל מפתח הספירה שלה**. ‏`caps()` ממופתח גם
    במודל וגם במפתח הספירה, ולכן שניהם מגיעים לאותה רשומה."""
    return caps().get(model) or {
        "limit": None, "window": "daily", "unit": "requests",
        "key": counting_subject(model)}


def _state_key(model, key_alias, cap):
    """הרשומה בקובץ המצב: מפתח ספירה | כינוי מפתח API | חלון.

    ‏`key` נסבל כחסר בכוונה: טסטים מזריקים `caps()` מצומצם, ואז
    המודל הוא מפתח הספירה של עצמו.
    """
    subject = cap.get("key") or model
    return "%s|%s|%s" % (subject, key_alias,
                         window_id(subject, cap.get("window", "daily")))


def record(model, key_alias="", tokens=0):
    """נקרא אחרי הצלחה. הפריסה מזוהה במודל+כינוי-מפתח.

    **גם טוקנים, לא רק בקשות.** ‏flash-lite מוגבל ב-250K טוקנים
    לדקה, וקריאה אחת שנמדדה שקלה 10,208 — כלומר 25 קריאות "קטנות"
    חוצות תקרה שמונה-בקשות אינו רואה כלל. מונה שסופר את היחידה
    הלא-נכונה מדווח "רחוק מהקיר" עד הרגע שבו הוא נחסם.
    """
    c = _cap_of(model)
    d = _load()
    k = _state_key(model, key_alias, c)
    n, tok = _cell(d.get(k, 0))
    n, tok = n + 1, tok + max(0, int(tokens or 0))
    d[k] = {"n": n, "tokens": tok}
    _save(d)
    used = tok if c.get("unit") == "tokens" else n
    if c["limit"] and used >= int(c["limit"] * WARN_AT):
        return "‏%s: ‏%d/%d %s בחלון ה-%s — מעל 80%%, הקיר מתקרב" % (
            model, used, c["limit"], c.get("unit", "requests"), c["window"])
    return None


def _spent(model, key_alias, idx):
    c = _cap_of(model)
    return _cell(_load().get(_state_key(model, key_alias, c), 0))[idx]


def spent_today(model, key_alias=""):
    """בקשות בחלון הנוכחי."""
    return _spent(model, key_alias, 0)


def tokens_today(model, key_alias=""):
    """טוקנים בחלון הנוכחי — אפס גם כשלא דווחו, ולכן `spent_today`
    נשאר המדד היחיד שתמיד קיים."""
    return _spent(model, key_alias, 1)


def group_exhausted(models_in_group):
    """‏True רק כשלכל הפריסות בקבוצה יש תקרה ידועה וכולן מוצו."""
    all_caps = caps()
    verdicts = []
    for model, key_alias in models_in_group:
        c = all_caps.get(model)
        if c is None:
            return False            # פריסה בלי תקרה ידועה = יש לאן לנתב
        used = (tokens_today(model, key_alias)
                if c.get("unit") == "tokens" else spent_today(model, key_alias))
        verdicts.append(used >= c["limit"])
    return bool(verdicts) and all(verdicts)


try:
    from litellm.integrations.custom_logger import CustomLogger

    class FleetBudget(CustomLogger):
        async def async_pre_call_hook(self, user_api_key_dict, cache, data,
                                      call_type):
            try:
                from litellm.proxy.proxy_server import llm_router
                group = data.get("model", "")
                deps = [(d["litellm_params"]["model"],
                         str(d["litellm_params"].get("api_key", ""))[-6:])
                        for d in (llm_router.get_model_list(model_name=group)
                                  or [])]
                if deps and group_exhausted(deps):
                    raise ValueError(
                        "התקרה היומית של כל הפריסות בקבוצה %r מוצתה — "
                        "הקריאה נחסמה לפני שיצאה (#286). מתאפס באיפוס "
                        "הספק." % group)
            except ValueError:
                raise
            except Exception as exc:                       # noqa: BLE001
                print("fleet_budget: הבדיקה עצמה כשלה (%s) — הקריאה "
                      "עוברת, והרעש הזה מכוון" % type(exc).__name__)
            return data

        async def async_log_success_event(self, kwargs, response_obj,
                                          start_time, end_time):
            try:
                lp = kwargs.get("litellm_params") or {}
                model = kwargs.get("model", "")
                # נמדד: ‏kwargs["model"] מגיע בלי קידומת הספק
                # ("gemini-3.1-flash-lite"), והתקרות ממופתחות **עם**
                # ("gemini/..."). בלי ההשלמה הזאת המונה סופר תחת שם
                # שהאכיפה לא מכירה — נספר ולעולם לא נחסם.
                if "/" not in model:
                    prov = kwargs.get("custom_llm_provider") or ""
                    if prov:
                        model = prov + "/" + model
                key = str(lp.get("api_key") or "")[-6:]
                # הטוקנים מגיעים מ-usage של התשובה. ספק שאינו מדווח
                # ‏usage משאיר 0 — וזה נראה בדוח כ-0, כלומר "לא דווח",
                # ולא כ"קריאה זולה".
                usage = getattr(response_obj, "usage", None) or {}
                if not isinstance(usage, dict):
                    usage = getattr(usage, "__dict__", {}) or {}
                tokens = usage.get("total_tokens") or 0
                warn = record(model, key, tokens)
                if warn:
                    print("fleet_budget: " + warn)
            except Exception as exc:                       # noqa: BLE001
                print("fleet_budget: רישום נכשל (%s) — נספר חסר, לא "
                      "עודף" % type(exc).__name__)

    handler = FleetBudget()
except ImportError:
    handler = None      # מחוץ ל-proxy (טסטים) — הלוגיקה למעלה עומדת לבדה


if __name__ == "__main__":
    # הרצה ישירה החזירה **אפס פלט** — מודול שנראה כמו כלי ואינו כלי.
    # הדוח עצמו יושב ב-fleet-report.py כדי לא לגרור argparse אל תוך
    # ה-proxy, ולכן כאן רק הפניה — ולא שתיקה.
    # ‏ASCII בלבד: ‏stderr של ווינדוס הוא cp1252, והודעה עברית כאן
    # הייתה קורסת — כלומר מחליפה שתיקה בהתרסקות, לא בהסבר.
    sys.stderr.write(
        "fleet_budget.py is the counting library, not a CLI.\n"
        "Report: python tools/agents/fleet-report.py --report\n")
    sys.exit(2)
