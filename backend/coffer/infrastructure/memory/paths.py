"""On-disk layout for the memory layer — the sole owner of path construction.

Mirrors ``infrastructure/knowledge/paths.py`` on purpose: one root, one guard,
one override for tests. Everything under this root is derived and rebuildable
(spec memory FR-023) — a partition is a directory holding a ``README.md`` that
says what it is, a ``summary.md`` digest another package writes, and a
``facts/`` folder of one Markdown file per fact. ``$COFFER_MEMORY_ROOT``
overrides the root, exactly like knowledge's own override, so a test can never
wander into a developer's real ``~/.coffer/memory`` and rewrite it (a past bug
did exactly that to the knowledge tree with its own override left unset).
"""

from __future__ import annotations

import os
import pathlib
import re

from coffer.domain.error_base import CofferError

README_NAME = "README.md"
SUMMARY_NAME = "summary.md"
FACTS_DIR_NAME = "facts"

_DOTS_ONLY = re.compile(r"^\.+$")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._\- 一-鿿]+$")


class UnsafeMemoryPath(CofferError):  # noqa: N818
    """A path segment that is hidden, all dots, or otherwise unsafe (FR-072)."""

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
    """Refuse a partition or fact name that is hidden, all dots, or unsafe.

    A partition name is produced by ``domain.memory.partition.partition_slug``
    / ``disambiguate``, which already yield safe slugs — this guard is defence
    in depth for the case a caller builds one another way, per FR-072: every
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
    """The directory of one partition — ``global`` or a project slug."""
    check_segment(name)
    return memory_root() / name


def facts_dir(name: str) -> pathlib.Path:
    """Where a partition keeps its one-file-per-fact Markdown."""
    return partition_dir(name) / FACTS_DIR_NAME


def fact_path(name: str, slug: str) -> pathlib.Path:
    """One fact's file inside partition ``name``."""
    check_segment(slug)
    return facts_dir(name) / f"{slug}.md"


def summary_path(name: str) -> pathlib.Path:
    """The partition's derived digest — organise's to write, not this layer's."""
    return partition_dir(name) / SUMMARY_NAME


def readme_path(name: str) -> pathlib.Path:
    """The partition's self-description, naming its project root (FR-011)."""
    return partition_dir(name) / README_NAME


def relative_of(path: pathlib.Path) -> str:
    """The memory-root-relative form of an absolute path."""
    root = memory_root()
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
