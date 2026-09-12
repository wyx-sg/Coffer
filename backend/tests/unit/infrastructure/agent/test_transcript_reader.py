"""Unit tests for FileTranscriptReader search/filter/sort + the mtime cache.

Every test builds its own transcript tree under ``tmp_path``; the reader is
never pointed at a real ``~/.claude`` or ``~/.codex``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from coffer.domain.agent.transcripts import UnsupportedAgentTypeError
from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader


def _codex_session(
    path: Path, *, sid: str, cwd: str, ts_start: str, ts_end: str, user_text: str
) -> None:
    lines = [
        json.dumps(
            {"timestamp": ts_start, "type": "session_meta", "payload": {"id": sid, "cwd": cwd}}
        ),
        json.dumps(
            {
                "timestamp": ts_start,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_text}],
                },
            }
        ),
        json.dumps(
            {
                "timestamp": ts_end,
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                },
            }
        ),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_codex_tree(root: Path) -> Path:
    """Three sessions; session 'a' runs long so last_activity order ≠ start order."""
    d = root / "sessions" / "2026" / "05"
    d.mkdir(parents=True)
    _codex_session(
        d / "rollout-a.jsonl",
        sid="a",
        cwd="/proj/alpha",
        ts_start="2026-05-01T00:00:00Z",
        ts_end="2026-05-09T00:00:00Z",
        user_text="fix the alpha login bug",
    )
    _codex_session(
        d / "rollout-b.jsonl",
        sid="b",
        cwd="/proj/beta",
        ts_start="2026-05-02T00:00:00Z",
        ts_end="2026-05-02T02:00:00Z",
        user_text="add beta dashboard",
    )
    _codex_session(
        d / "rollout-c.jsonl",
        sid="c",
        cwd="/proj/alpha",
        ts_start="2026-05-03T00:00:00Z",
        ts_end="2026-05-03T00:30:00Z",
        user_text="refactor alpha payments",
    )
    return d


def test_missing_sessions_dir_is_empty_not_an_error(tmp_path: Path) -> None:
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert (total, page) == (0, [])


def test_unknown_agent_type_is_rejected(tmp_path: Path) -> None:
    r = FileTranscriptReader()
    with pytest.raises(UnsupportedAgentTypeError):
        r.search_session_summaries(
            agent_type_value="nonexistent", config_dir=str(tmp_path), limit=10, offset=0
        )


def test_lists_every_session_with_summary_fields(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert total == 3
    by_id = {s.session_id: s for s in page}
    a = by_id["a"]
    assert a.title == "fix the alpha login bug"
    assert a.project_path == "/proj/alpha"
    assert a.message_count == 2
    assert a.source_path.endswith("rollout-a.jsonl")


def test_non_jsonl_files_are_ignored(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    (d / "notes.md").write_text("not a transcript", encoding="utf-8")
    r = FileTranscriptReader()
    total, _ = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert total == 3


def test_search_matches_title_or_project(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), query="alpha", limit=100, offset=0
    )
    assert total == 2
    assert {s.session_id for s in page} == {"a", "c"}


def test_search_is_case_insensitive(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), query="BETA", limit=100, offset=0
    )
    assert total == 1
    assert page[0].session_id == "b"


def test_filter_by_project_exact(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        project="/proj/alpha",
        limit=100,
        offset=0,
    )
    assert total == 2
    assert {s.session_id for s in page} == {"a", "c"}


def test_sort_by_started_at_asc_and_desc(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    _, asc = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="started_at",
        order="asc",
        limit=100,
        offset=0,
    )
    assert [s.session_id for s in asc] == ["a", "b", "c"]
    _, desc = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="started_at",
        order="desc",
        limit=100,
        offset=0,
    )
    assert [s.session_id for s in desc] == ["c", "b", "a"]


def test_sort_by_message_count(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    # Give 'b' a third turn so it outranks the others by message count.
    with (d / "rollout-b.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(
            "\n"
            + json.dumps(
                {
                    "timestamp": "2026-05-02T03:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "one more"}],
                    },
                }
            )
        )
    r = FileTranscriptReader()
    _, page = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="message_count",
        order="desc",
        limit=100,
        offset=0,
    )
    assert page[0].session_id == "b"
    assert page[0].message_count == 3


def test_default_sort_is_last_activity_desc(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    _, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    # a ends 05-09 (latest), c ends 05-03, b ends 05-02
    assert [s.session_id for s in page] == ["a", "c", "b"]


def test_pagination_limit_offset(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    total, page = r.search_session_summaries(
        agent_type_value="codex",
        config_dir=str(tmp_path),
        sort="started_at",
        order="asc",
        limit=1,
        offset=1,
    )
    assert total == 3  # total is the MATCHED count, not the page length
    assert [s.session_id for s in page] == ["b"]


def test_unreadable_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    broken = d / "rollout-broken.jsonl"
    broken.write_bytes(b"\x00\x01\x02")
    r = FileTranscriptReader()
    total, _ = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    # The binary file parses to an empty session rather than killing the listing.
    assert total == 4


def test_cache_reparses_only_changed_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    calls = {"n": 0}
    orig = r._parse_file

    def counting(agent_type_value: str, path: Path):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return orig(agent_type_value, path)

    monkeypatch.setattr(r, "_parse_file", counting)

    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 3  # all parsed on first call

    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 3  # full cache hit; nothing re-parsed

    p = d / "rollout-b.jsonl"
    st = p.stat()
    os.utime(p, (st.st_atime, st.st_mtime + 10))  # bump mtime
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert calls["n"] == 4  # only the changed file re-parsed


def test_cache_prunes_entries_for_deleted_files(tmp_path: Path) -> None:
    d = _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert len(r._cache) == 3
    (d / "rollout-b.jsonl").unlink()
    total, _ = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), limit=100, offset=0
    )
    assert total == 2
    assert len(r._cache) == 2  # the deleted file's entry is gone, not leaked
