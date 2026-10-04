"""Which notes a session's tool calls named, over a moving window and a bounded cache."""

from __future__ import annotations

import json
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

from coffer.infrastructure.memory import transcript_reads


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    transcript_reads.clear_cache()


def _record(root: pathlib.Path, slug: str, at: datetime) -> str:
    note = f"{root}/coffer/notes/{slug}.md"
    return json.dumps(
        {
            "timestamp": at.isoformat(),
            "message": {"content": [{"type": "tool_use", "input": {"file_path": note}}]},
        }
    )


def test_the_window_decides_per_call_and_a_widened_window_is_not_answered_from_a_narrow_one(
    tmp_path: pathlib.Path,
) -> None:
    root = tmp_path / "memory"
    config = tmp_path / "cc"
    session = config / "projects" / "p" / "s.jsonl"
    session.parent.mkdir(parents=True)
    now = datetime.now(tz=UTC)
    session.write_text(
        "\n".join([_record(root, "old", now - timedelta(days=20)), _record(root, "new", now)])
        + "\n"
    )

    narrow = transcript_reads.notes_read("claude_code", config, root, now - timedelta(days=7))
    wide = transcript_reads.notes_read("claude_code", config, root, now - timedelta(days=30))

    assert narrow == {"coffer/new"}
    assert wide == {"coffer/old", "coffer/new"}


def test_the_cache_is_bounded(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transcript_reads, "_CACHE_LIMIT", 2)
    root = tmp_path / "memory"
    config = tmp_path / "cc"
    now = datetime.now(tz=UTC)
    for n in range(5):
        session = config / "projects" / f"p{n}" / "s.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(_record(root, f"n{n}", now) + "\n")

    found = transcript_reads.notes_read("claude_code", config, root, now - timedelta(days=1))

    assert found == {f"coffer/n{n}" for n in range(5)}
    assert len(transcript_reads._CACHE) == 2
