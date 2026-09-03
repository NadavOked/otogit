"""מונה יומי בתוך ה-proxy — קריאה מעבר לתקרה לא יוצאת (#286).

**הפער שזה סוגר.** ‏rpm/tpm נאכפים ב-LiteLLM; התקרות **היומיות**
(‏250/יום ל-compound, ‏500/יום למפתח ג'מיני) היו מתועדות בלבד. רוב
הספקים אינם מדווחים יתרה (נמדד), ולכן הספירה חייבת להיות כאן.

**איך.** ‏callback של LiteLLM: כל הצלחה נספרת לפי הפריסה שנבחרה
(מודל+מפתח); לפני קריאה נבדקת הקבוצה — אם **כל** הפריסות בה מיצו
את היום, הקריאה נחסמת לפני שיצאה. פריסה בודדת שמיצתה מטופלת ממילא
על ידי ה-429 של הספק וה-cooldown של הראוטר.

**כשל ספירה אינו מפיל את הצי.** קובץ מצב פגום → אזהרה קולנית
והקריאה עוברת: ‏hard-$0 הוא מבני (אין למי לשלם) ולא תלוי במונה,
וספירה שנשברת עדיפה כרעש מאשר כהשבתה. זו החרגה מודעת מ"נכשל סגור",
והיא מתועדת כאן בכוונה.

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


def _spec_for(model, man):
    """מוצא את הצהרת המודל במניפסט לפי מחרוזת LiteLLM."""
    prefix = model.split("/", 1)[0]
    pmap = ((man.get("free_fleet") or {})
            .get("litellm_prefix_to_provider") or {})
    pname = pmap.get(prefix)
    if not pname:
        return None, None
    prov = (man.get("providers") or {}).get(pname) or {}
    models = prov.get("models") or {}
    # התאמה לפי סיומת: "groq/groq/compound" ← "compound".
    best = None
    for name in models:
        if model == name or model.endswith("/" + name):
            if best is None or len(name) > len(best):
                best = name
    if best is None and "default" in models:
        best = "default"        # ‏cloudflare מצהיר תקרה לחשבון, לא למודל
    return (models.get(best) if best else None), prov


# תקרות לפי מחרוזת המודל המלאה של LiteLLM, כולל **חלון** — יומי,
# שבועי או חודשי. נדרש על ידי הבעלים: ספק יכול לשנות את שיטת הספירה
# (יומי→חודשי), והחלון חייב לבוא מהמניפסט, לא מהקוד.
#
# נגזר עכשיו מהמניפסט + הקונפיג ולא מרשימה בקוד: ‏`rpd` שהבעלים יוסיף
# ל-mistral יתחיל להיאכף **בלי שינוי קוד**. עד אז המודל מדווח
# ב-`uncounted()` — לא נעלם.
def caps():
    man = _manifest()
    out = {}
    for model in deployed_models():
        spec, prov = _spec_for(model, man)
        if not spec:
            continue
        window = spec.get("window", "daily")
        if spec.get("rpd"):
            out[model] = {"limit": int(spec["rpd"]), "window": window,
                          "unit": "requests"}
        elif spec.get("tokens_per_day"):
            out[model] = {"limit": int(spec["tokens_per_day"]),
                          "window": window, "unit": "tokens"}
        elif spec.get("neurons_per_day"):
            # ‏neurons אינם בקשות; ‏2.8 לקריאה שנמדדה → תקרה שמרנית.
            out[model] = {"limit": int(spec["neurons_per_day"] / 3),
                          "window": window, "unit": "requests"}
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
        spec, prov = _spec_for(model, man)
        if spec is None and prov is None:
            why = "אין מיפוי קידומת ב-free_fleet.litellm_prefix_to_provider"
        elif spec is None:
            why = "הספק מוצהר אך המודל אינו מוצהר תחתיו"
        elif (prov or {}).get("paid") is False and not (prov or {}).get(
                "billing_enabled"):
            why = "מוצהר בלי rpd/tokens_per_day — התקרה אינה ידועה"
        else:
            why = "אין ערך תקרה מוצהר"
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


def record(model, key_alias="", tokens=0):
    """נקרא אחרי הצלחה. הפריסה מזוהה במודל+כינוי-מפתח.

    **גם טוקנים, לא רק בקשות.** ‏flash-lite מוגבל ב-250K טוקנים
    לדקה, וקריאה אחת שנמדדה שקלה 10,208 — כלומר 25 קריאות "קטנות"
    חוצות תקרה שמונה-בקשות אינו רואה כלל. מונה שסופר את היחידה
    הלא-נכונה מדווח "רחוק מהקיר" עד הרגע שבו הוא נחסם.
    """
    c = caps().get(model) or {"limit": None, "window": "daily",
                              "unit": "requests"}
    d = _load()
    k = "%s|%s|%s" % (model, key_alias, window_id(model, c["window"]))
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
    c = caps().get(model) or {"window": "daily"}
    d = _load()
    return _cell(d.get("%s|%s|%s" % (model, key_alias,
                                     window_id(model, c["window"])), 0))[idx]


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
