"""What one memory sync did, in the shape the ``memory_synced`` event and the
Memory page read (spec memory "Record every sync in Activity").

The report names what was published, updated and deleted in the hub, the
copies written, updated and removed per agent and path, the memories withheld
by agent and source path (never the text), and every source that could not be
read. It never carries a memory's body.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from coffer.domain.memory.hub import HubEntry
from coffer.domain.memory.native_writer import WriterStatus
from coffer.domain.memory.sync_plan import CopyOp

if TYPE_CHECKING:
    from coffer.application.memory.sync_publish import PublishResult
    from coffer.application.memory.sync_write import Applied, LocalAgent


def _entry(entry: HubEntry) -> dict[str, str]:
    return {
        "id": entry.id,
        "title": entry.title,
        "project": entry.project,
        "agent": entry.origin.agent,
    }


@dataclass
class AgentCopies:
    written: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    aux: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.written or self.updated or self.removed or self.aux)


@dataclass
class SyncReport:
    created: list[dict[str, str]] = field(default_factory=list)
    updated: list[dict[str, str]] = field(default_factory=list)
    deleted: list[dict[str, str]] = field(default_factory=list)
    withheld: list[dict[str, str]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    copies: dict[str, AgentCopies] = field(default_factory=dict)
    writers: dict[str, WriterStatus] = field(default_factory=dict)
    held_back: dict[str, int] = field(default_factory=dict)
    absorbed: int = 0
    sources_read: int = 0
    sources_skipped: int = 0
    #: The pending preview's summary when this sync held its copies back.
    preview: dict[str, Any] | None = None

    @classmethod
    def from_publish(cls, result: PublishResult) -> SyncReport:
        return cls(
            created=[_entry(e) for e in result.created],
            updated=[_entry(e) for e in result.updated],
            deleted=[_entry(e) for e in result.deleted],
            withheld=[{"agent": w.agent, "path": w.path} for w in result.withheld],
            failures=[
                {"agent": f.agent, "path": f.path, "reason": f.reason} for f in result.failures
            ],
            absorbed=result.absorbed,
            sources_read=result.sources_read,
            sources_skipped=result.sources_skipped,
        )

    def add_applied(self, local: LocalAgent, done: Applied) -> None:
        copies = self.copies.setdefault(local.agent_type, AgentCopies())
        copies.written += [op.path for op in done.written]
        copies.updated += [op.path for op in done.updated]
        copies.removed += [op.path for op in done.removed]
        copies.aux += done.aux

    def changed(self) -> bool:
        """Whether anything was published, written or withheld: a sync that
        did none of these records no event. A source that keeps failing, or a
        preview still waiting, is shown on the Memory page rather than
        recorded again every sync."""
        return bool(
            self.created
            or self.updated
            or self.deleted
            or self.withheld
            or any(self.copies.values())
        )

    def details(self) -> dict[str, Any]:
        """The ``memory_synced`` event's details."""
        out: dict[str, Any] = {
            "hub": {"created": self.created, "updated": self.updated, "deleted": self.deleted},
            "copies": {
                agent: {
                    "written": c.written,
                    "updated": c.updated,
                    "removed": c.removed,
                    "files": c.aux,
                }
                for agent, c in self.copies.items()
                if c
            },
            "withheld": self.withheld,
            "failures": self.failures,
            "absorbed": self.absorbed,
        }
        if self.preview:
            out["preview"] = self.preview
        return out

    def summary(self) -> dict[str, Any]:
        """The short form the ledger keeps for the Memory page."""
        return {
            "published": len(self.created),
            "updated": len(self.updated),
            "deleted": len(self.deleted),
            "written": sum(len(c.written) + len(c.updated) for c in self.copies.values()),
            "removed": sum(len(c.removed) for c in self.copies.values()),
            "withheld": self.withheld,
            "failures": self.failures,
            "writers": {
                agent: {"state": s.state, "path": s.path, "reason": s.reason}
                for agent, s in self.writers.items()
            },
            "held_back": self.held_back,
            "preview": bool(self.preview),
        }


def preview_summary(ops: Sequence[CopyOp], globals_: Mapping[str, int]) -> dict[str, Any]:
    """Per agent and project, how many copies a preview would write, update
    and remove."""
    counts: Counter[tuple[str, str, str]] = Counter(
        (op.agent, op.project or "", op.action) for op in ops
    )
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for (agent, project, action), n in counts.items():
        row = rows.setdefault(
            (agent, project),
            {"agent": agent, "project": project, "write": 0, "update": 0, "remove": 0},
        )
        row[action] = n
    return {
        "copies": len(ops),
        "rows": sorted(rows.values(), key=lambda r: (r["agent"], r["project"])),
        "global": dict(globals_),
    }


__all__ = ["AgentCopies", "SyncReport", "preview_summary"]
