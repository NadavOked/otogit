"""‏`http_open` חוסם סכימה שאינה http/https — בשלושת הכלים.

השומר נוסף ב-#4 ונשאר **בלי אף טסט**. זה בדיוק הדפוס של #53 בפרויקט
המקור: השומר של ההגדרה המסוכנת ביותר במערכת — הבדיקה אם קיים DHCP —
לא עבד, כי `if found:` על `None`/`[]` תמיד היה שקרי, ואיש לא בדק אותו.

**שומר שאיש לא בודק אינו שומר. הוא הצהרה.**

הטסט רץ על **שלושת** הקבצים, כי אין חבילה משותפת (השמות מקופים
ונטענים ב-`importlib`) והשומר משוכפל. שכפול בלי טסט משותף הוא הדרך
שבה שניים מהם נשארים מתוקנים ואחד נסחף.
"""
import importlib.util
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ["bench-local.py", "limits-watch.py", "model-watch.py"]


def _load(name):
    src = ROOT / "tools" / "agents" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MODULES = [pytest.param(_load(n), id=n) for n in TOOLS]

# נתיב חשוף (`/etc/passwd`) הוא המקרה שקל לפספס: `urlsplit` מחזיר
# עבורו scheme ריק, לא שגיאה.
REFUSED = ["file:///etc/passwd", "ftp://x/y", "gopher://x/y",
           "/etc/passwd", "data:text/plain,x"]


@pytest.mark.parametrize("mod", MODULES)
@pytest.mark.parametrize("url", REFUSED)
def test_a_url_that_is_not_http_is_refused(mod, url):
    with pytest.raises(mod.UnsafeScheme):
        mod.http_open(url, timeout=1)


@pytest.mark.parametrize("mod", MODULES)
@pytest.mark.parametrize("url", ["http://127.0.0.1:1/x", "https://127.0.0.1:1/x"])
def test_http_and_https_pass_the_check(mod, url):
    """הכיוון השני. שומר שחוסם הכול אינו שומר — הוא ניתוק.

    הכתובת מכוונת לפורט סגור, ולכן היא **חייבת** להיכשל ברשת. מה
    שנבדק הוא שהיא עברה את בדיקת הסכימה קודם: כל חריגה מותרת **חוץ**
    מ-`UnsafeScheme`.
    """
    try:
        mod.http_open(url, timeout=1)
    except mod.UnsafeScheme:
        pytest.fail("‏%s נדחה על סכימה, והוא http/https תקין" % url)
    except Exception:
        pass


@pytest.mark.parametrize("mod", MODULES)
def test_unsafe_scheme_is_not_a_network_error(mod):
    """הגדרה שגויה אינה תקלת רשת, ואסור שתיבלע לתוכה.

    הכלים מסווגים `URLError`/`ValueError` כ-`could-not-check` ומדפיסים
    "השרת אינו עונה". אם `UnsafeScheme` היה יורש מהם, עוגן שגוי היה
    נראה על המסך כתקלת רשת — ואז מחפשים את הבעיה ברשת במקום בהגדרה.
    ההפרדה נעשתה בכוונה בקוד; זה הטסט ששומר עליה.
    """
    assert not issubclass(mod.UnsafeScheme, urllib.error.URLError)
    assert not issubclass(mod.UnsafeScheme, ValueError)
    assert not issubclass(mod.UnsafeScheme, OSError)


@pytest.mark.parametrize("mod", MODULES)
def test_the_opener_carries_no_handler_for_other_schemes(mod):
    """הבדיקה המפורשת אינה ההגנה היחידה — הפותחן אוכף בעצמו.

    זה מה שתופס הפניה (redirect) אל סכימה אחרת **באמצע** הדרך, שהבדיקה
    על ה-URL הראשוני אינה רואה. ‏`UnknownHandler` הוא מה שהופך את זה
    לחריגה במקום ל-`None` שחוזר בשקט.
    """
    kinds = {type(h).__name__ for h in mod._OPENER.handlers}
    assert "UnknownHandler" in kinds, "בלי UnknownHandler הפותחן מחזיר None בשקט"
    for bad in ("FTPHandler", "FileHandler", "DataHandler"):
        assert bad not in kinds, "‏%s בפותחן — סכימה שאינה http נפתחת" % bad
