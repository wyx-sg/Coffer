"""``coffer__recall`` — a locator, not a reader (spec memory FR-035, FR-034).

Delivery hands a session the **whole index** of the partition it was opened
in, plus ``global``'s (``context.py``), so for that partition there is
nothing left to search: the lines are already in front of the caller and the
bodies are files. What is left over is one narrow question — *where is the
note about X, in a partition this session was not opened in* — and this
answers exactly that: a path, a title and a description per match.

**Not the body.** A note is an ordinary Markdown file (FR-022) and every
caller is a local process that can read one, so returning bodies here would
spend a tool result on what a file read does better, and would quietly
recreate the thing this layer just removed: a tool standing between an agent
and a file. The previous version returned whole bodies, and was called five
times in its lifetime.

**No score, no mode, no connection — and no caller identity either.**
Matching is a case-insensitive literal scan over every enabled partition's
notes (FR-013), the same corpus for whoever asks. There is no ranking to
explain and no embedder to be missing; an installation with no internal
connection gets the same recall as any other (FR-024). The scan used to be
narrowed to the asking agent's per-agent scope, and that scope was never
chosen by anybody: it defaulted to the agents a partition had been aggregated
from, so on a real vault Codex could not recall a single note about the
repository it was working in. Notes are shared or they are pointless, so the
narrowing is gone.

**And never a retired note.** That is FR-025, and it is a bug being fixed
rather than a property being restated: the previous version filtered nothing
at all, so on the maintainer's live vault 11 facts that had been marked
superseded — and were correctly withheld from delivery — were still
answerable here as if current. The mechanism now is structural rather than a
check: a retirement takes the note's file out of ``notes/`` and records it in
``RETIRED.md``, and this reads only what ``list_notes`` returns, which is
``notes/``. ``.raw/`` is excluded by the same fact (FR-008): it is aggregation's
verbatim input, not a note, and nothing here can reach it.

The scan stays memory's own rather than borrowing knowledge's ripgrep: at the
corpus size this layer assumes the notes are in hand already, shelling out
buys nothing, and the memory kind has no standing import of the knowledge
kind's search substrate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.memory.note import Note
from coffer.infrastructure.memory import paths as memory_paths

#: Locations returned per call. Higher than a reader's page would be, because
#: a location is three short fields rather than a body — the caller narrows by
#: reading the one it wants, not by asking again.
DEFAULT_TOP_K = 10


class MemoryPort(Protocol):
    """The slice of ``MemoryService`` recall needs: which partitions are
    served and what is in them, never aggregation. Matches
    ``MemoryService``'s real signatures structurally, so a unit test can fake
    it with no database at all.

    ``list_notes`` answers from the partition's ``notes/`` directory only.
    That is what keeps a retired note and a raw entry out of this answer
    (FR-025, FR-008), so it is a promise the port makes, not a filter this
    module applies afterwards.
    """

    async def enabled_partitions(self) -> Sequence[str]: ...

    async def list_notes(self, partition: str) -> Sequence[Note]: ...


@dataclass(frozen=True)
class RecalledNote:
    """One located note: where it is, and enough to decide whether to open it.

    The **absolute** path (FR-035), because the caller's next move is an
    ordinary file read and a vault-relative path would make it guess a root.
    """

    path: str
    title: str
    description: str
    type: str
    partition: str


@dataclass(frozen=True)
class RecallOutcome:
    notes: tuple[RecalledNote, ...]


def _abspath(note: Note) -> str:
    """The note file's absolute path — recall's whole answer to "where"."""
    return str(memory_paths.note_path(note.partition, note.slug))


class RecallService:
    def __init__(self, *, memory: MemoryPort) -> None:
        self._memory = memory

    async def recall(self, query: str, *, top_k: int = DEFAULT_TOP_K) -> RecallOutcome:
        """Locate the notes matching ``query``, across every enabled partition."""
        by_path: dict[str, Note] = {}
        for partition in await self._memory.enabled_partitions():
            for note in await self._memory.list_notes(partition):
                by_path[_abspath(note)] = note

        if not by_path or not query.strip():
            return RecallOutcome(notes=())
        return self._literal(query.strip(), by_path, top_k)

    def _literal(self, query: str, by_path: Mapping[str, Note], top_k: int) -> RecallOutcome:
        """A substring scan over the notes already in hand (FR-035).

        A note matches on its body, on its title or description, or on the
        search terms its source supplied (FR-004) — which are the words the
        source itself expected this lookup to be made with, so ignoring them
        here would waste the one hint the corpus carries about its own
        vocabulary. Results are sorted by path so the same query answers the
        same way twice; there is no score to sort by and none is invented.
        """
        needle = query.lower()
        matched: list[str] = []
        for path, note in by_path.items():
            haystack = "\n".join(
                (note.body, note.title, note.description, " ".join(note.search_terms))
            ).lower()
            if needle in haystack:
                matched.append(path)
        matched.sort()
        return RecallOutcome(
            notes=tuple(self._recalled(by_path[path], path) for path in matched[:top_k])
        )

    @staticmethod
    def _recalled(note: Note, path: str) -> RecalledNote:
        return RecalledNote(
            path=path,
            title=note.title,
            description=note.description,
            type=note.type,
            partition=note.partition,
        )


__all__ = [
    "DEFAULT_TOP_K",
    "MemoryPort",
    "RecallOutcome",
    "RecallService",
    "RecalledNote",
]
