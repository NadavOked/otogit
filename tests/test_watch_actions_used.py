# tests/test_watch_actions_used.py
import importlib.util as _ilu
from pathlib import Path as _Path

_SRC = (

    _Path(__file__).resolve().parent.parent

    / "tools" / "agents" / "watch" / "actions_used.py"

)
_spec = _ilu.spec_from_file_location('actions_used', _SRC)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
actions_used = _mod.actions_used
parse_uses = _mod.parse_uses


def test_simple_owner_repo_ref_is_parsed():
    res = parse_uses("      uses: actions/checkout@v7")
    assert res == {
        "kind": "remote",
        "owner": "actions",
        "repo": "checkout",
        "path": None,
        "ref": "v7",
        "raw": "actions/checkout@v7",
    }


def test_leading_dash_and_indentation_are_handled():
    res = parse_uses("  - uses: actions/checkout@v7")
    assert res["kind"] == "remote"
    assert res["owner"] == "actions"
    assert res["repo"] == "checkout"
    assert res["ref"] == "v7"


def test_double_and_single_quotes_are_stripped():
    res_double = parse_uses('uses: "actions/setup-python@v5"')
    res_single = parse_uses("uses: 'github/codeql-action/analyze@v3'")

    assert res_double["raw"] == "actions/setup-python@v5"
    assert res_double["owner"] == "actions"
    assert res_double["ref"] == "v5"

    assert res_single["raw"] == "github/codeql-action/analyze@v3"
    assert res_single["owner"] == "github"
    assert res_single["ref"] == "v3"


def test_subdirectory_action_splits_owner_repo_path():
    res = parse_uses("uses: github/codeql-action/analyze@v3")
    assert res["kind"] == "remote"
    assert res["owner"] == "github"
    assert res["repo"] == "codeql-action"
    assert res["path"] == "analyze"
    assert res["ref"] == "v3"


def test_trailing_comment_is_stripped():
    res = parse_uses("uses: actions/checkout@8f4b7f8   # a comment")
    assert res["raw"] == "actions/checkout@8f4b7f8"
    assert res["ref"] == "8f4b7f8"


def test_hash_inside_quotes_is_not_treated_as_a_comment():
    res = parse_uses('uses: "actions/checkout@v7#foo"')
    assert res["raw"] == "actions/checkout@v7#foo"
    assert res["ref"] == "v7#foo"


def test_sha_pinned_ref_is_kept_verbatim():
    res = parse_uses("uses: actions/checkout@8f4b7f8067f22a080c41881c698ed63d")
    assert res["ref"] == "8f4b7f8067f22a080c41881c698ed63d"


def test_local_action_is_kind_local():
    res = parse_uses("uses: ./.github/actions/local-thing")
    assert res["kind"] == "local"
    assert res["owner"] is None
    assert res["repo"] is None
    assert res["path"] is None
    assert res["ref"] is None
    assert res["raw"] == "./.github/actions/local-thing"


def test_docker_action_is_kind_docker():
    res = parse_uses("uses: docker://alpine:3.20")
    assert res["kind"] == "docker"
    assert res["owner"] is None
    assert res["repo"] is None
    assert res["path"] is None
    assert res["ref"] is None
    assert res["raw"] == "docker://alpine:3.20"


def test_remote_without_at_ref_is_unknown_not_dropped():
    res = parse_uses("uses: actions/checkout")
    assert res["kind"] == "unknown"

    files = [{"name": "ci.yml", "text": "uses: actions/checkout"}]
    inventory, unparsed = actions_used(files)
    assert inventory == []
    assert len(unparsed) == 1
    assert unparsed[0] == {
        "file": "ci.yml",
        "line": 1,
        "text": "uses: actions/checkout",
        "kind": "unknown",
    }


def test_empty_uses_value_is_unknown():
    res = parse_uses("uses:   ")
    assert res["kind"] == "unknown"
    assert res["raw"] == ""


def test_non_uses_line_returns_none():
    assert parse_uses("run: echo hello") is None
    assert parse_uses("name: CI Workflow") is None


def test_a_line_mentioning_uses_in_prose_returns_none():
    assert parse_uses("# this uses: something") is None
    assert parse_uses("  # - uses: actions/checkout@v7") is None


def test_inventory_merges_the_same_action_across_two_files():
    files = [
        {"name": "a.yml", "text": "uses: actions/checkout@v7"},
        {"name": "b.yml", "text": "uses: actions/checkout@v7"},
    ]
    inventory, unparsed = actions_used(files)
    assert unparsed == []
    assert len(inventory) == 1
    assert inventory[0] == {
        "owner": "actions",
        "repo": "checkout",
        "path": None,
        "refs": ("v7",),
        "files": ("a.yml", "b.yml"),
    }


def test_two_different_refs_for_one_action_are_both_listed():
    files = [
        {"name": "a.yml", "text": "uses: actions/checkout@v7"},
        {"name": "b.yml", "text": "uses: actions/checkout@v8"},
    ]
    inventory, unparsed = actions_used(files)
    assert inventory[0]["refs"] == ("v7", "v8")


def test_inventory_excludes_local_and_docker():
    files = [
        {
            "name": "a.yml",
            "text": "uses: ./.github/actions/foo\nuses: docker://alpine:3.20",
        }
    ]
    inventory, unparsed = actions_used(files)
    assert inventory == []
    assert len(unparsed) == 2
    assert unparsed[0]["kind"] == "local"
    assert unparsed[1]["kind"] == "docker"


def test_unparsed_records_file_and_one_based_line_number():
    files = [
        {"name": "a.yml", "text": "name: CI\n  uses: ./.github/actions/foo"},
    ]
    inventory, unparsed = actions_used(files)
    assert len(unparsed) == 1
    assert unparsed[0] == {
        "file": "a.yml",
        "line": 2,
        "text": "uses: ./.github/actions/foo",
        "kind": "local",
    }


def test_bad_file_entry_is_recorded_not_skipped():
    files = [
        {"name": "bad.yml", "text": None},
        "not-a-dict",
    ]
    inventory, unparsed = actions_used(files)
    assert inventory == []
    assert len(unparsed) == 2
    assert unparsed[0] == {
        "file": "bad.yml",
        "line": 0,
        "text": "",
        "kind": "bad-file",
    }
    assert unparsed[1] == {
        "file": "unknown",
        "line": 0,
        "text": "",
        "kind": "bad-file",
    }


def test_empty_files_returns_two_empty_lists():
    assert actions_used([]) == ([], [])


def test_inventory_is_sorted_and_deterministic():
    files = [
        {
            "name": "b.yml",
            "text": "uses: b/repo@v1\nuses: a/repo/path@v1\nuses: a/repo@v1",
        },
        {"name": "a.yml", "text": "uses: a/repo@v2"},
    ]
    inventory, _ = actions_used(files)
    assert [x["owner"] for x in inventory] == ["a", "a", "b"]
    assert inventory[0] == {
        "owner": "a",
        "repo": "repo",
        "path": None,
        "refs": ("v1", "v2"),
        "files": ("a.yml", "b.yml"),
    }
    assert inventory[1] == {
        "owner": "a",
        "repo": "repo",
        "path": "path",
        "refs": ("v1",),
        "files": ("b.yml",),
    }
