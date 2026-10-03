"""What a reply changed in each file, built from file content (spec chat "Record
what each reply changed in each file"): Claude Code's snapshot-then-compare and
Codex's per-change diffs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coffer.domain.chat.reply_file import MAX_DIFF_FILE_BYTES, MAX_REPLY_FILES
from coffer.infrastructure.chat.codex_mapping import CodexParseState, map_codex_notification
from coffer.infrastructure.chat.reply_file_diffs import ReplyFileRecorder, write_hooks


@pytest.mark.acceptance(spec="chat", scenario="a reply's edits to one file become one diff")
def test_two_edits_to_one_file_are_one_diff_against_its_content_before_the_first(
    tmp_path: Path,
) -> None:
    client = tmp_path / "ws_client.py"
    client.write_text("a\nb\nc\nd\ne\n")
    recorder = ReplyFileRecorder(str(tmp_path))

    recorder.snapshot("ws_client.py")  # first edit's hook: relative to the turn's cwd
    client.write_text("a\nB\nc\nd\ne\n")
    recorder.snapshot(str(client))  # second edit: the first snapshot is kept
    client.write_text("a\nB\nc\nd\nE\nf\n")
    new = tmp_path / "test_ws.py"
    recorder.snapshot(str(new))  # absent before the write
    new.write_text("x\ny\n")

    files = recorder.files()

    assert [f.path for f in files] == [str(client), str(new)]
    edited, created = files
    assert (edited.added, edited.removed) == (3, 2)
    assert edited.diff is not None
    assert edited.diff.startswith(f"--- a/{str(client).lstrip('/')}\n+++ b/")
    assert "-b\n+B\n" in edited.diff and "-e\n+E\n+f\n" in edited.diff
    assert edited.diff.count("\n@@ ") == 1  # one hunk, covering both edits
    assert (created.added, created.removed) == (2, 0)
    assert created.diff is not None and "@@ -0,0 +1,2 @@\n+x\n+y\n" in created.diff
    assert created.diff_omitted is None


def test_a_file_whose_content_ended_unchanged_is_dropped(tmp_path: Path) -> None:
    f = tmp_path / "same.txt"
    f.write_text("one\n")
    gone = tmp_path / "never.txt"
    recorder = ReplyFileRecorder(str(tmp_path))
    recorder.snapshot(str(f))
    recorder.snapshot(str(gone))
    f.write_text("two\n")
    f.write_text("one\n")  # changed and changed back

    assert recorder.files() == []


def test_a_deleted_file_is_all_removed_lines(tmp_path: Path) -> None:
    f = tmp_path / "old.txt"
    f.write_text("p\nq\n")
    recorder = ReplyFileRecorder(str(tmp_path))
    recorder.snapshot(str(f))
    f.unlink()

    (only,) = recorder.files()
    assert (only.added, only.removed) == (0, 2)
    assert only.diff is not None and "@@ -1,2 +0,0 @@\n-p\n-q\n" in only.diff


def test_a_missing_final_newline_is_marked_not_merged_into_the_next_line(tmp_path: Path) -> None:
    f = tmp_path / "n.txt"
    f.write_text("a\nb")
    recorder = ReplyFileRecorder(str(tmp_path))
    recorder.snapshot(str(f))
    f.write_text("a\nb\n")

    (only,) = recorder.files()
    assert (only.added, only.removed) == (1, 1)
    assert only.diff is not None
    assert "-b\n\\ No newline at end of file\n+b\n" in only.diff


@pytest.mark.acceptance(spec="chat", scenario="a binary file is listed without a diff")
def test_a_file_over_a_megabyte_is_listed_with_counts_and_no_diff(tmp_path: Path) -> None:
    big = tmp_path / "big.txt"
    recorder = ReplyFileRecorder(str(tmp_path))
    recorder.snapshot(str(big))
    big.write_text("line\n" * (3 * 1024 * 1024 // 5))
    assert big.stat().st_size > MAX_DIFF_FILE_BYTES

    (only,) = recorder.files()

    assert only.diff is None and only.diff_omitted == "too_large"
    assert (only.added, only.removed) == (3 * 1024 * 1024 // 5, 0)


def test_a_file_that_is_not_text_is_listed_without_a_diff(tmp_path: Path) -> None:
    blob = tmp_path / "pic.bin"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01")
    recorder = ReplyFileRecorder(str(tmp_path))
    recorder.snapshot(str(blob))
    blob.write_bytes(b"\xff\xfe\x00\x00 changed\n")

    (only,) = recorder.files()
    assert only.diff is None and only.diff_omitted == "binary"


def test_only_the_first_files_of_a_reply_are_watched(tmp_path: Path) -> None:
    recorder = ReplyFileRecorder(str(tmp_path))
    for i in range(MAX_REPLY_FILES + 5):
        recorder.snapshot(str(tmp_path / f"f{i}.txt"))
        (tmp_path / f"f{i}.txt").write_text("x\n")

    assert len(recorder.files()) == MAX_REPLY_FILES


async def test_the_hook_snapshots_the_path_and_decides_nothing(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("1\n")
    nb = tmp_path / "n.ipynb"
    recorder = ReplyFileRecorder(str(tmp_path))
    (matcher,) = write_hooks(recorder)["PreToolUse"]
    hook: Any = matcher.hooks[0]

    assert matcher.matcher == "Edit|MultiEdit|Write|NotebookEdit"
    assert await hook({"tool_input": {"file_path": str(f)}}, "t1", None) == {}
    assert await hook({"tool_input": {"notebook_path": str(nb)}}, "t2", None) == {}
    assert await hook({"tool_input": {"command": "ls"}}, "t3", None) == {}
    assert await hook({}, "t4", None) == {}
    f.write_text("2\n")
    nb.write_text("{}\n")

    assert sorted(x.path for x in recorder.files()) == sorted([str(f), str(nb)])


# --- Codex -----------------------------------------------------------------


def _file_change(state: CodexParseState, changes: list[dict[str, object]], status: str) -> None:
    map_codex_notification(
        "item/completed",
        {"item": {"type": "fileChange", "id": "f", "changes": changes, "status": status}},
        state,
    )


def test_codex_diffs_for_one_path_are_kept_in_order_and_summed() -> None:
    state = CodexParseState()
    _file_change(
        state,
        [{"path": "/w/a.py", "kind": {"type": "update"}, "diff": "@@ -1,2 +1,2 @@\n x\n-y\n+Y\n"}],
        "completed",
    )
    _file_change(
        state,
        [
            {
                "path": "/w/a.py",
                "kind": {"type": "update"},
                "diff": "--- a/w/a.py\n+++ b/w/a.py\n@@ -5 +5,2 @@\n z\n+w\n",
            },
            {"path": "/w/new.py", "kind": {"type": "add"}, "diff": "one\ntwo\n"},
        ],
        "completed",
    )

    a, new = state.reply_files.files()

    assert (a.path, a.added, a.removed) == ("/w/a.py", 2, 1)
    assert a.diff is not None
    assert a.diff.startswith("--- a/w/a.py\n+++ b/w/a.py\n@@ -1,2 +1,2 @@\n")
    assert a.diff.index("-y\n+Y") < a.diff.index("+w")
    assert (new.added, new.removed) == (2, 0)
    assert new.diff is not None and "@@ -0,0 +1,2 @@\n+one\n+two\n" in new.diff


def test_codex_a_failed_change_records_nothing() -> None:
    state = CodexParseState()
    _file_change(
        state,
        [{"path": "/w/a.py", "kind": {"type": "update"}, "diff": "@@ -1 +1 @@\n-a\n+b\n"}],
        "failed",
    )

    assert state.reply_files.files() == []
