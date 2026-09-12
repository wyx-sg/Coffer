"""Unit tests for the pure transcript layout map, value object, and scrubbing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.domain.agent.transcripts import (
    TranscriptSession,
    UnsupportedAgentTypeError,
    is_transcript_file,
    scrub_secrets,
    sessions_dir,
    supports_transcripts,
)


def test_claude_code_sessions_dir() -> None:
    assert sessions_dir("claude_code", Path("/home/u/.claude")) == Path("/home/u/.claude/projects")


def test_codex_sessions_dir() -> None:
    assert sessions_dir("codex", Path("/home/u/.codex")) == Path("/home/u/.codex/sessions")


def test_unknown_agent_rejected() -> None:
    with pytest.raises(UnsupportedAgentTypeError):
        sessions_dir("nonexistent_agent", Path("/x"))


def test_supports_transcripts_only_for_known_types() -> None:
    assert supports_transcripts("claude_code")
    assert supports_transcripts("codex")
    assert not supports_transcripts("nonexistent_agent")


def test_only_jsonl_is_transcript() -> None:
    assert is_transcript_file(Path("rollout-1.jsonl"))
    assert not is_transcript_file(Path("notes.md"))


def test_session_defaults_and_fields() -> None:
    s = TranscriptSession(
        session_id="abc",
        agent_type_value="claude_code",
        project_path="/repo",
        started_at=datetime(2026, 5, 1, tzinfo=UTC),
        message_count=2,
        source_path="/x.jsonl",
        title="Fix login",
    )
    assert s.message_count == 2
    assert s.project_path == "/repo"
    assert s.last_activity_at is None  # defaulted


def test_scrub_redacts_known_secret_shapes() -> None:
    text = "use sk-abcdefghijklmnopqrstuvwxyz and ghp_abcdefghijklmnopqrstuvwxyz1234"
    out = scrub_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in out
    assert "ghp_abcdefghijklmnopqrstuvwxyz1234" not in out
    assert out.count("[redacted]") == 2
    assert out.startswith("use ")


def test_scrub_leaves_ordinary_prose_intact() -> None:
    text = "refactor the payments module so retries are bounded"
    assert scrub_secrets(text) == text
