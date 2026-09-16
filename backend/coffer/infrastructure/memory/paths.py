"""On-disk layout for the memory layer — the sole owner of path construction.

Mirrors ``infrastructure/knowledge/paths.py`` on purpose: one root, one guard,
one override for tests. Everything under this root is derived and rebuildable
(spec memory FR-019), and a partition holds four things with one writer each:

``MEMORY.md``
    The index (FR-029). What a session is given, and what a human opens
    first. Written by the distil pass.

``notes/``
    Coffer's own notes, one topic per file (FR-020, FR-021). Written by the
    distil pass.

``RETIRED.md``
    What was retired and why (FR-025) — also the next pass's exclusion list,
    without which a deletion is undone by the next aggregation. Written by
    the distil pass.

``.raw/``
    What was read out of the agents, verbatim (FR-008). Written **only** by
    aggregation, and never by distil (FR-026): that is what lets a bad
    distillation be re-run without going back to the agents. Hidden, and
    excluded from the index, from delivery and from recall.

``$COFFER_MEMORY_ROOT`` overrides the root, exactly like knowledge's own
override, so a test can never wander into a developer's real
``~/.coffer/memory`` and rewrite it (a past bug did exactly that to the
knowledge tree with its own override left unset).
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.error_base import CofferError

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
    """A path segment that is hidden, all dots, or otherwise unsafe (FR-044)."""

    code = "MEMORY_UNSAFE_PATH"

    def __init__(self, segment: str, reason: str) -> None:
        super().__init__(f"unsafe memory path segment {segment!r}: {reason}")
        self.segment = segment
        self.reason = reason


def memory_root() -> pathlib.Path:
    """The one directory the memory layer lives in."""
    override = os.environ.get("COFFER_MEMORY_ROOT")
    if override:
        return pathlib.Path(override)
    home = pathlib.Path(os.environ.get("HOME", "~")).expanduser()
    return home / ".coffer" / "memory"


def check_segment(segment: str) -> None:
    """Refuse a partition or note name that is hidden, all dots, or unsafe.

    A partition name is produced by ``domain.memory.partition.partition_slug``
    / ``disambiguate``, which already yield safe slugs — this guard is defence
    in depth for the case a caller builds one another way, per FR-044: every
    path built from a source's contents must pass a traversal guard.
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
    """Where aggregation writes what it read, verbatim (FR-008).

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
    """The partition's index — the distil pass's to write (FR-029)."""
    return partition_dir(name) / INDEX_NAME


def retired_path(name: str) -> pathlib.Path:
    """The partition's retirement record (FR-025)."""
    return partition_dir(name) / RETIRED_NAME


def relative_of(path: pathlib.Path) -> str:
    """The memory-root-relative form of an absolute path."""
    root = memory_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
