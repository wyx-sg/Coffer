"""Read OpenCode transcript sessions from its on-disk storage tree (spec 007).

Unlike Claude Code / Codex (one ``.jsonl`` file per session), OpenCode persists
each conversation as a *tree* of single-JSON-object files under an XDG **data**
directory (not the config dir)::

    ~/.local/share/opencode/storage/
      project/<projectID>.json     # { id, worktree, directory, ... }
      session/<projectID>/<sessionID>.json   # { id, title, time:{created} }
      message/<sessionID>/<messageID>.json   # { id, role, time:{created} }
      part/<messageID>/<partID>.json         # { type:"text", text } | tool | ...

A session is reconstructed by joining those files: its project working
directory comes from ``project/<projectID>.json``'s ``directory`` (the parent
folder of the session file is the projectID), and its messages are the
``message`` files ordered by creation time, each message's text being the
concatenation of its ``text`` parts.

Defensive, read-only, and faithful to the distillation invariants: only natural
-language ``text`` parts are kept (tool / reasoning / file / step parts are
dropped), every kept text is scrubbed, and a single malformed file is skipped
rather than failing the whole read.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.domain.distill.scrub import scrub_text
from coffer.domain.distill.session import TranscriptMessage, TranscriptSession

log = logging.getLogger(__name__)

AGENT_TYPE_VALUE = "opencode"


def opencode_storage_dir() -> Path:
    """The OpenCode storage root, honouring ``$XDG_DATA_HOME`` (XDG spec).

    OpenCode stores transcripts under the data dir, independent of its config
    dir, so this is derived from the environment rather than the agent's
    config_dir.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "opencode" / "storage"


def parse_opencode_storage(storage_dir: Path) -> list[TranscriptSession]:
    """Reconstruct every OpenCode session under ``storage_dir``.

    Returns an empty list when the storage tree is absent. Never raises on a
    single malformed file — it is logged and skipped.
    """
    session_root = storage_dir / "session"
    if not session_root.is_dir():
        return []
    project_dirs = _project_directories(storage_dir)
    sessions: list[TranscriptSession] = []
    for sess_file in sorted(session_root.rglob("*.json")):
        data = _load_json(sess_file)
        if not isinstance(data, dict):
            continue
        session_id = str(data.get("id") or sess_file.stem)
        project_id = sess_file.parent.name
        directory = data.get("directory")
        project_path = directory if isinstance(directory, str) else project_dirs.get(project_id)
        sessions.append(
            TranscriptSession(
                session_id=session_id,
                agent_type_value=AGENT_TYPE_VALUE,
                project_path=project_path,
                started_at=_epoch_ms_to_dt(_dig(data, "time", "created")),
                messages=tuple(_session_messages(storage_dir, session_id)),
                source_path=str(sess_file),
            )
        )
    return sessions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _project_directories(storage_dir: Path) -> dict[str, str]:
    """Map projectID → working directory from ``project/*.json``.

    Keyed by both the file stem and any explicit ``id`` so the session file's
    parent-dir name resolves regardless of which OpenCode uses as the key.
    """
    out: dict[str, str] = {}
    project_root = storage_dir / "project"
    if not project_root.is_dir():
        return out
    for proj_file in project_root.glob("*.json"):
        data = _load_json(proj_file)
        if not isinstance(data, dict):
            continue
        directory = data.get("directory") or data.get("worktree")
        if isinstance(directory, str):
            out[proj_file.stem] = directory
            if isinstance(data.get("id"), str):
                out[data["id"]] = directory
    return out


def _session_messages(storage_dir: Path, session_id: str) -> list[TranscriptMessage]:
    message_root = storage_dir / "message" / session_id
    if not message_root.is_dir():
        return []
    ordered: list[tuple[tuple[float, str], str, str]] = []
    for msg_file in message_root.glob("*.json"):
        info = _load_json(msg_file)
        if not isinstance(info, dict):
            continue
        role = info.get("role")
        if not isinstance(role, str):
            continue
        message_id = str(info.get("id") or msg_file.stem)
        text = _message_text(storage_dir, message_id)
        if not text:
            continue
        created = _dig(info, "time", "created")
        sort_key = (float(created) if isinstance(created, (int, float)) else 0.0, message_id)
        ordered.append((sort_key, role, scrub_text(text)))
    ordered.sort(key=lambda e: e[0])
    return [TranscriptMessage(role=role, text=text) for _, role, text in ordered]


def _message_text(storage_dir: Path, message_id: str) -> str:
    """Concatenate a message's natural-language ``text`` parts (ordered by part
    id). Tool / reasoning / file / step parts are intentionally dropped so no
    tool payload ever reaches a distilled message."""
    part_root = storage_dir / "part" / message_id
    if not part_root.is_dir():
        return ""
    parts: list[str] = []
    for part_file in sorted(part_root.glob("*.json")):
        part = _load_json(part_file)
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "".join(parts)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        log.debug("opencode_reader: skipping unreadable/invalid file %s", path)
        return None


def _dig(data: dict[str, Any], *keys: str) -> Any:
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _epoch_ms_to_dt(value: Any) -> datetime | None:
    """Convert an epoch-milliseconds number to a tz-aware UTC datetime."""
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (ValueError, OSError, OverflowError):
        return None
