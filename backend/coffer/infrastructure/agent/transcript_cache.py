"""Remembers each transcript file's parsed summary across daemon restarts.

The reader's in-memory cache already spares it from re-parsing a file whose
mtime has not moved — but only for as long as the daemon lives. On this
machine a cold pass is 442 files / 560 MB for Claude Code and 1,933 files /
2.0 GB for Codex, seconds of blocking I/O, and every restart paid it again.
That work is a pure function of the bytes on disk, so it is written down.

The shape is the same one ``infrastructure/memory/source_state.py`` uses for
the same job one layer over: a flat, dot-prefixed JSON file replaced
atomically, loaded tolerantly. The entry is keyed by the transcript's absolute
path and stamped with ``(mtime, size)``; a file whose stamp still matches is
served from the sidecar, anything else is re-parsed. Message text is not in
here — only the summary fields the browse list shows, exactly what
``TranscriptSession`` already carries.

Losing this file costs one slow listing and nothing else. Every failure path
below therefore degrades to "parse it again" rather than raising: missing,
corrupt, not a dict, an entry with the wrong shape, an unwritable root.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from coffer.domain.agent.transcripts import TranscriptSession
from coffer.infrastructure.agent import paths

log = logging.getLogger(__name__)

#: ``{absolute transcript path: (mtime, size, summary)}`` — the reader's cache.
CacheEntry = tuple[float, int, TranscriptSession]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt(value: object) -> datetime | None:
    """Parse a stored timestamp back, or ``None`` — never raise."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_entry(key: str, raw: object) -> CacheEntry | None:
    """One stored record back into a cache entry, or ``None`` if unusable."""
    if not isinstance(raw, dict):
        return None
    mtime, size = raw.get("mtime"), raw.get("size")
    if not isinstance(mtime, int | float) or not isinstance(size, int):
        return None
    session_id, agent_type_value = raw.get("session_id"), raw.get("agent_type_value")
    if not isinstance(session_id, str) or not isinstance(agent_type_value, str):
        return None
    project_path, title = raw.get("project_path"), raw.get("title")
    message_count = raw.get("message_count")
    return (
        float(mtime),
        size,
        TranscriptSession(
            session_id=session_id,
            agent_type_value=agent_type_value,
            project_path=project_path if isinstance(project_path, str) else None,
            started_at=_dt(raw.get("started_at")),
            message_count=message_count if isinstance(message_count, int) else 0,
            source_path=key,
            title=title if isinstance(title, str) else None,
            last_activity_at=_dt(raw.get("last_activity_at")),
        ),
    )


def _from_entry(entry: CacheEntry) -> dict[str, Any]:
    mtime, size, session = entry
    return {
        "mtime": mtime,
        "size": size,
        "session_id": session.session_id,
        "agent_type_value": session.agent_type_value,
        "project_path": session.project_path,
        "started_at": _iso(session.started_at),
        "message_count": session.message_count,
        "title": session.title,
        "last_activity_at": _iso(session.last_activity_at),
    }


def load() -> dict[str, CacheEntry]:
    """Every usable entry the last pass wrote down, or ``{}``.

    A missing, corrupt, mid-write or foreign-shaped file yields ``{}``, and a
    single unusable entry is dropped rather than poisoning the rest: the only
    cost either way is re-parsing, and the listing must still be right.
    """
    path = paths.transcript_summaries_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.debug("transcript_cache: unreadable sidecar at %s; starting cold", path)
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, CacheEntry] = {}
    for key, raw in data.items():
        entry = _to_entry(str(key), raw)
        if entry is not None:
            out[str(key)] = entry
    return out


def save(entries: dict[str, CacheEntry]) -> None:
    """Replace the sidecar with *entries*, atomically and best-effort.

    ``tmp.replace(path)`` is what keeps a reader in another process from ever
    seeing half a file. A failure here is logged and swallowed — a listing that
    already has its answer must not fail because a cache could not be written.
    """
    path = paths.transcript_summaries_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        payload = {key: _from_entry(entry) for key, entry in entries.items()}
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.warning("transcript_cache: failed to write sidecar at %s", path, exc_info=True)


def save_if_needed(entries: dict[str, CacheEntry], *, changed: bool) -> None:
    """Write the sidecar when this pass derived something, or when it is gone.

    Two questions hide behind one word here, and they only came apart once the
    in-memory cache started outliving the file. ``changed`` answers "did this
    pass derive anything new?", which is the reader's own business and stays
    honest. "Is the sidecar worth writing?" is this module's, because this
    module owns the file — and the answer is yes whenever the file is not
    there, whatever the cache did. Without that second half a deleted sidecar
    stayed deleted for as long as no transcript happened to change, which is
    the one case the warm pass exists to cover.

    Best-effort like :func:`save`: an unwritable root is logged, never raised.
    """
    if changed or not paths.transcript_summaries_path().is_file():
        save(entries)


__all__ = ["CacheEntry", "load", "save", "save_if_needed"]
