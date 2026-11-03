"""Which hub entries an agent filed as task material (spec memory "Flag the
memories an agent filed as task material", ADR
memory-is-about-the-person-knowledge-is-about-the-world).

Memory holds what is about the person; notes on how an outside system, team or
process works belong in knowledge. Coffer judges no text to tell them apart: it
reads where the agent itself filed the memory.

- A Codex memory is task material when its identity names a task group: a
  bullet of a ``MEMORY.md`` task group, or a project's item under the newer
  summary's "What's in Memory" (:func:`codex_identity.task_group`). Codex's
  profile, preferences and general tips are not.
- A Claude Code memory is task material when it is typed ``reference``
  (where outside information lives). ``user``, ``feedback`` and ``project``
  memories are not.
"""

from __future__ import annotations

from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, TYPE_REFERENCE, HubEntry
from coffer.infrastructure.memory.codex_identity import task_group


def is_task_material(entry: HubEntry) -> bool:
    """Whether ``entry``'s agent filed it as task material."""
    if entry.origin.agent == CODEX:
        return bool(task_group(entry.origin.source))
    if entry.origin.agent == CLAUDE_CODE:
        return entry.type == TYPE_REFERENCE
    return False


__all__ = ["is_task_material"]
