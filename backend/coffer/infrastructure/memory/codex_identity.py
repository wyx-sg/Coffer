"""What a Codex hub entry's identity says about where in Codex it came from.

A Codex entry's ``Origin.source`` is ``<file>::<anchor>``
(``application.memory.sync_publish.source_identity``). The Codex reader builds
the anchor: ``<group>::<heading>::<digest>`` for a bullet of a ``MEMORY.md``
task group, ``profile::<heading>::<digest>`` for a ``memory_summary.md``
preference and :data:`PROFILE_ANCHOR` for its User Profile. The Claude Code
writer reads it back to tell a standing memory from one learned in a task.
Kept apart from the reader package, which imports the writers.
"""

from __future__ import annotations

import pathlib

MEMORY_NAME = "MEMORY.md"
SUMMARY_NAME = "memory_summary.md"
#: The anchor of the summary's `## User Profile` entry.
PROFILE_ANCHOR = "profile::user-profile"


def task_group(source: str) -> str:
    """The `MEMORY.md` task group a Codex entry's identity names, or ``""``.

    The identity is ``<file>::<anchor>`` (``sync_publish.source_identity``) and
    a group bullet's anchor is ``<group>::<heading>::<digest>`` (:func:`_anchor`),
    so the group is whatever sits between the file and the last two parts. A
    summary entry (profile or preference) belongs to no group."""
    file, sep, anchor = source.partition("::")
    if not sep or pathlib.PurePosixPath(file).name != MEMORY_NAME:
        return ""
    parts = anchor.rsplit("::", 2)
    return parts[0] if len(parts) == 3 else ""


def is_profile(source: str) -> bool:
    """Whether a Codex entry's identity names the summary's User Profile."""
    file, _, anchor = source.partition("::")
    return pathlib.PurePosixPath(file).name == SUMMARY_NAME and anchor == PROFILE_ANCHOR


__all__ = ["MEMORY_NAME", "PROFILE_ANCHOR", "SUMMARY_NAME", "is_profile", "task_group"]
