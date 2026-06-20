from pathlib import Path

import pytest

from coffer.domain.distill.locations import (
    UnsupportedAgentTypeError,
    is_transcript_file,
    sessions_dir,
)


def test_claude_code_sessions_dir():
    assert sessions_dir("claude_code", Path("/home/u/.claude")) == Path("/home/u/.claude/projects")


def test_codex_sessions_dir():
    assert sessions_dir("codex", Path("/home/u/.codex")) == Path("/home/u/.codex/sessions")


def test_unknown_agent_rejected():
    with pytest.raises(UnsupportedAgentTypeError):
        sessions_dir("nonexistent_agent", Path("/x"))


def test_only_jsonl_is_transcript():
    assert is_transcript_file(Path("rollout-1.jsonl"))
    assert not is_transcript_file(Path("notes.md"))
