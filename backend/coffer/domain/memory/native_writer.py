"""The port each agent's memory writer implements (spec memory "Write the hub
into Claude Code's native memory", "Write the hub into Codex's memory
extension").

Two agents, two writers, written as two ("Reintroduce no retired memory
mechanism": a third agent earns an abstraction, not before). This module is
only what the sync service composes against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.memory.sync_plan import CopyRecord, Target

#: The writer can write.
STATUS_OK = "ok"
#: The agent's own memory is switched off: nothing is written.
STATUS_OFF = "off"
#: The layout is not what the writer expects: nothing is written.
STATUS_UNRECOGNISED = "unrecognised"
#: The agent's config directory is not there.
STATUS_MISSING = "missing"


@dataclass(frozen=True)
class WriterStatus:
    state: str
    path: str = ""
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.state == STATUS_OK


@dataclass(frozen=True)
class AuxWrite:
    """A file a writer keeps beside the copies (``MEMORY.md`` with Coffer's
    block, the rules file, ``instructions.md``): the file's whole new content,
    or ``None`` to delete it. A writer computes ``MEMORY.md``'s new content
    from what is on disk, changing only the bytes between its markers."""

    path: str
    content: str | None
    #: Back the file up before changing it (it holds the agent's own lines).
    backup: bool = False


class NativeWriter(Protocol):
    agent_type: str

    def status(self, config_dir: str) -> WriterStatus: ...

    def wants(self, target: Target) -> bool:
        """Whether ``target`` is written as a per-entry copy (rather than only
        through an aux file, as Claude Code's global memories are)."""
        ...

    def path_for(self, config_dir: str, target: Target, taken: set[str]) -> str: ...

    def render(self, target: Target) -> str: ...

    def aux(
        self,
        config_dir: str,
        copies: Mapping[str, CopyRecord],
        targets: Mapping[str, Target],
        global_targets: Sequence[Target],
    ) -> list[AuxWrite]:
        """Coffer's own files beside the copies, rendered from the copies as
        they stand after a sync."""
        ...

    def undo(self, config_dir: str, copies: Mapping[str, CopyRecord]) -> list[AuxWrite]:
        """What removing Coffer's own files beside the copies takes."""
        ...


__all__ = [
    "STATUS_MISSING",
    "STATUS_OFF",
    "STATUS_OK",
    "STATUS_UNRECOGNISED",
    "AuxWrite",
    "NativeWriter",
    "WriterStatus",
]
