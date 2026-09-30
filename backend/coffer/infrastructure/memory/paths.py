"""On-disk layout for the memory layer — the sole owner of path construction.

Mirrors ``infrastructure/knowledge/paths.py`` on purpose: one root, one guard.
Everything under this root is derived and rebuildable (spec memory "Keep the
memory tree derived and local"), and a partition holds four things with one
writer each:

``MEMORY.md``
    The index (see "Write each index line to stand on its own"). What a session
    is given, and what a human opens first. Written by the distil pass.

``notes/``
    Coffer's own notes, one topic per file (see "Write notes in Coffer's own
    words", "Keep one topic per note"). Written by the distil pass.

``RETIRED.md``
    What was retired and why (see "Record retirements so they stick") — also the
    next pass's exclusion list, without which a deletion is undone by the next
    aggregation. Written by the distil pass.

``.raw/``
    What was read out of the agents, verbatim (see "Keep raw entries verbatim
    and hidden"). Written **only** by aggregation, and never by distil (see
    "Keep distil out of the raw directory"): that is what lets a bad
    distillation be re-run without going back to the agents. Hidden, and
    excluded from the index and from delivery.

The root is ``~/.coffer/derived/memory`` (ADR storage-is-five-classes-by-nature:
the tree is rebuilt from the agents, so deleting it is safe). There is no
override: it is resolved from ``HOME`` at every call, which is how a test's
throwaway home keeps it off a developer's real tree.
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.error_base import CofferError
from coffer.infrastructure.vault.home import derived_root, vault_root

#: The partition's index — the file delivery renders from and a human opens.
INDEX_NAME = "MEMORY.md"
#: The partition's retirement record.
RETIRED_NAME = "RETIRED.md"
#: Where Coffer's own notes live.
NOTES_DIR_NAME = "notes"
#: Where the verbatim entries aggregation read live. Hidden on purpose.
RAW_DIR_NAME = ".raw"

_DOTS_ONLY = re.compile(r"^\.+$")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._\- 一-鿿]+$")


class UnsafeMemoryPath(CofferError):  # noqa: N818
    """A path segment that is hidden, all dots, or otherwise unsafe.

    See "Confine reads to registered agents' memory paths".
    """

    code = "MEMORY_UNSAFE_PATH"

    def __init__(self, segment: str, reason: str) -> None:
        super().__init__(f"unsafe memory path segment {segment!r}: {reason}")
        self.segment = segment
        self.reason = reason


def memory_root() -> pathlib.Path:
    """The one directory the memory layer lives in: ``derived/memory``."""
    return derived_root() / "memory"


def triggers_root() -> pathlib.Path:
    """Where authored memory triggers live: ``vault/memory-triggers/``, one file
    per trigger (ADR storage-is-five-classes-by-nature). In the vault, not under
    the memory root, because a person wrote them: deleting and rebuilding the
    derived memory tree must not take them with it."""
    return vault_root() / "memory-triggers"


def notes_signature(name: str) -> tuple[tuple[str, int, int], ...]:
    """What a partition's ``notes/`` holds, cheaply: each file's name, mtime and
    size. A ranking index built from the notes is rebuilt when this changes;
    empty when the directory does not exist."""
    try:
        directory = notes_dir(name)
        with os.scandir(directory) as it:
            entries = [
                (e.name, e.stat().st_mtime_ns, e.stat().st_size)
                for e in it
                if e.is_file() and e.name.endswith(".md")
            ]
    except (OSError, UnsafeMemoryPath):
        return ()
    return tuple(sorted(entries))


def check_segment(segment: str) -> None:
    """Refuse a partition or note name that is hidden, all dots, or unsafe.

    A partition name is produced by ``domain.memory.partition.partition_slug`` /
    ``disambiguate``, which already yield safe slugs — this guard is defence in
    depth for the case a caller builds one another way, per "Confine reads to
    registered agents' memory paths": every path built from a source's contents
    must pass a traversal guard.
    """
    if not segment:
        raise UnsafeMemoryPath(segment, "empty path segment")
    if _DOTS_ONLY.fullmatch(segment):
        raise UnsafeMemoryPath(segment, "traversal segment")
    if segment.startswith("."):
        raise UnsafeMemoryPath(segment, "hidden entries are not addressable")
    if not _SAFE_SEGMENT.fullmatch(segment):
        raise UnsafeMemoryPath(segment, "unsafe segment")


def partition_dir(name: str) -> pathlib.Path:
    """The directory of one partition — ``global`` or a repository slug."""
    check_segment(name)
    return memory_root() / name


def notes_dir(name: str) -> pathlib.Path:
    """Where a partition keeps Coffer's own notes, one topic per file."""
    return partition_dir(name) / NOTES_DIR_NAME


def note_path(name: str, slug: str) -> pathlib.Path:
    """One note's file inside partition ``name``."""
    check_segment(slug)
    return notes_dir(name) / f"{slug}.md"


def raw_dir(name: str) -> pathlib.Path:
    """Where aggregation writes what it read, verbatim (see "Keep raw entries verbatim and hidden").

    Built from ``partition_dir`` and a constant rather than through
    ``check_segment``, which refuses a dot-prefixed segment on purpose: the
    guard exists to stop a *caller-supplied* name from reaching a hidden
    directory, and this is the one hidden directory the layer itself owns.
    """
    return partition_dir(name) / RAW_DIR_NAME


def raw_path(name: str, entry_id: str) -> pathlib.Path:
    """One raw entry's file inside partition ``name``."""
    check_segment(entry_id)
    return raw_dir(name) / f"{entry_id}.md"


def index_path(name: str) -> pathlib.Path:
    """The partition's index — the distil pass's to write."""
    return partition_dir(name) / INDEX_NAME


def retired_path(name: str) -> pathlib.Path:
    """The partition's retirement record (see "Record retirements so they stick")."""
    return partition_dir(name) / RETIRED_NAME


def relative_of(path: pathlib.Path) -> str:
    """The memory-root-relative form of an absolute path."""
    root = memory_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
