"""Defensive per-agent transcript parsers (pure functions).

Design principles:
- Never raise on a single bad line; skip and continue.
- Keep only natural-language *text* blocks; drop tool_use / tool_result /
  function-call blocks entirely.
- Apply scrub_text to every message text before storing.
- Derive ``title`` (Claude Code ai-title / first real user message),
  ``project_path`` (``cwd``), ``session_id``, and ``started_at`` /
  ``last_activity_at`` (first / last ``timestamp``).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from coffer.domain.distill.scrub import scrub_text
from coffer.domain.distill.session import TranscriptMessage, TranscriptSession

log = logging.getLogger(__name__)

# Title cap — a session title is a single short line for the history table.
_TITLE_MAX_CHARS = 80

# Lowercased prefixes of non-conversational user messages that must NOT become a
# title: environment/instructions blocks, shell-command echoes, slash commands,
# and injected reminders. Codex's first "user" turn is almost always one of these.
_TITLE_NOISE_PREFIXES: tuple[str, ...] = (
    "<environment_context",
    "<user_shell_command",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command",
    "<system-reminder",
    "# agents.md instructions",
    "# claude.md instructions",
    "caveat:",
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string; return None on any failure.

    Always returns a tz-aware datetime (UTC when no offset is present) so that
    comparisons across sessions never raise TypeError on mixed aware/naive values.
    """
    if not ts:
        return None
    try:
        # Python 3.11+ handles Z suffix; for 3.10 compatibility replace it.
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _text_from_content(content: object) -> str | None:
    """Extract plain text from a Claude ``content`` value (str or block list).

    Returns None when the content carries no text at all (e.g. it is purely a
    tool_use payload that we intentionally discard).
    """
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if text:
                    parts.append(str(text))
            # tool_use / tool_result blocks are silently dropped
        return "".join(parts) or None
    return None


def _text_from_codex_content(content: object) -> str | None:
    """Extract text from a Codex message ``content`` (str or typed-block list).

    Codex blocks use ``input_text`` / ``output_text`` (and plain ``text``);
    tool / reasoning / other blocks are dropped.
    """
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if isinstance(btype, str) and (btype == "text" or btype.endswith("_text")):
                text = block.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts) or None
    return None


def _is_real_user_text(text: str) -> bool:
    """True when *text* reads like a genuine human prompt suitable as a title.

    Filters out the non-conversational preambles (environment/instructions
    blocks, shell-command echoes, slash commands) that lead most sessions.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("/"):  # bare slash command, e.g. "/clear"
        return False
    return not stripped.lower().startswith(_TITLE_NOISE_PREFIXES)


def _make_title(text: str) -> str:
    """First non-empty line of *text*, whitespace-collapsed and truncated."""
    first_line = ""
    for line in text.strip().splitlines():
        if line.strip():
            first_line = line.strip()
            break
    collapsed = " ".join(first_line.split())
    if len(collapsed) > _TITLE_MAX_CHARS:
        return collapsed[: _TITLE_MAX_CHARS - 1].rstrip() + "…"
    return collapsed


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_claude_code(lines: Iterable[str], *, source_path: str) -> TranscriptSession:
    """Parse a Claude Code persisted transcript (one JSON object per line).

    Tolerates non-JSON lines (skipped). Keeps only text content blocks;
    drops tool_use / tool_result entirely.
    """
    messages: list[TranscriptMessage] = []
    project_path: str | None = None
    session_id: str = source_path  # fallback: use path if record carries none
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    ai_title: str | None = None
    first_user_title: str | None = None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record: dict[object, object] = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("claude_code parser: skipping non-JSON line in %s", source_path)
            continue

        if not isinstance(record, dict):
            continue

        # Extract metadata from any record that carries it (first wins).
        if project_path is None and isinstance(record.get("cwd"), str):
            project_path = record["cwd"]  # type: ignore[assignment]
        if session_id == source_path and isinstance(record.get("sessionId"), str):
            session_id = record["sessionId"]  # type: ignore[assignment]
        ts = _parse_iso(record.get("timestamp"))  # type: ignore[arg-type]
        if ts is not None:
            if started_at is None:
                started_at = ts
            last_activity_at = ts  # last timestamped event wins

        # Claude Code persists its own session title, updated over time — latest wins.
        if record.get("type") == "ai-title":
            at = record.get("aiTitle")
            if isinstance(at, str) and at.strip():
                ai_title = at.strip()
            continue

        # Extract message text.
        msg_obj = record.get("message")
        if not isinstance(msg_obj, dict):
            continue
        role = msg_obj.get("role")
        if not isinstance(role, str):
            continue
        content = msg_obj.get("content")
        text = _text_from_content(content)
        if text is not None:
            scrubbed = scrub_text(text)
            messages.append(TranscriptMessage(role=role, text=scrubbed))
            if first_user_title is None and role == "user" and _is_real_user_text(scrubbed):
                first_user_title = _make_title(scrubbed)

    return TranscriptSession(
        session_id=session_id,
        agent_type_value="claude_code",
        project_path=project_path,
        started_at=started_at,
        messages=tuple(messages),
        source_path=source_path,
        title=ai_title or first_user_title,
        last_activity_at=last_activity_at,
    )


def parse_codex(lines: Iterable[str], *, source_path: str) -> TranscriptSession:
    """Parse a Codex rollout-*.jsonl transcript.

    The real persisted rollout wraps every event in a ``payload`` envelope:
    ``session_meta`` carries ``payload.cwd``/``payload.id``, and a conversation
    turn is a ``response_item`` whose ``payload.type == "message"`` (role +
    typed ``*_text`` content blocks). The parallel ``event_msg``
    user_message/agent_message events are UI duplicates and are dropped so turns
    are not double-counted. A flat ``message`` shape (older fixtures) and the
    live ``codex exec --json`` ``item.completed`` shape are also tolerated.

    Tolerates non-JSON / unrecognised lines (skipped); never raises on one line.
    """
    messages: list[TranscriptMessage] = []
    project_path: str | None = None
    session_id: str = source_path  # fallback
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    first_user_title: str | None = None

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record: dict[object, object] = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("codex parser: skipping non-JSON line in %s", source_path)
            continue

        if not isinstance(record, dict):
            continue

        kind = record.get("type")
        payload = record.get("payload")
        # Real rollout nests everything under ``payload``; flat/live shapes don't.
        inner = payload if isinstance(payload, dict) else record

        # timestamp is top-level on every record (first → started, last → last_activity)
        ts = _parse_iso(record.get("timestamp"))  # type: ignore[arg-type]
        if ts is not None:
            if started_at is None:
                started_at = ts
            last_activity_at = ts

        # session_meta carries cwd + id (under payload in the real rollout)
        if kind in ("session_meta", "thread.started"):
            if project_path is None and isinstance(inner.get("cwd"), str):
                project_path = inner["cwd"]  # type: ignore[assignment]
            if session_id == source_path:
                # Codex live stream uses thread_id; rollout uses id
                sid = inner.get("id") or inner.get("thread_id")
                if isinstance(sid, str):
                    session_id = sid
            continue

        role: object = None
        content: object = None
        if kind == "response_item" and inner.get("type") == "message":
            role = inner.get("role")
            content = inner.get("content")
        elif kind == "message":  # flat fixture / legacy shape
            role = record.get("role")
            content = record.get("content")
        elif kind == "item.completed":  # live stream shape — keep agent_message only
            item = record.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text:
                    messages.append(TranscriptMessage(role="assistant", text=scrub_text(text)))
            continue
        else:
            # event_msg (UI duplicate) + command_execution / file_change / tool_use … dropped
            continue

        if not isinstance(role, str):
            continue
        text = _text_from_codex_content(content)
        if text is None:
            continue
        scrubbed = scrub_text(text)
        messages.append(TranscriptMessage(role=role, text=scrubbed))
        if first_user_title is None and role == "user" and _is_real_user_text(scrubbed):
            first_user_title = _make_title(scrubbed)

    return TranscriptSession(
        session_id=session_id,
        agent_type_value="codex",
        project_path=project_path,
        started_at=started_at,
        messages=tuple(messages),
        source_path=source_path,
        title=first_user_title,
        last_activity_at=last_activity_at,
    )


__all__ = ["parse_claude_code", "parse_codex"]
