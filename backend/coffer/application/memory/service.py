"""``MemoryService`` — ties the two finished readers to the derived store.

One pass (``aggregate``) does everything spec memory's Aggregation section
asks for: read every registered, enabled agent's native memory through its
reader, skip what has not changed (FR-006), isolate what cannot be parsed
(FR-005), file each fact into its project's partition or ``global`` (FR-012),
merge only what is certainly the same fact (FR-022, in ``aggregate.py``), and
rewrite the affected partitions (FR-023). Everything under
``~/.coffer/memory/`` is derived, so a partition is free to be cleared and
rewritten from scratch on every pass that touches it — the one thing worth
avoiding is doing that when nothing actually changed, which is why the write
step below compares against what a partition already holds before touching
disk (the acceptance scenario "a second pass with nothing changed writes
nothing" is exactly this check).

The developer's own decisions (hide/pin/supersede/settle,
``application/memory/overrides.py``) are deliberately NOT reapplied here.
This service answers to the Aggregation section of the spec; overrides are
FR-040/041's concern and belong to whatever composes delivery and recall on
top of ``list_facts``/``list_partitions`` — reapplying them a second place
would risk the two disagreeing about what "hidden" means.
"""

from __future__ import annotations

import os
import pathlib
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from coffer.application.audit_service import AuditService
from coffer.application.memory.aggregate import (
    AgentSourceResolver,
    AggregationResult,
    SourceFailure,
    assign_slugs,
    build_fact,
    merge_duplicates,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.fact import PERSONAL_TYPES, Fact
from coffer.domain.memory.partition import GLOBAL_PARTITION, disambiguate, partition_slug
from coffer.domain.memory.reader import MemoryReader, RawFact
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope, is_active
from coffer.infrastructure.memory import source_state, store
from coffer.infrastructure.memory.readers import ClaudeCodeMemoryReader, CodexMemoryReader

KIND_MEMORY = "memory"


class MemoryPartitionConfig(BaseModel):
    """``Resource.config`` payload when ``kind == 'memory'``.

    One field: the absolute project root a partition was minted for (empty
    for ``global``, and for any partition read before this field existed).
    Recorded so a later pass can find this partition by its root again
    (FR-011) instead of reminting a name that might now collide with a
    different project — the mapping is persisted on the Resource, not
    recomputed from a directory name every time.
    """

    model_config = ConfigDict(extra="forbid")

    project_root: str = ""


@dataclass(frozen=True)
class PartitionSummary:
    """One partition as the management surface lists it (FR-062)."""

    name: str
    project_root: str
    fact_count: int


#: The two readers this layer supports (spec memory FR-004, FR-073 — a third
#: agent earns an abstraction, not before). Built once; a caller that wants a
#: fake substitutes the whole mapping rather than reaching inside it.
DEFAULT_READERS: Mapping[str, MemoryReader] = {
    "claude_code": ClaudeCodeMemoryReader(),
    "codex": CodexMemoryReader(),
}


def _source_failure(agent: str, path: str, exc: Exception) -> SourceFailure:
    """One source's failure, whatever shape it took.

    A reader is meant to raise ``UnreadableMemory`` for a file it cannot
    parse, but a reader has bugs like any code, and FR-005's isolation is
    only worth anything if it holds for the failure nobody anticipated: one
    file that trips a reader must cost that file, not the whole pass.
    """
    if isinstance(exc, UnreadableMemory):
        return SourceFailure(agent=agent, path=exc.path, reason=exc.reason)
    return SourceFailure(agent=agent, path=path, reason=f"{type(exc).__name__}: {exc}")


def _home_dir() -> str:
    """The developer's home directory, by the same rule ``paths.py`` uses.

    A source whose project root IS this directory is about the person, not a
    project, and files into ``global`` regardless of its fact type (FR-012).
    """
    return str(pathlib.Path(os.environ.get("HOME", "~")).expanduser()).rstrip("/")


class MemoryService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        agent_source_resolver: AgentSourceResolver,
        readers: Mapping[str, MemoryReader] | None = None,
    ) -> None:
        self._resources = resources
        self._audit = audit
        self._resolve_agent_source = agent_source_resolver
        self._readers: Mapping[str, MemoryReader] = (
            dict(readers) if readers is not None else DEFAULT_READERS
        )

    # ----------------------------------------------------------------- #
    # Aggregation                                                        #
    # ----------------------------------------------------------------- #

    async def aggregate(self, *, actor: str = "system") -> AggregationResult:
        agent_rows = await self._resources.list(kind="agent", enabled=True)
        memory_rows = await self._resources.list(kind=KIND_MEMORY)
        known_before = {r.name for r in memory_rows}
        root_to_name: dict[str, str] = {}
        name_to_root: dict[str, str] = {}
        for row in memory_rows:
            root = str(row.config.get("project_root", "") or "")
            name_to_root[row.name] = root
            if root:
                root_to_name[root] = row.name
        claimed_names = set(known_before)

        existing_partitions = store.list_partitions()
        existing_facts: dict[str, tuple[Fact, ...]] = {
            p: store.list_facts(p) for p in existing_partitions
        }
        by_native_path: dict[str, list[Fact]] = defaultdict(list)
        for facts in existing_facts.values():
            for fact in facts:
                for origin in fact.origins:
                    by_native_path[origin.native_path].append(fact)

        old_state = source_state.load()
        new_state: dict[str, str] = {}
        failures: list[SourceFailure] = []
        sources_read = 0
        sources_skipped = 0
        home = _home_dir()
        collected: dict[str, list[Fact]] = defaultdict(list)

        for resource in agent_rows:
            agent_source = self._resolve_agent_source(resource)
            reader = self._readers.get(agent_source.agent_type)
            if reader is None:
                continue  # no reader for this agent type (FR-001): silent
            for source in reader.sources(agent_source.config_dir):
                # The digest match alone is not enough to skip: if the store
                # (or just this partition) was cleared by hand since the last
                # pass, there is nothing to reuse, and skipping would silently
                # drop the fact rather than reproduce it (FR-023 — the whole
                # tree, or any part of it, must be safe to delete and rebuild).
                if old_state.get(source.path) == source.digest and by_native_path.get(source.path):
                    sources_skipped += 1
                    new_state[source.path] = source.digest
                    for fact in by_native_path.get(source.path, ()):
                        collected[fact.partition].append(fact)
                    continue

                try:
                    raw_facts = reader.read(source)
                except Exception as exc:
                    failures.append(_source_failure(resource.name, source.path, exc))
                    # Left standing (FR-005): the digest is deliberately NOT
                    # recorded, so a future pass keeps retrying this source
                    # until its format is fixed (or it disappears).
                    for fact in by_native_path.get(source.path, ()):
                        collected[fact.partition].append(fact)
                    continue

                sources_read += 1
                new_state[source.path] = source.digest
                captured_at = datetime.now(tz=UTC).isoformat()
                for raw in raw_facts:
                    partition = _resolve_partition(
                        raw,
                        home=home,
                        root_to_name=root_to_name,
                        name_to_root=name_to_root,
                        claimed_names=claimed_names,
                    )
                    collected[partition].append(
                        build_fact(
                            raw,
                            partition=partition,
                            agent=resource.name,
                            native_path=source.path,
                            captured_at=captured_at,
                        )
                    )

        facts_written = 0
        result_partitions: list[str] = []
        for partition, partition_facts in collected.items():
            final = assign_slugs(merge_duplicates(partition_facts))
            result_partitions.append(partition)
            if set(final) == set(existing_facts.get(partition, ())):
                continue  # nothing actually changed — write nothing (FR-023)
            store.clear_facts(partition)
            for fact in final:
                store.write_fact(fact)
            facts_written += len(final)
            store.write_readme(partition, name_to_root.get(partition, ""))
            if partition not in known_before:
                await self._register_partition(
                    partition,
                    project_root=name_to_root.get(partition, ""),
                    agents={o.agent for f in final for o in f.origins},
                    actor=actor,
                )

        for partition in set(existing_partitions) - set(collected):
            await self._delete_partition(partition, actor=actor)

        source_state.save(new_state)
        await self._audit.record(
            AuditEventType.MEMORY_AGGREGATED.value,
            actor=actor,
            details={
                "partitions": sorted(result_partitions),
                "facts_written": facts_written,
                "sources_read": sources_read,
                "sources_skipped": sources_skipped,
                "failures": [f.path for f in failures],
            },
        )
        return AggregationResult(
            partitions=tuple(sorted(result_partitions)),
            facts_written=facts_written,
            sources_read=sources_read,
            sources_skipped=sources_skipped,
            failures=tuple(failures),
        )

    async def _register_partition(
        self, name: str, *, project_root: str, agents: set[str], actor: str
    ) -> None:
        await self._resources.register(
            kind=KIND_MEMORY,
            name=name,
            config={"project_root": project_root},
            actor=actor,
            allow_lifecycle_kind=True,
        )
        # Default scope: the agents it was aggregated from (FR-014), so
        # memory flows back to its own sources with no setup step. A
        # partition that already existed is never touched here — only a
        # brand-new registration reaches this method.
        await self._resources.update_scope(
            ResourceRef(KIND_MEMORY, name),
            Scope(agents=sorted(agents)),
            actor=actor,
        )

    async def _delete_partition(self, name: str, *, actor: str) -> None:
        ref = ResourceRef(KIND_MEMORY, name)
        try:
            await self._resources.get(ref)
        except ResourceNotFound:
            # No matching Resource row (should not happen under FR-013, but a
            # stray directory is still worth clearing defensively).
            store.delete_partition(name)
            return
        # The kind's on_delete hook (kind.py) removes the directory.
        await self._resources.delete(ref, actor=actor)

    # ----------------------------------------------------------------- #
    # Listing                                                            #
    # ----------------------------------------------------------------- #

    async def list_partitions(self) -> list[PartitionSummary]:
        """Every partition, with its fact count — an unfiltered management
        view (FR-062), not the agent-scoped read path below."""
        rows = await self._resources.list(kind=KIND_MEMORY)
        return [
            PartitionSummary(
                name=r.name,
                project_root=str(r.config.get("project_root", "") or ""),
                fact_count=len(store.list_facts(r.name)),
            )
            for r in sorted(rows, key=lambda r: r.name)
        ]

    async def list_facts(self, partition: str, *, agent: str | None = None) -> tuple[Fact, ...]:
        """Every fact in ``partition``, or none at all when ``agent`` is given
        and is out of that partition's scope (FR-014) — reported as absent
        rather than forbidden, mirroring ``KnowledgeService``."""
        if agent is not None and partition not in await self.visible_partitions(agent):
            return ()
        return store.list_facts(partition)

    async def visible_partitions(self, agent: str | None) -> list[str]:
        """The partitions ``agent`` may see (FR-014), mirroring
        ``KnowledgeService.visible_collections``."""
        rows = await self._resources.list(kind=KIND_MEMORY, enabled=True)
        return sorted(r.name for r in rows if is_active(r.scope, agent))

    # ----------------------------------------------------------------- #
    # Lifecycle                                                          #
    # ----------------------------------------------------------------- #

    async def cleanup_partition(self, name: str) -> None:
        """Remove a partition's directory when its Resource is deleted."""
        store.delete_partition(name)


def _resolve_partition(
    raw: RawFact,
    *,
    home: str,
    root_to_name: dict[str, str],
    name_to_root: dict[str, str],
    claimed_names: set[str],
) -> str:
    """Which partition ``raw`` files into (FR-012).

    A personal-typed fact, one with no project root, or one whose root IS the
    developer's home directory all go to ``global``. Anything else belongs to
    its project's partition, named once and remembered by the Resource
    (``root_to_name``/``name_to_root`` — the caller's per-pass cache, seeded
    from every ``memory``-kind Resource that already exists) rather than
    recomputed from the directory name on every pass.
    """
    root = (raw.project_root or "").rstrip("/")
    if raw.type in PERSONAL_TYPES or not root or root == home:
        return GLOBAL_PARTITION
    existing = root_to_name.get(root)
    if existing is not None:
        return existing
    slug = partition_slug(root)
    name = disambiguate(root, frozenset(claimed_names)) if slug in claimed_names else slug
    root_to_name[root] = name
    name_to_root[name] = root
    claimed_names.add(name)
    return name
