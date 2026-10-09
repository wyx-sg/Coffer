"""The diff an audit row carries for an edit (coffer.domain.audit_diff)."""

from __future__ import annotations

from coffer.domain.audit_diff import (
    MAX_DIFF_BYTES,
    as_text,
    capped_diff,
    commit_change,
    is_diffable,
    text_diff,
)


def test_a_short_diff_is_kept_whole() -> None:
    assert capped_diff("-a\n+b\n") == {"diff": "-a\n+b\n"}


def test_a_diff_at_the_cap_is_not_cut() -> None:
    exact = "x" * MAX_DIFF_BYTES
    assert capped_diff(exact) == {"diff": exact}


def test_a_long_diff_is_cut_to_the_cap_and_says_how_long_it_was() -> None:
    long = "+" + "y" * (MAX_DIFF_BYTES * 2)
    out = capped_diff(long)
    assert out["diff_truncated"] is True
    assert out["diff_bytes"] == len(long.encode("utf-8"))
    assert len(out["diff"].encode("utf-8")) == MAX_DIFF_BYTES
    assert long.startswith(out["diff"])


def test_the_cap_counts_utf8_bytes_and_never_splits_a_character() -> None:
    # Three bytes each: the cap falls inside one of them.
    long = "中" * (MAX_DIFF_BYTES // 3 + 10)
    out = capped_diff(long)
    raw = out["diff"].encode("utf-8")
    assert len(raw) <= MAX_DIFF_BYTES
    assert MAX_DIFF_BYTES - len(raw) < 3
    assert out["diff_bytes"] == len(long.encode("utf-8"))


def test_text_diff_is_a_unified_diff_with_three_lines_of_context() -> None:
    before = "".join(f"line {i}\n" for i in range(10))
    after = before.replace("line 5\n", "line five\n")
    diff = text_diff(before, after, "knowledge/c/doc.md")["diff"]
    assert diff.startswith("--- a/knowledge/c/doc.md\n+++ b/knowledge/c/doc.md\n")
    assert "@@ -3,7 +3,7 @@\n" in diff
    assert "-line 5\n+line five\n" in diff
    assert " line 1\n" not in diff  # outside the three lines of context


def test_text_diff_of_the_same_text_is_empty() -> None:
    assert text_diff("same\n", "same\n", "knowledge/a.md") == {}


def test_a_missing_final_newline_does_not_run_into_the_next_line() -> None:
    diff = text_diff("a", "b", "knowledge/a.md")["diff"]
    assert diff.endswith("-a\n+b\n")


def test_only_knowledge_and_skill_text_is_diffable() -> None:
    assert is_diffable("knowledge/team/doc.md")
    assert is_diffable("skills/pdf/SKILL.md")
    assert is_diffable("skills/pdf/scripts/run.py")
    # Config may carry an MCP server's env or headers; secrets are secrets.
    assert not is_diffable("resources/mcp_server/github.json")
    assert not is_diffable("state/agent/claude.json")
    assert not is_diffable("secret/abc.json")
    assert not is_diffable("skills/pdf/.env")
    assert not is_diffable("skills/pdf/.env.md")
    assert not is_diffable("skills/pdf/config.json")


def test_as_text_refuses_binary_and_undecodable_bytes() -> None:
    assert as_text(b"plain\n") == "plain\n"
    assert as_text(None) is None
    assert as_text(b"\x00\x01") is None
    assert as_text(b"\xff\xfe") is None


def _reader(files: dict[tuple[str, str], bytes]):  # type: ignore[no-untyped-def]
    return lambda ref, path: files.get((ref, path))


def test_commit_change_names_the_change_and_diffs_one_file() -> None:
    read = _reader({("v^", "knowledge/a.md"): b"one\n", ("v", "knowledge/a.md"): b"two\n"})
    out = commit_change(read, "v", ["knowledge/a.md"])
    assert out["change"] == "modified"
    assert "-one\n+two\n" in out["diff"]


def test_commit_change_never_diffs_config() -> None:
    read = _reader(
        {
            ("v^", "resources/mcp_server/x.json"): b'{"env": {"T": "old"}}',
            ("v", "resources/mcp_server/x.json"): b'{"env": {"T": "new"}}',
        }
    )
    assert commit_change(read, "v", ["resources/mcp_server/x.json"]) == {"change": "modified"}


def test_commit_change_of_an_added_file_has_no_diff() -> None:
    read = _reader({("v", "knowledge/new.md"): b"fresh\n"})
    assert commit_change(read, "v", ["knowledge/new.md"]) == {"change": "added"}


def test_commit_change_over_several_files_counts_them_and_caps_one_diff() -> None:
    big = "".join(f"{i}\n" for i in range(4000)).encode()
    read = _reader(
        {
            ("v^", "skills/s/SKILL.md"): b"old\n",
            ("v", "skills/s/SKILL.md"): big,
            ("v^", "skills/s/extra.md"): b"gone\n",
            ("v", "skills/s/added.md"): b"new\n",
        }
    )
    out = commit_change(read, "v", ["skills/s/SKILL.md", "skills/s/extra.md", "skills/s/added.md"])
    assert (out["modified"], out["deleted"], out["added"]) == (1, 1, 1)
    assert "change" not in out
    assert out["diff_truncated"] is True
    assert out["diff_bytes"] > MAX_DIFF_BYTES


def test_commit_change_of_untouched_paths_is_empty() -> None:
    assert commit_change(_reader({}), "v", ["knowledge/a.md"]) == {}
