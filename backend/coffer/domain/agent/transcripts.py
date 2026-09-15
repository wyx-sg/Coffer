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

    Message *text* is deliberately absent: the list never shows it, and the
    reader caches one of these per file for the daemon's lifetime — an agent
    with thousands of past sessions would otherwise pin every transcript in
    memory. Reading one session's turns is a separate, bounded act
    (:class:`TranscriptSessionBody`) that streams the file again rather than
    keeping anything.
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


#: Cap on one turn's text where it crosses the wire. A transcript runs to tens
#: of megabytes and a single pasted turn can be a large fraction of that, so a
#: page of a conversation is bounded twice over: by how many turns it carries
#: (the caller's window) and by how much of any one turn it shows. Past this the
#: text is cut and the turn says so — the whole file is one click away in the
#: user's own editor, which is where an unbounded read belongs.
MAX_MESSAGE_CHARS = 8_000


@dataclass(frozen=True)
class TranscriptMessage:
    """One conversational turn, as a reader is allowed to see it.

    ``text`` is already scrubbed (:func:`scrub_secrets`) and already cut to
    ``MAX_MESSAGE_CHARS`` by the time one of these exists. That ordering is the
    point: a transcript body is the one thing Coffer reads that can contain a
    key the user pasted into a prompt, and until this feature no body left the
    machine at all. Constructing the value IS the redaction, so there is no
    window in which an unscrubbed turn is sitting in a variable waiting for
    somebody downstream to remember.
    """

    role: str
    text: str
    timestamp: datetime | None = None
    #: The turn was longer than ``MAX_MESSAGE_CHARS`` and ``text`` is its start.
    truncated: bool = False


@dataclass(frozen=True)
class TranscriptSessionBody:
    """One session's summary plus a bounded window of its turns.

    ``session.message_count`` is the whole file's turn count; ``messages`` is
    the ``limit`` turns starting at ``offset``. The two are deliberately
    separate numbers — a reader looking at turns 0-199 of 812 should be told
    that, not shown 200 and left to assume.
    """

    session: TranscriptSession
    messages: list[TranscriptMessage]
    offset: int
    limit: int


def is_session_of(agent_type_value: str, config_dir: Path, candidate: Path) -> bool:
    """Whether *candidate* is one of this agent's own transcript files.

    The containment rule behind reading a single session: the caller hands back
    a ``source_path`` the listing gave it, and that is all the authority it has
    — an arbitrary path must not become a file read. Both paths are expected to
    be resolved already (so a symlink pointing out of the sessions dir is
    caught here rather than followed), and an agent type with no transcript
    layout contains nothing at all.
    """
    try:
        root = sessions_dir(agent_type_value, config_dir)
    except UnsupportedAgentTypeError:
        return False
    return is_transcript_file(candidate) and candidate.is_relative_to(root)


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
    "MAX_MESSAGE_CHARS",
    "TranscriptMessage",
    "TranscriptSession",
    "TranscriptSessionBody",
    "UnsupportedAgentTypeError",
    "is_session_of",
    "is_transcript_file",
    "scrub_secrets",
    "sessions_dir",
    "supports_transcripts",
]
