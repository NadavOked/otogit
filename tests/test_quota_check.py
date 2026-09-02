"""ארבעה מצבים, וסוד שלא יוצא החוצה.

**למה זה קיים.** ‏`quota-check` נועד לענות על שאלה אחת: האם המקור
שממנו קראנו מכסה **עדיין עובד**. אם הוא מקפל "נשבר", "פג" ו"אין
מקור" לכישלון אחד, הוא עונה על השאלה הלא נכונה — ומי שיקרא את
הפלט יחפש באג ב-endpoint בזמן שצריך פשוט לחדש טוקן.

זה קרה בפועל: הריצה הראשונה דיווחה `broken` על גרוק, והסיבה
האמיתית הייתה `expires_at` שעבר באותו בוקר.
"""
import importlib.util
import json
import datetime as dt
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "quota-check.py"


def _load():
    spec = importlib.util.spec_from_file_location("quota_check", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


qc = _load()


def test_the_four_states_are_distinct():
    """שלושה מהם אינם כישלון — ורק אחד מהם הרעה."""
    assert len({qc.OK, qc.BROKEN, qc.ABSENT, qc.EXPIRED}) == 4


@pytest.mark.parametrize("stamp,want", [
    ("2020-01-01T00:00:00Z", True),
    ("2999-01-01T00:00:00Z", False),
    ("לא תאריך", None),
    (None, None),
])
def test_expiry_is_measured_and_unknown_is_not_valid(stamp, want):
    """‏None פירושו 'לא ידוע', ולא 'תקף'. זו ההבחנה של עיקרון 5."""
    assert qc._expired(stamp) is want


def test_an_expired_token_is_not_reported_as_broken(tmp_path, monkeypatch):
    """הבדיקה שמונעת את הכשל האמיתי שקרה כאן."""
    home = tmp_path
    (home / ".grok").mkdir()
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2))
    (home / ".grok" / "auth.json").write_text(json.dumps({
        "https://auth.x.ai::abc": {"key": "x" * 64,
                                   "expires_at": past.isoformat()}}),
        encoding="utf-8")
    monkeypatch.setattr(qc, "HOME", str(home))
    r = qc.check_grok()
    assert r["state"] == qc.EXPIRED, (
        "טוקן שפג דווח כ-%r — מי שיקרא את זה יחפש באג ב-endpoint"
        % r["state"])


def test_no_token_value_ever_reaches_the_output(tmp_path, monkeypatch):
    """הכלי קורא סוד. הפלט שלו אסור שיכיל אותו — בשום שדה."""
    secret = "SECRET" + "y" * 60
    home = tmp_path
    (home / ".grok").mkdir()
    (home / ".grok" / "auth.json").write_text(json.dumps({
        "https://auth.x.ai::abc": {"key": secret,
                                   "expires_at": "2020-01-01T00:00:00Z"}}),
        encoding="utf-8")
    monkeypatch.setattr(qc, "HOME", str(home))
    blob = json.dumps(qc.check_grok(), ensure_ascii=False)
    assert secret not in blob and secret[:12] not in blob


def test_a_missing_auth_file_is_absent_not_broken(tmp_path, monkeypatch):
    """אין קובץ אינו 'המקור נשבר'. אין ראיה על המקור בכלל."""
    monkeypatch.setattr(qc, "HOME", str(tmp_path))
    assert qc.check_grok()["state"] == qc.ABSENT


def test_the_codex_reader_looks_under_rate_limits():
    """הקינון הזה הוא בדיוק מה שהפיל את הריצה הראשונה."""
    body = SRC.read_text(encoding="utf-8")
    assert '.get("rateLimits")' in body, (
        "התשובה יושבת תחת result.rateLimits — קריאה מ-result מחזירה "
        "{} ונראית כמו מתודה שהשתנתה")
