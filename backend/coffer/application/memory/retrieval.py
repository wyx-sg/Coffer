"""Prompt-time retrieval: the notes one prompt names, ranked lexically (spec
memory "Retrieve the notes a prompt names").

For each substantive prompt the hook sends, the notes of the session's
repository partition and of ``global`` are ranked against the prompt with BM25
(``domain.memory.retrieval``); the top three above the relevance floor that
this session has not already been given are delivered, at most 1.5 KB, each as
the note's absolute path and its substance worded as provenance plus fact
(``domain.memory.hook_output``).

The ranking index is **derived and held in memory**: it is rebuilt from the
note files when a partition's ``notes/`` changes (by name, mtime and size), and
never written anywhere. Nothing chunks or embeds a note.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.memory.context import MemoryPort, resolve_cwd_partition
from coffer.application.memory.session_ledger import SessionLedger
from coffer.domain.memory import retrieval as ranking
from coffer.domain.memory.hook_output import RETRIEVAL_HEADER, note_line
from coffer.domain.memory.note import Note
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.infrastructure.memory import paths as memory_paths

Signature = tuple[tuple[str, int, int], ...]

#: How many combined indexes (one per repository partition, with ``global``)
#: are kept.
_MAX_CACHED = 32


def note_key(note: Note) -> str:
    """How a delivered note is named in the session ledger and the audit log."""
    return f"{note.partition}/{note.slug}"


def note_file(note: Note) -> str:
    return str(memory_paths.notes_dir(note.partition) / f"{note.slug}.md")


def _document(note: Note) -> str:
    return " ".join((note.title, note.description, " ".join(note.search_terms), note.body))


@dataclass(frozen=True)
class Retrieved:
    """What one prompt brought in: the text (empty for nothing) and the notes."""

    text: str
    partition: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class _Cached:
    signature: tuple[Signature, ...]
    index: ranking.Bm25Index
    notes: dict[str, Note]


class RetrievalService:
    """Ranks notes against prompts and remembers what each session was given."""

    def __init__(
        self,
        memory: MemoryPort,
        ledger: SessionLedger,
        *,
        signature: Callable[[str], Signature] = memory_paths.notes_signature,
    ) -> None:
        self._memory = memory
        self._ledger = ledger
        self._signature = signature
        self._cache: dict[str, _Cached] = {}

    async def _index(self, partitions: Sequence[str]) -> _Cached:
        key = ",".join(partitions)
        sig = tuple(self._signature(p) for p in partitions)
        cached = self._cache.get(key)
        if cached is not None and cached.signature == sig:
            return cached
        notes: dict[str, Note] = {}
        for partition in partitions:
            for note in await self._memory.list_notes(partition):
                notes[note_key(note)] = note
        built = _Cached(sig, ranking.Bm25Index((k, _document(n)) for k, n in notes.items()), notes)
        if len(self._cache) >= _MAX_CACHED:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = built
        return built

    async def partitions_for(self, cwd: str) -> tuple[str, list[str]]:
        """The session's own partition and every served partition it reads:
        its repository's (when it has one) and ``global``."""
        served = set(await self._memory.served_partitions())
        project = resolve_cwd_partition(await self._memory.placements(), cwd)
        wanted = [p for p in dict.fromkeys((project, GLOBAL_PARTITION)) if p in served]
        return project, wanted

    async def rank(self, *, cwd: str, prompt: str) -> tuple[str, list[tuple[Note, float]]]:
        """Every note above zero for ``prompt``, best first — the unfiltered
        ranking, for a test or a preview."""
        project, partitions = await self.partitions_for(cwd)
        if not partitions:
            return project, []
        cached = await self._index(partitions)
        return project, [(cached.notes[r.key], r.score) for r in cached.index.rank(prompt)]

    async def retrieve(self, *, cwd: str, prompt: str, session_id: str) -> Retrieved:
        """The delivery for one prompt, and the ledger updated with it."""
        if not ranking.is_substantive(prompt):
            return Retrieved("", "", ())
        project, partitions = await self.partitions_for(cwd)
        if not partitions:
            return Retrieved("", project, ())
        cached = await self._index(partitions)
        await self._ledger.ready()
        exclude = self._ledger.delivered(session_id) if session_id else frozenset()
        picked = ranking.select(cached.index.rank(prompt), exclude=exclude)
        lines: list[str] = []
        keys: list[str] = []
        used = len(RETRIEVAL_HEADER.encode("utf-8"))
        for r in picked:
            note = cached.notes[r.key]
            line = note_line(note, note_file(note))
            cost = len(line.encode("utf-8")) + 1
            if used + cost > ranking.RETRIEVAL_CEILING_BYTES:
                continue
            used += cost
            lines.append(line)
            keys.append(r.key)
        if not lines:
            return Retrieved("", project, ())
        if session_id:
            self._ledger.mark_delivered(session_id, keys)
        return Retrieved("\n".join([RETRIEVAL_HEADER, *lines]), project, tuple(keys))


__all__ = ["RetrievalService", "Retrieved", "note_file", "note_key"]
