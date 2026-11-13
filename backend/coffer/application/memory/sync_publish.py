"""Publish: this machine's agents' own memories into the hub (spec memory
"Publish only what the origin agent wrote, and only from its machine").

Each registered agent's native memory is read through its reader. Every memory
the agent wrote itself becomes, or updates, one hub entry; a memory it no
longer holds is deleted from the hub.
Only entries this machine and this agent published are ever changed or
deleted here. A source that is unchanged since the last sync is not re-read
("Skip unchanged sources"); a reader that fails costs only that source, and
the entries it published before are left standing ("Fail a broken reader
loudly and in isolation").

Before an entry is published:

- its project is resolved: one learned in a repository is filed under the
  repository's project key; any other is not published ("Identify a project
  by a key that does not depend on the machine", "Sync only project
  memories");
- its paths are made portable ("Store paths in a memory portably");
- it is withheld when it holds something shaped like a secret ("Withhold a
  memory that looks like a secret");
- a change that only restates what Coffer delivered to this agent is recorded
  without publishing ("Never republish Coffer's own copies").
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from coffer.application.memory.sources import AgentSource, SourceFailure
from coffer.domain.memory import absorption
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.hub import (
    CLAUDE_CODE,
    HubEntry,
    Origin,
    entry_id,
    one_line,
)
from coffer.domain.memory.portable import from_portable, to_portable
from coffer.domain.memory.reader import MemoryReader, RawEntry, SourceFile
from coffer.infrastructure.memory.checkouts import Checkout
from coffer.infrastructure.memory.hub_store import HubChanges
from coffer.infrastructure.memory.sync_ledger import Ledger, SourceRecord

#: The rule that says a text holds a secret, or ``None``.
FindSecret = Callable[[str], str | None]
#: The project a directory is inside, or ``None``.
ProjectOf = Callable[[str], Checkout | None]


@dataclass(frozen=True)
class Withheld:
    agent: str
    path: str


@dataclass
class PublishResult:
    changes: HubChanges = field(default_factory=HubChanges)
    created: list[HubEntry] = field(default_factory=list)
    updated: list[HubEntry] = field(default_factory=list)
    deleted: list[HubEntry] = field(default_factory=list)
    withheld: list[Withheld] = field(default_factory=list)
    failures: list[SourceFailure] = field(default_factory=list)
    absorbed: int = 0
    sources_read: int = 0
    sources_skipped: int = 0


@dataclass(frozen=True)
class PublishContext:
    machine: str
    home: str
    now: str
    find_secret: FindSecret
    project_of: ProjectOf


def failure(agent: str, path: str, exc: Exception) -> SourceFailure:
    """One source's failure, whatever shape it took: a reader with a bug costs
    that source, not the sync."""
    if isinstance(exc, UnreadableMemory):
        return SourceFailure(agent=agent, path=exc.path, reason=exc.reason)
    return SourceFailure(agent=agent, path=path, reason=f"{type(exc).__name__}: {exc}")


def source_identity(agent_type: str, config_dir: str, source: SourceFile, anchor: str) -> str:
    """What names one memory inside an agent, stable across a re-read.

    Claude Code: the topic file's path under the config directory. Codex: the
    summary file plus the reader's anchor (the topic's scope and content
    hash), so a topic Codex rewrote is a new memory.
    """
    try:
        rel = pathlib.Path(source.path).relative_to(config_dir).as_posix()
    except ValueError:
        rel = source.path
    if agent_type == CLAUDE_CODE:
        return rel.removesuffix(".md")
    return f"{rel}::{anchor}"


def publish(
    agents: Sequence[AgentSource],
    readers: Mapping[str, MemoryReader],
    hub: Mapping[str, HubEntry],
    ledger: Ledger,
    ctx: PublishContext,
) -> PublishResult:
    """Plan this machine's changes to the hub; update ``ledger.sources``."""
    result = PublishResult()
    produced: dict[str, set[str]] = {}
    judged: set[str] = set()
    new_sources: dict[str, SourceRecord] = {}

    for agent in agents:
        reader = readers.get(agent.agent_type)
        if reader is None:
            continue
        ids = produced.setdefault(agent.agent_type, set())
        try:
            listed = reader.sources(agent.config_dir)
        except Exception as exc:
            result.failures.append(failure(agent.agent, agent.config_dir, exc))
            ids |= {e.id for e in hub.values() if _mine(e, ctx.machine, agent.agent_type)}
            continue
        if not listed and not pathlib.Path(agent.config_dir).is_dir():
            ids |= {e.id for e in hub.values() if _mine(e, ctx.machine, agent.agent_type)}
            continue
        judged.add(agent.agent_type)
        for source in listed:
            before = ledger.sources.get(source.path)
            if before and before.digest == source.digest and all(i in hub for i in before.entries):
                result.sources_skipped += 1
                ids.update(before.entries)
                new_sources[source.path] = before
                continue
            try:
                entries = reader.read(source)
            except Exception as exc:
                result.failures.append(failure(agent.agent, source.path, exc))
                if before:
                    ids.update(before.entries)
                    new_sources[source.path] = before
                continue
            result.sources_read += 1
            kept = _publish_source(agent, source, entries, hub, ledger, ctx, result)
            ids.update(kept)
            new_sources[source.path] = SourceRecord(digest=source.digest, entries=sorted(kept))

    for entry in hub.values():
        agent_type = entry.origin.agent
        if agent_type not in judged or not _mine(entry, ctx.machine, agent_type):
            continue
        if entry.id not in produced.get(agent_type, set()):
            result.changes.deletes.append(entry)
            result.deleted.append(entry)
    ledger.sources = new_sources
    return result


def _mine(entry: HubEntry, machine: str, agent_type: str) -> bool:
    return entry.origin.machine == machine and entry.origin.agent == agent_type


def _publish_source(
    agent: AgentSource,
    source: SourceFile,
    entries: Sequence[RawEntry],
    hub: Mapping[str, HubEntry],
    ledger: Ledger,
    ctx: PublishContext,
    result: PublishResult,
) -> set[str]:
    """Publish one source's entries; answer the ids it stands for in the hub."""
    kept: set[str] = set()
    delivered = ledger.delivered.get(agent.agent_type, [])
    seen: set[str] = set()
    for raw in entries:
        identity = source_identity(agent.agent_type, agent.config_dir, source, raw.anchor)
        eid = entry_id(ctx.machine, agent.agent_type, identity)
        if eid in seen:
            continue
        seen.add(eid)
        placed = _place(raw, ctx)
        if placed is None:
            # The agent still holds the memory and its repository is gone from
            # this machine: another machine may still use the entry, so it
            # stays ("Publish only what the origin agent wrote, and only from
            # its machine").
            if eid in hub and _gone(raw):
                kept.add(eid)
            continue
        project, roots = placed
        text = "\n".join((raw.title, raw.description, raw.body))
        if ctx.find_secret(text):
            result.withheld.append(Withheld(agent=agent.agent, path=source.path))
            if eid in hub:
                kept.add(eid)
            continue
        existing = hub.get(eid)
        old = (
            from_portable(existing.body, repo_root=roots[0] if roots else None, home=ctx.home)
            if existing
            else ""
        )
        if absorption.only_delivered(old, raw.body, delivered):
            result.absorbed += 1
            if existing is not None:
                kept.add(eid)
            continue
        entry = HubEntry(
            id=eid,
            origin=Origin(machine=ctx.machine, agent=agent.agent_type, source=identity),
            project=project,
            type=raw.type,
            title=one_line(raw.title, 200),
            description=one_line(raw.description, 400),
            body=to_portable(raw.body.strip("\n"), repo_roots=roots, home=ctx.home),
            created_at=existing.created_at if existing else ctx.now,
            updated_at=ctx.now,
        )
        kept.add(eid)
        if existing is not None and existing.same_content(entry):
            continue
        if existing is not None:
            result.updated.append(entry)
        else:
            result.created.append(entry)
        result.changes.upserts.append(entry)
    return kept


def _place(raw: RawEntry, ctx: PublishContext) -> tuple[str, list[str]] | None:
    """``(project key, repository roots)`` for an entry, or ``None`` when the
    entry is not published.

    An entry stays where its agent filed it, whatever its type: under the
    repository its directory is inside, as that repository's project. A memory
    learned in no repository (a scratch directory, a session with no working
    directory) is not published ("Sync only project memories")."""
    directory = raw.project_root
    if not directory:
        return None
    checkout = ctx.project_of(directory)
    if checkout is None:
        return None
    roots = [checkout.root]
    if directory.rstrip("/") != checkout.root.rstrip("/"):
        roots.append(directory)
    return checkout.key, roots


def _gone(raw: RawEntry) -> bool:
    """Whether the directory the entry was learned in is no longer there."""
    return bool(raw.project_root) and not pathlib.Path(raw.project_root).exists()


__all__ = [
    "FindSecret",
    "ProjectOf",
    "PublishContext",
    "PublishResult",
    "Withheld",
    "failure",
    "publish",
    "source_identity",
]
