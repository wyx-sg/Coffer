"""FileTranscriptReader — discover, parse, cache, and search agent transcripts.

The pure per-agent parsers live in :mod:`transcript_parsers` (summaries) and
:mod:`transcript_messages` (bodies); this module is the read-only filesystem
adapter that finds each agent's ``.jsonl`` session files, parses them (via a
stamp-aware cache that survives a daemon restart), and serves both the
search/sort/page query behind the Conversations list and the single-session read
behind one conversation's page. ``parse_claude_code`` / ``parse_codex`` are
re-exported for callers and tests.

The cache has two halves and one rule. In memory it is a dict on this object,
which the composition root keeps for the daemon's lifetime. On disk it is a
disposable sidecar (:mod:`transcript_cache`) so a restart does not pay the cold
pass again — 442 files / 560 MB for Claude Code and 1,933 / 2.0 GB for Codex on
the machine this was measured on. The rule is that neither half may change an
answer: an entry is used only while its file's ``(mtime, size)`` still match, and
a missing, empty or corrupt sidecar makes the listing slower and nothing else.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from coffer.domain.agent.transcripts import (
    TranscriptMessage,
    TranscriptSession,
    TranscriptSessionBody,
    UnsupportedAgentTypeError,
    is_session_of,
    is_transcript_file,
    sessions_dir,
    supports_transcripts,
)
from coffer.infrastructure.agent import transcript_cache
from coffer.infrastructure.agent.transcript_messages import (
    iter_claude_code_messages,
    iter_codex_messages,
)
from coffer.infrastructure.agent.transcript_parsers import parse_claude_code, parse_codex

log = logging.getLogger(__name__)

# Sort sentinel for sessions with no timestamp — keeps them last on a desc sort
# (and first on asc), and is tz-aware so it never mixes with naive datetimes.
_DT_MIN = datetime(1, 1, 1, tzinfo=UTC)


class FileTranscriptReader:
    """Read-only adapter that discovers and parses agent transcript files.

    Implements ``TranscriptReaderPort``; wired at the composition root.
    Reads Claude Code ``~/.claude/projects/**/*.jsonl`` and
    Codex ``~/.codex/sessions/**/*.jsonl`` (one ``.jsonl`` per session).
    Nothing here writes an agent's files: the agent owns those. The one thing
    it does write is its own summary sidecar, which is not one of them.
    """

    # Map agent_type_value → parser function (one .jsonl file per session).
    _PARSERS: ClassVar[dict[str, Callable[..., TranscriptSession]]] = {
        "claude_code": parse_claude_code,
        "codex": parse_codex,
    }

    # The same files read the other way round — turns kept rather than counted.
    # Keyed identically on purpose: an agent type the list can summarise is an
    # agent type one of whose sessions can be opened.
    _MESSAGE_ITERATORS: ClassVar[dict[str, Callable[..., Iterator[TranscriptMessage]]]] = {
        "claude_code": iter_claude_code_messages,
        "codex": iter_codex_messages,
    }

    def __init__(self) -> None:
        # path -> (mtime, size, parsed session). The reader is a composition-root
        # singleton, so this cache lives for the daemon's lifetime: an agent with
        # thousands of sessions re-parses only files whose stamp changed. It is
        # seeded from the sidecar on first use so a restart inherits the work.
        self._cache: dict[str, transcript_cache.CacheEntry] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Seed the in-memory cache from the sidecar, once per reader."""
        if self._loaded:
            return
        # Set first: a sidecar that cannot be read is a cold start, not a retry
        # on every listing.
        self._loaded = True
        self._cache.update(transcript_cache.load())

    def _iter_files(self, agent_type_value: str, config_dir: str) -> Iterable[Path]:
        """Yield transcript file paths under the agent's sessions directory."""
        root = sessions_dir(agent_type_value, Path(config_dir))
        if not root.exists():
            return
        for path in root.rglob("*.jsonl"):
            if is_transcript_file(path):
                yield path

    def _parse_file(self, agent_type_value: str, path: Path) -> TranscriptSession:
        """Parse one transcript, streaming it a line at a time.

        The handle is handed straight to the parser rather than
        ``read_text().splitlines()``: these files run to tens of megabytes each,
        and reading one whole meant holding the file twice over — once as a
        single string, once as a list of every line — before a single record was
        looked at.
        """
        parser = self._PARSERS.get(agent_type_value)
        if parser is None:
            raise UnsupportedAgentTypeError(agent_type_value)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return parser(handle, source_path=str(path))

    def _summary_for(
        self, agent_type_value: str, path: Path, stamp: tuple[float, int]
    ) -> tuple[TranscriptSession, bool]:
        """The summary for one file, and whether this call had to derive it.

        The single rule the whole cache rests on, in one place so the listing
        and the single-session read cannot disagree about when an entry is
        still good: a cached summary is used only while the file's
        ``(mtime, size)`` is unchanged. The ``derived`` flag is what lets the
        caller decide whether the sidecar is worth rewriting — a pass that
        parsed nothing new must not cost a write.
        """
        key = str(path)
        cached = self._cache.get(key)
        if cached is not None and (cached[0], cached[1]) == stamp:
            return cached[2], False
        session = self._parse_file(agent_type_value, path)
        self._cache[key] = (stamp[0], stamp[1], session)
        return session, True

    def _all_summaries(self, agent_type_value: str, config_dir: str) -> list[TranscriptSession]:
        """Parse every session under the agent's sessions dir, reusing the cache.

        Stamp-aware: a file is re-parsed only when its ``(mtime, size)`` changes.
        Size is in the stamp because mtime alone has a filesystem's timestamp
        granularity underneath it, and an append within that granularity is
        exactly what a live transcript does. Cache entries for files that have
        since been deleted (under this root) are pruned so the cache — and the
        sidecar it is written back to — cannot grow without bound.

        The sidecar is rewritten only when this pass actually changed something.
        A listing that parsed nothing new is the common case (every visit after
        the first), and it must not cost a write.
        """
        self._ensure_loaded()
        root_prefix = str(sessions_dir(agent_type_value, Path(config_dir)))
        out: list[TranscriptSession] = []
        seen: set[str] = set()
        changed = False
        for path in self._iter_files(agent_type_value, config_dir):
            key = str(path)
            seen.add(key)
            try:
                stat = path.stat()
            except OSError:
                log.warning("transcript_reader: failed to stat %s; skipping", path, exc_info=True)
                continue
            try:
                session, derived = self._summary_for(
                    agent_type_value, path, (stat.st_mtime, stat.st_size)
                )
            except Exception:
                log.warning("transcript_reader: failed to parse %s; skipping", path, exc_info=True)
                continue
            changed = changed or derived
            out.append(session)
        for stale in [k for k in self._cache if k.startswith(root_prefix) and k not in seen]:
            del self._cache[stale]
            changed = True
        if changed:
            transcript_cache.save(self._cache)
        return out

    def warm(self, *, agent_type_value: str, config_dir: str) -> int:
        """Parse everything under this agent's sessions dir; return the count.

        What the boot-time warm pass calls. Deliberately not routed through
        ``AgentTranscriptService``: this is the same disk read the listing does,
        with none of the management semantics around it — no agent lookup, and
        so no audit event, which FR-048 forbids for a workspace listing.
        """
        return len(self._all_summaries(agent_type_value, config_dir))

    def read_session(
        self,
        *,
        agent_type_value: str,
        config_dir: str,
        source_path: str,
        limit: int,
        offset: int,
    ) -> TranscriptSessionBody:
        """One session's summary plus a window of ``limit`` turns from ``offset``.

        ``source_path`` is a path the listing handed out, and that is the only
        authority it carries: it is resolved and must land inside this agent's
        own sessions directory (:func:`is_session_of`), so neither a crafted
        query nor a symlink pointing elsewhere turns this into a general file
        read. A path that passes containment but names nothing raises
        ``FileNotFoundError`` — the transcript was deleted between the listing
        and the click, which is ordinary rather than suspicious.

        The window is taken from a generator, so a reader looking at the start
        of a 60 MB transcript stops the file read at the end of the page rather
        than parsing the rest to throw it away. The summary beside it comes
        from the same stamp-aware cache the listing uses, so opening a session
        costs nothing the listing had not already paid.

        Raises:
            UnsupportedAgentTypeError: the agent type has no transcript layout.
            ValueError: the path is not one of this agent's transcripts.
            FileNotFoundError: no such transcript file.
        """
        # An agent type with no layout is a different answer from a path that
        # misses, so it is asked first and separately — otherwise containment
        # (which treats "no layout" as "contains nothing") would flatten the two
        # into one indistinguishable rejection.
        if not supports_transcripts(agent_type_value):
            raise UnsupportedAgentTypeError(agent_type_value)
        resolved_config = Path(config_dir).resolve()
        candidate = Path(source_path).resolve(strict=False)
        if not is_session_of(agent_type_value, resolved_config, candidate):
            raise ValueError(f"not a transcript of this agent: {source_path!r}")
        if not candidate.is_file():
            raise FileNotFoundError(source_path)

        self._ensure_loaded()
        stat = candidate.stat()
        session, derived = self._summary_for(
            agent_type_value, candidate, (stat.st_mtime, stat.st_size)
        )
        if derived:
            transcript_cache.save(self._cache)
        messages = self._read_messages(agent_type_value, candidate, limit=limit, offset=offset)
        return TranscriptSessionBody(session=session, messages=messages, offset=offset, limit=limit)

    def _read_messages(
        self, agent_type_value: str, path: Path, *, limit: int, offset: int
    ) -> list[TranscriptMessage]:
        """Stream *path* and keep the ``limit`` turns starting at ``offset``."""
        iterator = self._MESSAGE_ITERATORS.get(agent_type_value)
        if iterator is None:
            raise UnsupportedAgentTypeError(agent_type_value)
        out: list[TranscriptMessage] = []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for index, message in enumerate(iterator(handle, source_path=str(path))):
                if index < offset:
                    continue
                out.append(message)
                if len(out) >= limit:
                    break
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
        sort: str = "last_activity_at",
        order: str = "desc",
    ) -> tuple[int, list[TranscriptSession]]:
        """Return ``(matched_total, page)`` after search + filter + sort.

        Parses (cached) every session, then applies a case-insensitive search
        over title + project_path, an exact ``project`` filter, and a sort by
        ``started_at`` / ``last_activity_at`` / ``message_count`` (asc/desc),
        paged by ``limit``/``offset``.
        """
        sessions = self._all_summaries(agent_type_value, config_dir)
        q = query.strip().lower() if query else None

        def keep(s: TranscriptSession) -> bool:
            if project is not None and s.project_path != project:
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


__all__ = [
    "FileTranscriptReader",
    "parse_claude_code",
    "parse_codex",
]
