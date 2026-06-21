"""Unit tests for FileTranscriptReader search/filter/sort + the mtime cache."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader


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


def test_filter_by_started_after(tmp_path: Path) -> None:
    _make_codex_tree(tmp_path)
    r = FileTranscriptReader()
    after = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)
    total, page = r.search_session_summaries(
        agent_type_value="codex", config_dir=str(tmp_path), started_after=after, limit=100, offset=0
    )
    assert total == 1
    assert page[0].session_id == "c"


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
    assert total == 3
    assert [s.session_id for s in page] == ["b"]


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
