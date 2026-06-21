"""FileTranscriptReader (TranscriptReaderPort) — discover, parse, cache, search.

The pure per-agent parsers live in :mod:`transcript_parsers`; this module is the
read-only filesystem adapter that finds each agent's ``.jsonl`` session files,
parses them (via an mtime-aware cache), and serves list / search / read queries.
``parse_claude_code`` / ``parse_codex`` are re-exported for callers and tests.
"""

from __future__ import annotations

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
from coffer.domain.distill.session import TranscriptSession
from coffer.infrastructure.distill.transcript_parsers import parse_claude_code, parse_codex

log = logging.getLogger(__name__)

# Sort sentinel for sessions with no timestamp — keeps them last on a desc sort
# (and first on asc), and is tz-aware so it never mixes with naive datetimes.
_DT_MIN = datetime(1, 1, 1, tzinfo=UTC)


class FileTranscriptReader:
    """Read-only adapter that discovers and parses agent transcript files.

    Implements ``TranscriptReaderPort``; wired at the composition root.
    Reads Claude Code ``~/.claude/projects/**/*.jsonl`` and
    Codex ``~/.codex/sessions/**/*.jsonl`` (one ``.jsonl`` per session).
    """

    # Map agent_type_value → parser function (one .jsonl file per session).
    _PARSERS: ClassVar[dict[str, Callable[..., TranscriptSession]]] = {
        "claude_code": parse_claude_code,
        "codex": parse_codex,
    }

    def __init__(self) -> None:
        # path -> (mtime, parsed session). The reader is a composition-root
        # singleton, so this cache lives for the daemon's lifetime: an agent
        # with thousands of sessions re-parses only files whose mtime changed.
        self._cache: dict[str, tuple[float, TranscriptSession]] = {}

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
        sessions: list[TranscriptSession] = []
        for path in self._iter_files(agent_type_value, config_dir):
            try:
                sessions.append(self._parse_file(agent_type_value, path))
            except Exception:
                log.warning("transcript_reader: failed to parse %s; skipping", path, exc_info=True)
        return sessions

    def list_session_summaries(
        self, *, agent_type_value: str, config_dir: str, limit: int, offset: int
    ) -> tuple[int, list[TranscriptSession]]:
        """Return ``(total, page)`` — the total session count and one page of
        sessions, most-recent first.

        Sorts transcript *files* by mtime (a cheap ``stat``) and parses only
        the requested window, so listing stays fast no matter how many thousand
        past sessions sit on disk — unlike :meth:`list_sessions`, which parses
        every file.
        """
        files: list[tuple[float, Path]] = []
        for path in self._iter_files(agent_type_value, config_dir):
            try:
                files.append((path.stat().st_mtime, path))
            except OSError:
                log.warning("transcript_reader: failed to stat %s; skipping", path, exc_info=True)
        files.sort(key=lambda f: f[0], reverse=True)
        page: list[TranscriptSession] = []
        for _, path in files[offset : offset + limit]:
            try:
                page.append(self._parse_file(agent_type_value, path))
            except Exception:
                log.warning("transcript_reader: failed to parse %s; skipping", path, exc_info=True)
        return len(files), page

    def _all_summaries(self, agent_type_value: str, config_dir: str) -> list[TranscriptSession]:
        """Parse every session under the agent's sessions dir, reusing the cache.

        mtime-aware: a file is re-parsed only when its mtime changes. Cache
        entries for files that have since been deleted (under this root) are
        pruned so the cache can't grow without bound.
        """
        root_prefix = str(sessions_dir(agent_type_value, Path(config_dir)))
        out: list[TranscriptSession] = []
        seen: set[str] = set()
        for path in self._iter_files(agent_type_value, config_dir):
            key = str(path)
            seen.add(key)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                log.warning("transcript_reader: failed to stat %s; skipping", path, exc_info=True)
                continue
            cached = self._cache.get(key)
            if cached is not None and cached[0] == mtime:
                out.append(cached[1])
                continue
            try:
                session = self._parse_file(agent_type_value, path)
            except Exception:
                log.warning("transcript_reader: failed to parse %s; skipping", path, exc_info=True)
                continue
            self._cache[key] = (mtime, session)
            out.append(session)
        for stale in [k for k in self._cache if k.startswith(root_prefix) and k not in seen]:
            del self._cache[stale]
        return out

    def search_session_summaries(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        limit: int,
        offset: int,
        query: str | None = None,
        project: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[int, list[TranscriptSession]]:
        """Return ``(matched_total, page)`` after search + filter + sort.

        Parses (cached) every session, then applies a case-insensitive search
        over title + project_path, a project + ``started_at``-range filter, and
        a sort by ``started_at`` / ``last_activity_at`` / ``message_count``
        (asc/desc), paged by ``limit``/``offset``.
        """
        sessions = self._all_summaries(agent_type_value, config_dir)
        q = query.strip().lower() if query else None
        # started_at is always tz-aware (UTC); normalise naive bounds (an
        # offset-less ?started_after=… is valid per the date-time contract) so
        # the comparison never raises "can't compare naive and aware datetimes".
        if started_after is not None and started_after.tzinfo is None:
            started_after = started_after.replace(tzinfo=UTC)
        if started_before is not None and started_before.tzinfo is None:
            started_before = started_before.replace(tzinfo=UTC)

        def keep(s: TranscriptSession) -> bool:
            if project is not None and s.project_path != project:
                return False
            if started_after is not None and (s.started_at is None or s.started_at < started_after):
                return False
            if started_before is not None and (
                s.started_at is None or s.started_at > started_before
            ):
                return False
            if q:
                haystack = " ".join(p for p in (s.title, s.project_path) if p).lower()
                if q not in haystack:
                    return False
            return True

        filtered = [s for s in sessions if keep(s)]
        reverse = order != "asc"
        if sort == "message_count":
            filtered.sort(key=lambda s: s.message_count, reverse=reverse)
        elif sort == "started_at":
            filtered.sort(key=lambda s: s.started_at or _DT_MIN, reverse=reverse)
        else:  # last_activity_at (default)
            filtered.sort(key=lambda s: s.last_activity_at or _DT_MIN, reverse=reverse)
        return len(filtered), filtered[offset : offset + limit]

    def read_session(
        self, *, agent_type_value: str, config_dir: str, session_id: str
    ) -> TranscriptSession:
        """Return the fully parsed TranscriptSession matching ``session_id``.

        Raises KeyError if no matching session is found.
        Raises UnsupportedAgentTypeError for unknown agent types.
        """
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
