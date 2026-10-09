"""What one memory sync decides before it writes anything (spec memory
"Preview a first or large sync", "Hand an edited or removed copy to the
agent").

Plain values: the copies a machine holds in its agents (the ledger's records),
the hub entries to write into one agent here (targets), and the operations a
sync plans from the two. The state machine that turns records and targets into
operations is :func:`plan_copies`; it is pure, so every case of "the agent
edited or removed a copy" is a unit test with no disk.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from coffer.domain.memory.hub import HubEntry

#: A copy as Coffer last wrote it.
STATE_WRITTEN = "written"
#: A copy whose content no longer matches what Coffer wrote: the agent's now.
STATE_EDITED = "edited"
#: A copy the agent removed.
STATE_REMOVED = "removed"

ACTION_WRITE = "write"
ACTION_UPDATE = "update"
ACTION_REMOVE = "remove"

#: A sync that would write more copies than this waits for the person.
PREVIEW_THRESHOLD = 50


@dataclass(frozen=True)
class CopyRecord:
    """One copy Coffer wrote into one agent, as the ledger keeps it."""

    path: str
    entry: str
    entry_updated_at: str
    digest: str
    state: str = STATE_WRITTEN


@dataclass(frozen=True)
class Target:
    """One hub entry to write into one agent on this machine."""

    entry: HubEntry
    #: The project's checkout here, or ``None`` for a global entry.
    root: str | None
    #: The entry's text with ``<repo>`` and ``~`` expanded for this machine.
    body: str


@dataclass(frozen=True)
class CopyOp:
    """One file a sync writes, rewrites or removes in one agent."""

    agent: str
    action: str
    path: str
    entry: str
    entry_updated_at: str
    project: str
    title: str
    #: The file's new content; empty for a removal.
    content: str = ""


@dataclass
class AgentPlan:
    """What a sync would do in one agent here."""

    agent: str
    ops: list[CopyOp] = field(default_factory=list)
    #: Records the ledger keeps or changes without a write (an edit noticed).
    records: dict[str, CopyRecord] = field(default_factory=dict)


#: The digest of the file at a path now, or ``None`` when it is gone.
DigestOf = Callable[[str], str | None]
#: Where a new copy of a target goes, given the paths already taken.
PathFor = Callable[[Target, set[str]], str]
#: The file a copy of a target is.
Render = Callable[[Target], str]


def observe(records: Mapping[str, CopyRecord], digest_of: DigestOf) -> dict[str, CopyRecord]:
    """``records`` with each one's state brought up to date from disk: a
    missing file is ``removed``, a changed one ``edited``. A copy once edited
    or removed stays so: it is the agent's from then on."""
    out: dict[str, CopyRecord] = {}
    for path, rec in records.items():
        state = rec.state
        if state == STATE_WRITTEN:
            now = digest_of(path)
            if now is None:
                state = STATE_REMOVED
            elif now != rec.digest:
                state = STATE_EDITED
        out[path] = CopyRecord(path, rec.entry, rec.entry_updated_at, rec.digest, state)
    return out


def plan_copies(
    agent: str,
    targets: Sequence[Target],
    records: Mapping[str, CopyRecord],
    *,
    path_for: PathFor,
    render: Render,
    digest_of: DigestOf,
) -> AgentPlan:
    """The copies to write, update and remove in one agent.

    - A target with no copy gets one.
    - A target whose copy is as Coffer wrote it gets it rewritten when the
      content differs.
    - A copy the agent edited or removed is left alone while its entry is
      unchanged. Once the entry changes, a removed copy is written again and
      an edited one gets a new copy beside it; the edited file stays the
      agent's.
    - A copy whose entry is no longer a target here is removed when it is
      still as written; an edited one is left and forgotten.
    """
    plan = AgentPlan(agent=agent)
    current = observe(records, digest_of)
    by_entry: dict[str, list[CopyRecord]] = {}
    for rec in current.values():
        by_entry.setdefault(rec.entry, []).append(rec)
    taken = set(current)
    wanted = {t.entry.id for t in targets}

    for target in targets:
        entry = target.entry
        content = render(target)
        mine = by_entry.get(entry.id, [])
        live = [r for r in mine if r.state == STATE_WRITTEN]
        if live:
            rec = live[0]
            plan.records[rec.path] = rec
            if digest_of(rec.path) != digest_text(content):
                plan.ops.append(_op(agent, ACTION_UPDATE, rec.path, target, content))
            continue
        changed = [r for r in mine if r.entry_updated_at != entry.updated_at]
        if mine and not changed:
            for rec in mine:
                plan.records[rec.path] = rec
            continue
        removed = [r for r in mine if r.state == STATE_REMOVED]
        for rec in mine:
            if rec.state == STATE_EDITED:
                plan.records[rec.path] = rec
        if removed:
            path = removed[0].path
        else:
            path = path_for(target, taken)
            taken.add(path)
        plan.ops.append(_op(agent, ACTION_WRITE, path, target, content))

    for path, rec in current.items():
        if rec.entry in wanted:
            continue
        if rec.state == STATE_WRITTEN:
            plan.ops.append(
                CopyOp(agent, ACTION_REMOVE, path, rec.entry, rec.entry_updated_at, "", "")
            )
    return plan


def _op(agent: str, action: str, path: str, target: Target, content: str) -> CopyOp:
    entry = target.entry
    return CopyOp(
        agent=agent,
        action=action,
        path=path,
        entry=entry.id,
        entry_updated_at=entry.updated_at,
        project=entry.project,
        title=entry.title,
        content=content,
    )


def digest_text(text: str) -> str:
    """The digest a copy's content is recorded by."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "ACTION_REMOVE",
    "ACTION_UPDATE",
    "ACTION_WRITE",
    "PREVIEW_THRESHOLD",
    "STATE_EDITED",
    "STATE_REMOVED",
    "STATE_WRITTEN",
    "AgentPlan",
    "CopyOp",
    "CopyRecord",
    "Target",
    "digest_text",
    "observe",
    "plan_copies",
]
