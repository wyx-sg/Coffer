"""Integration tests for FileTranscriptReader against real temp .jsonl files."""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.infrastructure.distill.transcript_reader import FileTranscriptReader

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

# Claude Code record lines: slug = cwd path with '/' -> '-'
_CLAUDE_LINES = [
    json.dumps(
        {
            "type": "user",
            "cwd": "/my/project",
            "sessionId": "claude-session-1",
            "timestamp": "2026-06-01T10:00:00Z",
            "message": {"role": "user", "content": "hello agent"},
        }
    ),
    json.dumps(
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Hello! I will help you."},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "SECRET_VAL"}},
                ],
            },
        }
    ),
]

# Codex rollout record lines
_CODEX_LINES = [
    json.dumps({"type": "session_meta", "cwd": "/codex/repo", "id": "codex-session-1"}),
    json.dumps({"type": "message", "role": "user", "content": "run the tests"}),
    "not valid json",
    json.dumps({"type": "message", "role": "assistant", "content": "Tests pass!"}),
]


@pytest.fixture
def config_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create fake config dirs with real transcript files."""
    # Claude Code: ~/.claude/projects/<slug>/<file>.jsonl
    claude_cfg = tmp_path / "claude_cfg"
    slug = "-my-project"  # /my/project -> -my-project
    claude_project_dir = claude_cfg / "projects" / slug
    claude_project_dir.mkdir(parents=True)
    (claude_project_dir / "transcript.jsonl").write_text("\n".join(_CLAUDE_LINES) + "\n")

    # Codex: ~/.codex/sessions/2026/06/01/rollout-x.jsonl
    codex_cfg = tmp_path / "codex_cfg"
    codex_session_dir = codex_cfg / "sessions" / "2026" / "06" / "01"
    codex_session_dir.mkdir(parents=True)
    (codex_session_dir / "rollout-session1.jsonl").write_text("\n".join(_CODEX_LINES) + "\n")

    return tmp_path


class TestFileTranscriptReaderClaudeCode:
    def test_list_sessions_discovers_claude_file(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        sessions = reader.list_sessions(
            agent_type_value="claude_code",
            config_dir=str(config_dir / "claude_cfg"),
        )
        assert len(sessions) == 1
        s = sessions[0]
        assert s.session_id == "claude-session-1"
        assert s.project_path == "/my/project"

    def test_list_sessions_no_tool_payloads(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        sessions = reader.list_sessions(
            agent_type_value="claude_code",
            config_dir=str(config_dir / "claude_cfg"),
        )
        all_text = " ".join(m.text for s in sessions for m in s.messages)
        assert "SECRET_VAL" not in all_text

    def test_list_sessions_returns_empty_when_dir_missing(self, tmp_path: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        result = reader.list_sessions(
            agent_type_value="claude_code",
            config_dir=str(tmp_path / "nonexistent"),
        )
        assert result == []

    def test_read_session_returns_full_session(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        s = reader.read_session(
            agent_type_value="claude_code",
            config_dir=str(config_dir / "claude_cfg"),
            session_id="claude-session-1",
        )
        assert s.session_id == "claude-session-1"
        assert s.project_path == "/my/project"
        roles = [m.role for m in s.messages]
        assert "user" in roles
        assert "assistant" in roles
        # Tool payload must be dropped
        assert all("SECRET_VAL" not in m.text for m in s.messages)

    def test_read_session_raises_on_missing_session(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        with pytest.raises(KeyError):
            reader.read_session(
                agent_type_value="claude_code",
                config_dir=str(config_dir / "claude_cfg"),
                session_id="nonexistent-id",
            )


class TestFileTranscriptReaderCodex:
    def test_list_sessions_discovers_codex_file(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        sessions = reader.list_sessions(
            agent_type_value="codex",
            config_dir=str(config_dir / "codex_cfg"),
        )
        assert len(sessions) == 1
        s = sessions[0]
        assert s.session_id == "codex-session-1"
        assert s.project_path == "/codex/repo"

    def test_list_sessions_skips_bad_json_lines(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        sessions = reader.list_sessions(
            agent_type_value="codex",
            config_dir=str(config_dir / "codex_cfg"),
        )
        # Should not raise; bad line was silently skipped
        assert len(sessions) == 1

    def test_read_session_codex(self, config_dir: pathlib.Path) -> None:
        reader = FileTranscriptReader()
        s = reader.read_session(
            agent_type_value="codex",
            config_dir=str(config_dir / "codex_cfg"),
            session_id="codex-session-1",
        )
        assert [m.role for m in s.messages] == ["user", "assistant"]
        assert s.project_path == "/codex/repo"
