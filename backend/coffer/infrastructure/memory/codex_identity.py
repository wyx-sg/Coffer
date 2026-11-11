"""What a Codex hub entry's identity says about where in Codex it came from.

A Codex entry's ``Origin.source`` is ``<file>::<anchor>``
(``application.memory.sync_publish.source_identity``). The Codex reader builds
the anchor: ``<group>::<heading>::<digest>`` for a bullet of a ``MEMORY.md``
task group, ``profile::<heading>::<digest>`` for a ``memory_summary.md``
preference or (v2) General Tips paragraph, :data:`PROFILE_ANCHOR` for its User
Profile, and ``<scope>::What's in Memory::<digest>`` for a v2 summary's topic.
Kept apart from the reader package, which imports the writers.
"""

from __future__ import annotations

MEMORY_NAME = "MEMORY.md"
SUMMARY_NAME = "memory_summary.md"
#: The heading part of a v2 topic's anchor (the reader's ``V2_TOPICS_HEADING``).
V2_TOPICS_HEADING = "What's in Memory"
#: The anchor of the summary's `## User Profile` entry.
PROFILE_ANCHOR = "profile::user-profile"


__all__ = [
    "MEMORY_NAME",
    "PROFILE_ANCHOR",
    "SUMMARY_NAME",
    "V2_TOPICS_HEADING",
]
