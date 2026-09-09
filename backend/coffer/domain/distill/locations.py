"""Pure mapping from agent workspace root to transcript locations."""

from __future__ import annotations

from pathlib import Path

_SESSIONS_SUBDIR = {"claude_code": "projects", "codex": "sessions"}


class UnsupportedAgentTypeError(ValueError):
    """Raised when an agent type has no known transcript layout."""


def sessions_dir(agent_type_value: str, config_dir: Path) -> Path:
    try:
        return config_dir / _SESSIONS_SUBDIR[agent_type_value]
    except KeyError as exc:
        raise UnsupportedAgentTypeError(agent_type_value) from exc


def supports_transcripts(agent_type_value: str) -> bool:
    """Whether the agent type has a known on-disk transcript layout."""
    return agent_type_value in _SESSIONS_SUBDIR


def is_transcript_file(path: Path) -> bool:
    return path.suffix == ".jsonl"
