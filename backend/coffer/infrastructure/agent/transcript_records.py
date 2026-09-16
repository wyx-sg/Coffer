"""Record-level reading of an agent's ``.jsonl`` transcripts.

The one place that knows what a *line* of a Claude Code or Codex transcript
looks like. Two things are derived from those lines and they must not drift
apart: the browse-list summary (:mod:`transcript_parsers`) and the body one
session's detail page renders (:mod:`transcript_messages`). If each grew its own
idea of which records are conversational turns, a session could list as six
messages and render five, and nothing would say which count was wrong. So the
recognisers live here and both callers ask them the same question.

Everything is a pure function over an iterable of lines. In production that
iterable is an open file handle, so a transcript is streamed rather than held
whole — these files run to tens of megabytes each.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime

log = logging.getLogger(__name__)


def parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string; return None on any failure.

    Always returns a tz-aware datetime (UTC when no offset is present) so that
    comparisons across sessions never raise TypeError on mixed aware/naive
    values.
    """
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def iter_json_records(
    lines: Iterable[str], *, source_path: str, label: str
) -> Iterator[dict[object, object]]:
    """Yield each line of a transcript as a JSON object, skipping what isn't.

    A transcript is written by a live process and read while it is still being
    appended to, so a half-flushed final line is normal rather than
    exceptional: one bad line must never cost the whole file. Blank lines are
    dropped without a ``strip()`` — that copies every line of a file that can
    be tens of megabytes, and ``json.loads`` already tolerates surrounding
    whitespace.
    """
    for raw in lines:
        if not raw or raw.isspace():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            log.debug("%s: skipping non-JSON line in %s", label, source_path)
            continue
        if isinstance(record, dict):
            yield record


def text_from_claude_content(content: object) -> str | None:
    """Extract plain text from a Claude ``content`` value (str or block list).

    Returns None when the content carries no text at all (e.g. it is purely a
    tool_use payload, which is not a conversational turn).
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


def text_from_codex_content(content: object) -> str | None:
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


def claude_turn(record: dict[object, object]) -> tuple[str, str] | None:
    """``(role, text)`` when this Claude Code record is a conversational turn.

    None for everything else — the ``ai-title`` marker, a record whose
    ``message`` is nothing but tool_use / tool_result blocks, anything without
    a role. "Carries natural-language text" is the whole definition of a turn
    here, and it is why a tool-heavy session counts far fewer messages than it
    has lines.
    """
    msg_obj = record.get("message")
    if not isinstance(msg_obj, dict):
        return None
    role = msg_obj.get("role")
    if not isinstance(role, str):
        return None
    text = text_from_claude_content(msg_obj.get("content"))
    if text is None:
        return None
    return role, text


def codex_inner(record: dict[object, object]) -> dict[object, object]:
    """The record's payload envelope, or the record itself when it has none.

    A real persisted rollout nests every event under ``payload``; the live
    ``codex exec --json`` stream does not.

    Measured, because this parses another tool's file format and guessing is
    how a reader silently drops turns: 1,937 rollout files on a developer
    machine, spanning months of use, are ``response_item`` records with a
    ``payload`` — every single one. Not one flat record among them.
    """
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else record


def codex_turn(record: dict[object, object]) -> tuple[str, str] | None:
    """``(role, text)`` when this Codex record is a conversational turn.

    Three shapes count: the rollout's ``response_item`` message, the flat
    ``message`` of older fixtures, and the live stream's ``item.completed``
    agent message (which carries no role of its own, so it is attributed to the
    assistant it came from). The parallel ``event_msg`` user_message /
    agent_message events are the UI's own duplicates of the rollout records and
    are dropped, or every turn would be counted — and rendered — twice.
    """
    kind = record.get("type")
    inner = codex_inner(record)

    if kind == "response_item" and inner.get("type") == "message":
        role: object = inner.get("role")
        content: object = inner.get("content")
    elif kind == "message":
        # Tolerance, not a format anything is known to write. No real rollout
        # on hand uses it (see ``codex_inner``), so this branch is reachable
        # only from a Codex version nobody here has run — kept because Codex
        # owns this file format and the cost of being wrong is asymmetric:
        # three lines of tolerance against a transcript reader that silently
        # loses every turn. Delete it the day Codex's format is versioned.
        role = record.get("role")
        content = record.get("content")
    elif kind == "item.completed":  # live stream shape — keep agent_message only
        item = record.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text:
                return "assistant", text
        return None
    else:
        # event_msg (UI duplicate) + command_execution / file_change / tool_use …
        return None

    if not isinstance(role, str):
        return None
    text = text_from_codex_content(content)
    if text is None:
        return None
    return role, text


__all__ = [
    "claude_turn",
    "codex_inner",
    "codex_turn",
    "iter_json_records",
    "parse_iso",
    "text_from_claude_content",
    "text_from_codex_content",
]
