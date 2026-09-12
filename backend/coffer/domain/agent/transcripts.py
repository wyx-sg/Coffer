"""Agent transcript sessions — pure value object, layout map, and scrubbing.

An agent persists each of its past conversations as one ``.jsonl`` file under a
per-type directory of its config dir (Claude Code: ``projects/``, Codex:
``sessions/``). Coffer reads those files read-only to offer a browse surface —
it never writes them, and it keeps no message text: a session is projected down
to what the list shows (title, project, counts, timestamps, source path).

Everything here is pure: the filesystem walk and the per-agent parsers live in
``infrastructure/agent``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from coffer.domain.agent.types import AgentType

# Where each agent type keeps its per-session .jsonl files, relative to the
# agent's effective config dir.
_SESSIONS_SUBDIR: dict[str, str] = {
    AgentType.CLAUDE_CODE.value: "projects",
    AgentType.CODEX.value: "sessions",
}


class UnsupportedAgentTypeError(ValueError):
    """Raised when an agent type has no known transcript layout."""


def sessions_dir(agent_type_value: str, config_dir: Path) -> Path:
    """Directory holding *agent_type_value*'s transcript files."""
    try:
        return config_dir / _SESSIONS_SUBDIR[agent_type_value]
    except KeyError as exc:
        raise UnsupportedAgentTypeError(agent_type_value) from exc


def supports_transcripts(agent_type_value: str) -> bool:
    """Whether the agent type has a known on-disk transcript layout."""
    return agent_type_value in _SESSIONS_SUBDIR


def is_transcript_file(path: Path) -> bool:
    """Whether *path* looks like a persisted transcript (one session per file)."""
    return path.suffix == ".jsonl"


@dataclass(frozen=True)
class TranscriptSession:
    """One past conversation, projected to what the browse list needs.

    Message *text* is deliberately absent: nothing reads it, and the reader
    caches one of these per file for the daemon's lifetime — an agent with
    thousands of past sessions would otherwise pin every transcript in memory.
    """

    session_id: str
    #: ``AgentType`` value. Kept as a plain string so the parsers and the reader
    #: can stay string-keyed all the way from the HTTP query.
    agent_type_value: str
    project_path: str | None
    started_at: datetime | None
    message_count: int = 0
    source_path: str = ""
    title: str | None = None
    last_activity_at: datetime | None = None


# ---------------------------------------------------------------------------
# Title scrubbing
# ---------------------------------------------------------------------------

_REDACTED = "[redacted]"

# Conservative, well-known secret shapes only, so ordinary prose survives. A
# session title is derived from what the user typed, and it is rendered in the
# UI and returned over HTTP — a pasted key must not travel with it.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),  # OpenAI-style
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),  # AWS access key id
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b"),  # bearer tokens
    re.compile(r"\beyJ[A-Za-z0-9._-]{20,}\b"),  # JWTs
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+"),  # password assignments
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),  # URL credentials user:pass@
    re.compile(r"(?i)\baws_secret_access_key\s*[=:]\s*\S+"),  # AWS secret key
)


def scrub_secrets(text: str) -> str:
    """Redact known secret shapes from *text*."""
    scrubbed = text
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(_REDACTED, scrubbed)
    return scrubbed


__all__ = [
    "TranscriptSession",
    "UnsupportedAgentTypeError",
    "is_transcript_file",
    "scrub_secrets",
    "sessions_dir",
    "supports_transcripts",
]
