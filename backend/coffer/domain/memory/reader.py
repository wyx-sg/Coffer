"""The port every native-memory reader implements (spec memory "Read Claude
Code and Codex memory").

Two agents, two private formats, one shape: list the source files under an
agent's own ``config_dir`` without parsing them (``sources``), then parse one
of those files into the memories it holds (``read``). Splitting the two lets
the caller hash a file to decide whether it changed ("Skip unchanged
sources") before paying to parse it.

Everything here is a plain value or a ``Protocol``. The two adapters that walk
a disk live in :mod:`coffer.infrastructure.memory.readers`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SourceFile:
    """One native memory file, cheap to compare across syncs.

    ``digest`` is a content hash, not a size or an mtime: a native tool may
    rewrite a file with the same bytes at a new mtime, or the reverse on a
    filesystem with coarse mtime resolution.
    """

    #: Absolute path of the native file.
    path: str
    #: Content hash.
    digest: str


@dataclass(frozen=True)
class RawEntry:
    """One memory as a reader sees it, before publishing files it under a
    project and makes its paths portable."""

    #: Short title: the source's own (Claude Code's frontmatter ``name``), or
    #: one the reader derives from the text.
    title: str
    #: One-line description, with the same provenance as ``title``.
    description: str
    #: One of :data:`coffer.domain.memory.hub.HUB_TYPES`.
    type: str
    #: The source's own words.
    body: str
    #: Where inside the source file this memory lives; the same string on a
    #: second, unchanged read. Half of the memory's identity.
    anchor: str
    #: Absolute working directory this memory was learned in, or "" when the
    #: source records none. Publishing resolves it to a repository; a memory
    #: whose directory is inside none is not published.
    project_root: str


class MemoryReader(Protocol):
    """What one agent's native-memory adapter must provide."""

    #: ``"claude_code"`` or ``"codex"``: the registered agent's type.
    agent_type: str

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        """List this agent's native memory files under ``config_dir``.

        Must not raise for one unreadable file: skip it and keep listing.
        """
        ...

    def read(self, source: SourceFile) -> tuple[RawEntry, ...]:
        """Parse one source file into the memories it holds.

        Raises :class:`coffer.domain.memory.errors.UnreadableMemory`, never
        returns a partial tuple, when the file cannot be parsed: the caller
        catches it per file, records the reason and carries on.
        """
        ...


__all__ = ["MemoryReader", "RawEntry", "SourceFile"]
