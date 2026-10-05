"""An agent's own sessions, as Coffer lists them (spec agent-registry
"List an agent's native sessions through the agent").

The agents keep their conversations themselves — Claude Code in its project
files, Codex in its thread store — and answer for them through their own
listing. Coffer holds no copy: a session here is only what a list row shows.

Pure: the Agent SDK and the Codex app-server live in ``infrastructure/agent``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from coffer.domain.error_base import CofferError
from coffer.domain.pagination import Page

#: What a session id may look like on the wire (both agents use UUIDs). Checked
#: before the id reaches an agent's API or a command line.
SESSION_ID_PATTERN = r"^[A-Za-z0-9-]{1,128}$"
_SESSION_ID = re.compile(SESSION_ID_PATTERN)


def is_session_id(value: str) -> bool:
    """Whether *value* is shaped like a session id."""
    return _SESSION_ID.fullmatch(value) is not None


class UnsupportedAgentType(CofferError):  # noqa: N818
    """The agent's type has no native-session listing. Maps to 400."""

    code = "AGENT_TYPE_UNSUPPORTED"

    def __init__(self, agent_type: str) -> None:
        super().__init__(f"agent type {agent_type!r} has no native sessions to list")
        self.agent_type = agent_type


class NativeSessionNotFound(CofferError):  # noqa: N818
    """The agent holds no session with this id. Maps to 404."""

    code = "NATIVE_SESSION_NOT_FOUND"

    def __init__(self, session_id: str) -> None:
        super().__init__(f"no such session: {session_id}")
        self.session_id = session_id


class NativeSessionInvalid(CofferError):  # noqa: N818
    """The agent refused the request as malformed (an id it cannot parse, an
    empty title). Maps to 400."""

    code = "NATIVE_SESSION_INVALID"


@dataclass(frozen=True)
class NativeSession:
    """One session as the agent reports it."""

    session_id: str
    title: str
    cwd: str | None
    created_at: datetime | None
    last_activity_at: datetime | None


@dataclass(frozen=True)
class SessionPlace:
    """Which chat and thread of its channel a conversation lives in."""

    chat_kind: str | None = None
    thread: bool = False
    parallel_mark: str | None = None
    chat_name: str | None = None


@dataclass(frozen=True)
class SessionChannel:
    """The channel a conversation is driven from (its binding)."""

    channel_uid: str
    #: The channel's label now; ``None`` once the channel was deleted.
    channel: str | None
    chat_id: str
    #: The channel's type key; ``None`` once the channel was deleted.
    platform: str | None = None
    place: SessionPlace | None = None


@dataclass(frozen=True)
class SessionConversation:
    """The channel conversation a session id belongs to (spec agent-registry
    "List an agent's native sessions through the agent")."""

    conversation_id: str
    running: bool
    needs_you: bool
    channel: SessionChannel | None = None


@dataclass(frozen=True)
class NativeSessionPage(Page[NativeSession]):
    """A page of sessions. ``total`` is the number of sessions matching the
    search, or ``None`` where the source cannot count without reading them all
    (Codex pages by its own cursor). ``conversations`` holds, by session id, the
    conversation of each session on the page that one points at."""

    total: int | None = None
    conversations: Mapping[str, SessionConversation] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Title scrubbing
# ---------------------------------------------------------------------------

_REDACTED = "[redacted]"

# Conservative, well-known secret shapes only, so ordinary prose survives. A
# session title can be derived from what the user typed, and it is rendered in
# the UI and returned over HTTP — a pasted key must not travel with it.
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
    "SESSION_ID_PATTERN",
    "NativeSession",
    "NativeSessionInvalid",
    "NativeSessionNotFound",
    "NativeSessionPage",
    "SessionChannel",
    "SessionConversation",
    "SessionPlace",
    "UnsupportedAgentType",
    "is_session_id",
    "scrub_secrets",
]
