"""Defensive per-agent transcript parsers (pure functions).

What the browse list is made of: one ``.jsonl`` file in, one
:class:`TranscriptSession` summary out. The record shapes themselves are not
known here — :mod:`transcript_records` owns those, so that this module and
:mod:`transcript_messages` agree on what a turn is — and what IS here is
everything that only a *summary* needs: which user turn is worth a title, how
to cut one down to a line, and which metadata records carry the session's cwd,
id and timestamps.

Design principles:
- Take any iterable of lines — in production an open file handle, so a
  transcript is streamed rather than held whole.
- Never raise on a single bad line; skip and continue.
- Count only natural-language *text* turns; tool_use / tool_result /
  function-call records carry no text and are not turns.
- Keep no message text — a session is projected to the browse-list fields.
- Derive ``title`` (Claude Code ai-title / first real user message, scrubbed),
  ``project_path`` (``cwd``), ``session_id``, and ``started_at`` /
  ``last_activity_at`` (first / last ``timestamp``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from coffer.domain.agent.transcripts import TranscriptSession, scrub_secrets
from coffer.infrastructure.agent.transcript_records import (
    claude_turn,
    codex_inner,
    codex_turn,
    iter_json_records,
    parse_iso,
)

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

# The prefixes above name the injected blocks seen most often, but naming them
# one at a time never finishes: ``<turn_aborted>`` and ``<recommended_plugins>``
# both reached the UI as session titles. What they have in common is the shape,
# so match that instead — a "user turn" that is nothing but an XML/HTML-ish tag
# block was written by the harness, not by a person.
#
# Narrow on purpose, in the same spirit as ``_SECRET_PATTERNS``: a tag is
# ``<name>``, ``</name>``, ``<name attr="…">`` or ``<name/>`` with an
# identifier-shaped name and no nested angle bracket. Prose that merely contains
# a ``<`` — a comparison, an arrow, a shell redirect — matches nothing here and
# survives.
_TAG = re.compile(r"<\s*/?[A-Za-z_][\w.:-]*(?:\s[^<>]*)?/?>")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _first_line(text: str) -> str:
    """First non-empty line of *text*, stripped — what a title is made from."""
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _is_only_tags(text: str) -> bool:
    """True when *text* has nothing left once tag-shaped spans are removed."""
    return bool(text) and not _TAG.sub("", text).strip()


def _is_real_user_text(text: str) -> bool:
    """True when *text* reads like a genuine human prompt suitable as a title.

    Filters out the non-conversational preambles (environment/instructions
    blocks, shell-command echoes, slash commands) that lead most sessions, and
    any turn that is only markup — either whole, or in the one line that would
    have become the title.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("/"):  # bare slash command, e.g. "/clear"
        return False
    if stripped.lower().startswith(_TITLE_NOISE_PREFIXES):
        return False
    return not (_is_only_tags(stripped) or _is_only_tags(_first_line(stripped)))


def _make_title(text: str) -> str:
    """First non-empty line of *text*, scrubbed, collapsed, and truncated."""
    collapsed = " ".join(scrub_secrets(_first_line(text)).split())
    if len(collapsed) > _TITLE_MAX_CHARS:
        return collapsed[: _TITLE_MAX_CHARS - 1].rstrip() + "…"
    return collapsed


def _title_from_user_text(current: str | None, role: str, text: str) -> str | None:
    """Keep the first real user message as the fallback title."""
    if current is not None or role != "user" or not _is_real_user_text(text):
        return current
    return _make_title(text)


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


def parse_claude_code(lines: Iterable[str], *, source_path: str) -> TranscriptSession:
    """Parse a Claude Code persisted transcript (one JSON object per line).

    Tolerates non-JSON lines (skipped). Counts only text turns; records that
    carry nothing but tool_use / tool_result are not turns.
    """
    message_count = 0
    project_path: str | None = None
    session_id: str = source_path  # fallback: use path if record carries none
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    ai_title: str | None = None
    first_user_title: str | None = None

    for record in iter_json_records(lines, source_path=source_path, label="claude_code parser"):
        # Extract metadata from any record that carries it (first wins).
        if project_path is None and isinstance(record.get("cwd"), str):
            project_path = record["cwd"]  # type: ignore[assignment]
        if session_id == source_path and isinstance(record.get("sessionId"), str):
            session_id = record["sessionId"]  # type: ignore[assignment]
        ts = parse_iso(record.get("timestamp"))  # type: ignore[arg-type]
        if ts is not None:
            if started_at is None:
                started_at = ts
            last_activity_at = ts  # last timestamped event wins

        # Claude Code persists its own session title, updated over time — latest wins.
        if record.get("type") == "ai-title":
            at = record.get("aiTitle")
            if isinstance(at, str) and at.strip():
                ai_title = _make_title(at)
            continue

        turn = claude_turn(record)
        if turn is None:
            continue
        role, text = turn
        message_count += 1
        first_user_title = _title_from_user_text(first_user_title, role, text)

    return TranscriptSession(
        session_id=session_id,
        agent_type_value="claude_code",
        project_path=project_path,
        started_at=started_at,
        message_count=message_count,
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
    message_count = 0
    project_path: str | None = None
    session_id: str = source_path  # fallback
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    first_user_title: str | None = None

    for record in iter_json_records(lines, source_path=source_path, label="codex parser"):
        kind = record.get("type")
        inner = codex_inner(record)

        # timestamp is top-level on every record (first → started, last → last_activity)
        ts = parse_iso(record.get("timestamp"))  # type: ignore[arg-type]
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

        turn = codex_turn(record)
        if turn is None:
            continue
        role, text = turn
        message_count += 1
        first_user_title = _title_from_user_text(first_user_title, role, text)

    return TranscriptSession(
        session_id=session_id,
        agent_type_value="codex",
        project_path=project_path,
        started_at=started_at,
        message_count=message_count,
        source_path=source_path,
        title=first_user_title,
        last_activity_at=last_activity_at,
    )


__all__ = ["parse_claude_code", "parse_codex"]
