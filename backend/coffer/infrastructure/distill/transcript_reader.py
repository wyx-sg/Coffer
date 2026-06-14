"""Defensive transcript parsers + FileTranscriptReader (TranscriptReaderPort).

Parser design principles:
- Never raise on a single bad line; skip and continue.
- Keep only natural-language *text* blocks; drop tool_use / tool_result /
  function-call blocks entirely.
- Apply scrub_text to every message text before storing.
- Extract project_path from ``cwd``, session_id from ``sessionId`` (Claude) /
  ``id`` (Codex), started_at from first ``timestamp`` (ISO-8601 → datetime).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from coffer.domain.distill.locations import (
    UnsupportedAgentTypeError,
    is_transcript_file,
    sessions_dir,
)
from coffer.domain.distill.scrub import scrub_text
from coffer.domain.distill.session import TranscriptMessage, TranscriptSession
from coffer.infrastructure.distill.opencode_reader import (
    opencode_storage_dir,
    parse_opencode_storage,
)

log = logging.getLogger(__name__)

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
        if started_at is None:
            started_at = _parse_iso(record.get("timestamp"))  # type: ignore[arg-type]

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
            messages.append(TranscriptMessage(role=role, text=scrub_text(text)))

    return TranscriptSession(
        session_id=session_id,
        agent_type_value="claude_code",
        project_path=project_path,
        started_at=started_at,
        messages=tuple(messages),
        source_path=source_path,
    )


def parse_codex(lines: Iterable[str], *, source_path: str) -> TranscriptSession:
    """Parse a Codex rollout-*.jsonl transcript (flat JSONL events).

    Tolerates non-JSON lines (skipped). Keeps ``message`` events with text
    content; drops command_execution / file_change / function-call events.

    The persisted rollout format is similar to but not identical with the live
    ``codex exec --json`` stream.  We therefore parse defensively: any line
    whose ``type`` we don't recognise is silently skipped.
    """
    messages: list[TranscriptMessage] = []
    project_path: str | None = None
    session_id: str = source_path  # fallback
    started_at: datetime | None = None

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

        # session_meta carries cwd + id
        if kind in ("session_meta", "thread.started"):
            if project_path is None and isinstance(record.get("cwd"), str):
                project_path = record["cwd"]  # type: ignore[assignment]
            if session_id == source_path:
                # Codex live stream uses thread_id; rollout may use id
                sid = record.get("id") or record.get("thread_id")
                if isinstance(sid, str):
                    session_id = sid
            continue

        # timestamp on any record (first wins)
        if started_at is None:
            started_at = _parse_iso(record.get("timestamp"))  # type: ignore[arg-type]

        # message events carry role + content text
        if kind == "message":
            role = record.get("role")
            content = record.get("content")
            if isinstance(role, str):
                if isinstance(content, str) and content:
                    messages.append(TranscriptMessage(role=role, text=scrub_text(content)))
                elif isinstance(content, list):
                    # Real Codex rollout stores content as typed blocks, e.g.
                    # {"type":"input_text","text":...} / {"type":"output_text","text":...}
                    parts: list[str] = []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type", "")
                        if isinstance(btype, str) and (btype == "text" or btype.endswith("_text")):
                            text = block.get("text")
                            if text:
                                parts.append(str(text))
                    joined = "".join(parts)
                    if joined:
                        messages.append(TranscriptMessage(role=role, text=scrub_text(joined)))
            continue

        # item.completed events (live stream shape) — keep agent_message only
        if kind == "item.completed":
            item = record.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = item.get("text")
                if isinstance(text, str) and text:
                    messages.append(TranscriptMessage(role="assistant", text=scrub_text(text)))
            continue

        # All other event types (command_execution, file_change, tool_use, …) are dropped.

    return TranscriptSession(
        session_id=session_id,
        agent_type_value="codex",
        project_path=project_path,
        started_at=started_at,
        messages=tuple(messages),
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# FileTranscriptReader (implements TranscriptReaderPort)
# ---------------------------------------------------------------------------


class FileTranscriptReader:
    """Read-only adapter that discovers and parses agent transcript files.

    Implements ``TranscriptReaderPort``; wired at the composition root.
    Reads Claude Code ``~/.claude/projects/**/*.jsonl`` and
    Codex ``~/.codex/sessions/**/*.jsonl`` (one ``.jsonl`` per session), plus
    OpenCode's multi-file JSON storage tree via a per-agent *tree source*.
    """

    # Map agent_type_value → parser function (one .jsonl file per session).
    _PARSERS: ClassVar[dict[str, Callable[..., TranscriptSession]]] = {
        "claude_code": parse_claude_code,
        "codex": parse_codex,
    }

    # Agents whose transcripts are NOT one-.jsonl-per-session but a storage tree
    # joined across files. Each source ignores config_dir and reads its own
    # (XDG-derived) location, returning fully-built sessions.
    _TREE_SOURCES: ClassVar[dict[str, Callable[[], list[TranscriptSession]]]] = {
        "opencode": lambda: parse_opencode_storage(opencode_storage_dir()),
    }

    def _tree_sessions(self, agent_type_value: str) -> list[TranscriptSession]:
        source = self._TREE_SOURCES[agent_type_value]
        try:
            return source()
        except Exception:
            log.warning(
                "transcript_reader: failed to read %s storage tree; skipping",
                agent_type_value,
                exc_info=True,
            )
            return []

    def _iter_files(self, agent_type_value: str, config_dir: str) -> Iterable[Path]:
        """Yield transcript file paths under the agent's sessions directory."""
        root = sessions_dir(agent_type_value, Path(config_dir))
        if not root.exists():
            return
        for path in root.rglob("*.jsonl"):
            if is_transcript_file(path):
                yield path

    def _parse_file(self, agent_type_value: str, path: Path) -> TranscriptSession:
        parser = self._PARSERS.get(agent_type_value)
        if parser is None:
            raise UnsupportedAgentTypeError(agent_type_value)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return parser(lines, source_path=str(path))

    def list_sessions(self, *, agent_type_value: str, config_dir: str) -> list[TranscriptSession]:
        """Return one TranscriptSession per transcript file discovered.

        If the sessions directory does not exist, returns an empty list.
        Errors on individual files are logged and skipped.
        """
        if agent_type_value in self._TREE_SOURCES:
            return self._tree_sessions(agent_type_value)
        sessions: list[TranscriptSession] = []
        for path in self._iter_files(agent_type_value, config_dir):
            try:
                sessions.append(self._parse_file(agent_type_value, path))
            except Exception:
                log.warning("transcript_reader: failed to parse %s; skipping", path, exc_info=True)
        return sessions

    def read_session(
        self, *, agent_type_value: str, config_dir: str, session_id: str
    ) -> TranscriptSession:
        """Return the fully parsed TranscriptSession matching ``session_id``.

        Raises KeyError if no matching session is found.
        Raises UnsupportedAgentTypeError for unknown agent types.
        """
        if agent_type_value in self._TREE_SOURCES:
            for session in self._tree_sessions(agent_type_value):
                if session.session_id == session_id:
                    return session
            raise KeyError(f"No transcript session with id={session_id!r} for {agent_type_value!r}")
        for path in self._iter_files(agent_type_value, config_dir):
            try:
                session = self._parse_file(agent_type_value, path)
            except Exception:
                log.warning("transcript_reader: failed to parse %s; skipping", path, exc_info=True)
                continue
            if session.session_id == session_id:
                return session
        raise KeyError(f"No transcript session with id={session_id!r} found in {config_dir!r}")


__all__ = [
    "FileTranscriptReader",
    "parse_claude_code",
    "parse_codex",
]
