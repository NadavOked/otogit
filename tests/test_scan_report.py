# tests/test_scan_report.py
import datetime
import pytest
import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "report" / "scan.py"

)
_spec = _ilu.spec_from_file_location('scan', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
source = _mod.source
build = _mod.build
render = _mod.render
Report = _mod.Report


@pytest.fixture
def tz_now():
    return datetime.datetime(2026, 9, 4, 12, 0, 0, tzinfo=datetime.timezone.utc)


def test_all_sources_ok_with_findings_is_ok(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("src2", True, count=10)
    rep = build([s1, s2], ["finding1"], tz_now)
    assert rep.status == "ok"


def test_all_sources_ok_without_findings_is_empty(tz_now):
    s1 = source("src1", True, count=5)
    rep = build([s1], [], tz_now)
    assert rep.status == "empty"


def test_one_failed_source_is_degraded(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("src2", False, count=0, detail="timeout")
    rep = build([s1, s2], [], tz_now)
    assert rep.status == "degraded"


def test_degraded_stays_degraded_even_with_many_findings(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("src2", False, count=0, detail="error")
    rep = build([s1, s2], ["f1", "f2", "f3"], tz_now)
    assert rep.status != "ok"
    assert rep.status == "degraded"


def test_every_source_failed_is_failed(tz_now):
    s1 = source("src1", False, count=0)
    s2 = source("src2", False, count=0)
    rep = build([s1, s2], [], tz_now)
    assert rep.status == "failed"


def test_empty_sources_list_is_failed(tz_now):
    rep = build([], [], tz_now)
    assert rep.status != "empty"
    assert rep.status != "ok"
    assert rep.status == "failed"


def test_items_scanned_excludes_failed_sources(tz_now):
    s1 = source("src1", True, count=10)
    s2 = source("src2", False, count=50)
    rep = build([s1, s2], [], tz_now)
    assert rep.items_scanned == 10


def test_source_rejects_non_bool_ok():
    with pytest.raises(TypeError):
        source("src1", "false")


def test_source_rejects_boolean_count():
    with pytest.raises(ValueError):
        source("src1", True, count=True)


def test_source_rejects_negative_count():
    with pytest.raises(ValueError):
        source("src1", True, count=-1)


def test_source_rejects_empty_name():
    with pytest.raises(ValueError):
        source("", True)


def test_build_rejects_naive_now():
    s1 = source("src1", True)
    naive_now = datetime.datetime(2026, 9, 4, 12, 0, 0)
    with pytest.raises(ValueError):
        build([s1], [], naive_now)


def test_generated_at_comes_from_now_not_the_clock():
    s1 = source("src1", True)
    specific_now = datetime.datetime(
        2025, 1, 1, 10, 20, 30, tzinfo=datetime.timezone.utc
    )
    rep = build([s1], [], specific_now)
    assert rep.generated_at == specific_now.isoformat()


def test_sources_are_returned_in_input_order(tz_now):
    s1 = source("b_src", True)
    s2 = source("a_src", True)
    rep = build([s1, s2], [], tz_now)
    assert rep.sources == (s1, s2)


def test_render_starts_with_the_uppercased_status(tz_now):
    s1 = source("src1", True)
    rep = build([s1], [], tz_now)
    text = render(rep)
    assert text.startswith("STATUS: EMPTY")


def test_render_lists_every_source_with_ok_or_failed(tz_now):
    s1 = source("src1", True, count=2)
    s2 = source("src2", False, count=0)
    rep = build([s1, s2], [], tz_now)
    text = render(rep)
    assert "Source 'src1': OK" in text
    assert "Source 'src2': FAILED" in text


def test_render_shows_since_and_detail_when_present(tz_now):
    s1 = source("src1", True, count=2, since="7d", detail="all clean")
    rep = build([s1], [], tz_now)
    text = render(rep)
    assert "Since: 7d" in text
    assert "Detail: all clean" in text


def test_render_of_degraded_names_the_failed_sources(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("bad_src", False, detail="down")
    rep = build([s1, s2], [], tz_now)
    text = render(rep)
    assert "bad_src" in text
    assert "incomplete" in text


def test_render_of_failed_says_the_picture_is_incomplete(tz_now):
    s1 = source("bad_src", False, detail="down")
    rep = build([s1], [], tz_now)
    text = render(rep)
    assert "incomplete" in text


def test_render_of_empty_status_may_say_nothing_found(tz_now):
    s1 = source("src1", True, count=0)
    rep = build([s1], [], tz_now)
    text = render(rep)
    # The requirement permits "nothing found" or "no findings" here if desired.
    # We verify rendering works cleanly without claiming uncompleted state.
    assert "no findings" not in text.lower() or rep.status == "empty"


def test_render_of_degraded_does_not_say_nothing_found(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("src2", False, count=0)
    rep = build([s1, s2], [], tz_now)
    text = render(rep)
    assert "no findings" not in text.lower()
    assert "nothing found" not in text.lower()


def test_render_of_failed_does_not_say_nothing_found(tz_now):
    s1 = source("src1", False, count=0)
    rep = build([s1], [], tz_now)
    text = render(rep)
    assert "no findings" not in text.lower()
    assert "nothing found" not in text.lower()


def test_render_contains_no_ansi_escape(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("src2", False, count=0, detail="err")
    rep = build([s1, s2], [], tz_now)
    text = render(rep)
    assert "\x1b" not in text


def test_render_is_stable(tz_now):
    s1 = source("src1", True, count=5)
    s2 = source("src2", False, count=0, detail="err")
    rep = build([s1, s2], [], tz_now)
    text1 = render(rep)
    text2 = render(rep)
    assert text1 == text2


def test_hand_built_source_with_non_bool_ok_is_not_counted_as_success(tz_now):
    # A record that arrived as JSON never passed through source(), so its `ok`
    # can be the string "false" — truthy in Python. F10 forbids a truthiness
    # check on `ok`: a source that failed must never be counted as a success.
    raw = {"name": "gh-api", "ok": "false", "count": 0,
           "since": None, "detail": "HTTP 500"}
    rep = build([raw], [], tz_now)
    assert rep.sources_ok == 0
    assert rep.sources_failed == 1
    assert rep.status == "failed"
    assert rep.status != "empty"
    assert rep.items_scanned == 0
    text = render(rep)
    assert "Source 'gh-api': FAILED" in text
    assert "Source 'gh-api': OK" not in text
    assert "incomplete" in text.lower()
    assert "gh-api" in text.splitlines()[-1]


def test_hand_built_source_with_non_bool_ok_does_not_hide_a_real_failure(tz_now):
    # One genuine success beside the type-slipped record: the report must be
    # degraded, not "ok", and must not claim nothing was found.
    good = source("disk", True, count=4)
    raw = {"name": "gh-api", "ok": "false", "count": 7, "detail": "HTTP 500"}
    rep = build([good, raw], [], tz_now)
    assert rep.status == "degraded"
    assert rep.sources_ok == 1
    assert rep.sources_failed == 1
    assert rep.items_scanned == 4  # the failed source's 7 must not inflate it
    text = render(rep).lower()
    assert "no findings" not in text
    assert "nothing found" not in text
