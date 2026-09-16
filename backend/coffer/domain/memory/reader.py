"""The port every native-memory reader implements (spec memory FR-004).

Two agents, two undocumented private formats, one shape: list the source
files under an agent's own ``config_dir`` without opening them (``sources``),
then parse one of those files into the entries it holds (``read``). Splitting
the two lets the caller hash a file cheaply to decide whether it changed
(FR-006) before paying to parse it.

A reader's output is a :class:`RawEntry` — **the input layer, not the
product**. It is written verbatim under the partition's ``.raw/`` (FR-008)
and the distil pass turns entries into Coffer's own notes (FR-020). That
split is why a reader may stay dumb: it is not trying to write anything a
person will read, only to hand the pass everything the source said,
including the source's own search terms where it supplies them.

Everything here is a plain value or a ``Protocol`` — no filesystem access, no
YAML, no agent-specific knowledge. The two adapters that actually walk a disk
live in :mod:`coffer.infrastructure.memory.readers`; this module is what they
both promise to satisfy, and what the aggregation pass composes against
instead of a concrete reader class (so a third agent, when one earns the
abstraction per FR-045, is one more adapter, not a change here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SourceFile:
    """One native memory file, cheap to compare across syncs.

    ``digest`` is a content hash, not a size or an mtime, because a native
    tool may rewrite a file with the same bytes at a new mtime (or vice versa
    on a filesystem with coarse mtime resolution) — FR-006's skip-unchanged
    check needs to survive either.
    """

    #: Absolute path of the native file.
    path: str
    #: Content hash, so aggregation can skip a file whose content is unchanged
    #: since the last pass (FR-006) without re-parsing it.
    digest: str


@dataclass(frozen=True)
class RawEntry:
    """One entry as a reader first sees it, before Coffer writes anything.

    Deliberately thinner than :class:`coffer.domain.memory.note.Note`: it
    carries no provenance beyond its anchor and no partition, because those
    are the aggregator's job once it knows which repository the entry belongs
    to. A reader only ever answers "what does this one source file say".
    """

    #: Short human title. From the source's own words when it has one (Claude
    #: Code's frontmatter ``name``); otherwise derived defensibly by the
    #: reader, which documents the choice where it makes it. It is a handle
    #: for the distil pass, not a title a person will read — the note's title
    #: is Coffer's to write (FR-020).
    title: str
    #: Longer human description, same provenance rule as ``title``.
    description: str
    #: One of :data:`coffer.domain.memory.note.NOTE_TYPES`.
    type: str
    #: The source's own words, verbatim. This is the layer where verbatim
    #: still holds (FR-008): it is what lands under ``.raw/`` and what a
    #: note's claim is checked against.
    body: str
    #: Where inside the source file this entry lives — a heading, a bullet's
    #: content hash, or empty when the whole file is the entry. Half of the
    #: stable identity FR-009 needs; the reader is responsible for it being
    #: the same string on a second, unchanged read.
    anchor: str
    #: Absolute working directory this entry was learned in, or "" when it is
    #: about the person rather than any one project. Aggregation resolves it
    #: to a repository (FR-014); an entry whose directory is not inside one
    #: creates no partition and is judged on its merits by distil (FR-015).
    project_root: str
    #: The source's own timestamp for this entry, when it records one at all.
    source_written_at: str = ""
    #: Search terms the source itself states for this material. Codex writes
    #: them per task group in its summary; Claude Code states none. Carried
    #: rather than discarded because the source has already answered "what
    #: would you look this up by" better than a later guess can (FR-004), and
    #: the index line repeats them (FR-029).
    search_terms: tuple[str, ...] = field(default_factory=tuple)


class MemoryReader(Protocol):
    """What one agent's native-memory adapter must provide."""

    #: ``"claude_code"`` or ``"codex"`` — matches the registered agent's type,
    #: so the aggregator knows which reader to hand which ``config_dir``.
    agent_type: str

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        """List this agent's native memory files under ``config_dir``.

        Must not raise for one unreadable file — skip it and keep listing the
        rest (a directory-listing failure is a filesystem problem, not a
        format problem, and FR-005's isolation still applies: one bad path
        must not blank the whole list).
        """
        ...

    def read(self, source: SourceFile) -> tuple[RawEntry, ...]:
        """Parse one source file into the entries it holds.

        Raises :class:`coffer.domain.memory.errors.UnreadableMemory` — never
        returns a partial tuple — when the file cannot be parsed (FR-005):
        the caller is expected to catch it per file, record the reason, and
        carry on with everything else.
        """
        ...


__all__ = ["MemoryReader", "RawEntry", "SourceFile"]
