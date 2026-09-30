"""``MemoryService`` — the two passes, and the reads every other surface makes.

The layer has two passes and they own two directories. **Aggregation** reads
every registered, enabled agent's native memory and writes what it read,
verbatim, under each partition's hidden ``.raw/`` (``aggregate.py``).
**Distil** turns those entries into Coffer's own notes and rewrites the index
(``distil.py``). This service is where each pass meets the database: which
agents are registered, which partitions have a Resource row, which repository
each row records, and the audit event that says a pass happened.

**A partition carries no per-agent reach and no enabled switch (see "Serve every
partition to every agent"), and the read path here has no ``agent`` parameter to narrow
by.** It used to: a new partition was scoped to the agents it had been aggregated from,
which on a real vault meant ``coffer`` was scoped to ``claude-code`` alone and Codex got
no project memory at all, while the ``account*`` partitions were scoped to ``codex`` and
Claude Code got nothing from them. Memory aggregated from several agents exists so each
of them can read what the others learned, so every partition is served — see
``kind.py``.

Everything it hands back it reads **from disk at call time**, and that is structural
rather than stylistic. A note has no status any more: a retirement takes the file out of
``notes/`` and records it in ``RETIRED.md`` (see "Record retirements so they stick"), so
there is nothing to filter — the note is simply not in the directory. That guarantee
holds only as far as the read does. The previous design served ``list_facts`` from a
value it had already computed, and went on handing back 11 facts it had itself marked
superseded; ``list_notes`` below opens the directory every time so that cannot recur,
and ``context.py`` states it as the promise it relies on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from coffer.application.audit_service import AuditService
from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.engine_timeout import TimeoutReader
from coffer.application.memory.aggregate import (
    AgentSourceResolver,
    AggregationResult,
    PartitionTouch,
    Placement,
    run_aggregation,
)
from coffer.application.memory.distil import DistilResult, distil_partition
from coffer.application.memory.partition_row import (
    MemoryPartitionConfig,
    PartitionSummary,
    config_of,
    placement_of,
    summary_of,
)
from coffer.application.memory.triggers import TriggerDraft
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.note import Note
from coffer.domain.memory.reader import MemoryReader
from coffer.infrastructure.memory import store

KIND_MEMORY = "memory"


#: Files one proposed trigger; the trigger service's ``propose``.
TriggerProposer = Callable[[TriggerDraft], Awaitable[object]]


class MemoryService:
    """The two passes' database half, and the one read path over ``notes/``.

    The three internal-engine arguments all default to ``None``, and that default is a
    configuration rather than a gap: ``distil_partition`` treats a missing selector, a
    selector with no connection on it and a missing completion port as one answer — the
    mechanical pass of "Distil mechanically with no internal connection", where each raw
    entry becomes a note of its own and the index is still written. So a vault with no
    internal connection and a service constructed without the provider kind take the
    same path, and there is no null adapter in between whose behaviour could differ from
    the real absence it stands for.
    """

    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        agent_source_resolver: AgentSourceResolver,
        readers: Mapping[str, MemoryReader],
        completion: LlmCompletionPort | None = None,
        model_selector: ModelSelectorPort | None = None,
        secret_resolver: Callable[[str], str] | None = None,
        read_timeout: TimeoutReader | None = None,
    ) -> None:
        self._read_timeout = read_timeout
        self._resources = resources
        self._audit = audit
        self._resolve_agent_source = agent_source_resolver
        # One reader per agent type value: the memory-reader facets of the
        # agents (ADR agent-mechanisms-are-optional-facets-on-the-descriptor),
        # handed in by the composition root. An agent without one is skipped.
        self._readers: Mapping[str, MemoryReader] = dict(readers)
        self._completion = completion
        self._models = model_selector
        self._secret_resolver = secret_resolver
        self._propose_trigger: TriggerProposer | None = None

    def set_trigger_proposer(self, proposer: TriggerProposer) -> None:
        """Where a distil pass hands the triggers it proposes: the trigger
        service, which files each one unarmed."""
        self._propose_trigger = proposer

    # ----------------------------------------------------------------- #
    # Aggregation                                                        #
    # ----------------------------------------------------------------- #

    async def aggregate(self, *, actor: str = "system") -> AggregationResult:
        """One pass over every registered, enabled agent (see "Read only registered and
        enabled agents' memory").

        The pass itself is in ``aggregate.py`` and touches no database. What is
        left here is the part that needs one: seeding the pass with the
        partitions that already have a row, then giving a row to each partition
        it filed into that did not have one.
        """
        agent_rows = await self._resources.list(kind="agent", enabled=True)
        memory_rows = await self._resources.list(kind=KIND_MEMORY)
        # Keyed by name because that is what a placement carries — a
        # partition's name IS its directory — but holding the whole row, so the
        # config update below addresses it by uid without a second lookup.
        known = {row.name: row for row in memory_rows}

        outcome = run_aggregation(
            agents=[self._resolve_agent_source(row) for row in agent_rows],
            readers=self._readers,
            known=[placement_of(row) for row in memory_rows],
        )

        for touch in outcome.touched:
            row = known.get(touch.placement.name)
            if row is None:
                await self._register_partition(touch, actor=actor)
            elif placement_of(row) != touch.placement:
                await self._record_repository(row.uid, touch.placement, actor=actor)

        result = outcome.result
        await self._audit.record(
            AuditEventType.MEMORY_AGGREGATED.value,
            actor=actor,
            details={
                "partitions": list(result.partitions),
                "entries_written": result.entries_written,
                "sources_read": result.sources_read,
                "sources_skipped": result.sources_skipped,
                "failures": [f.path for f in result.failures],
                # Whose read failed and why, for the Memory page's header
                # ("Report the last read of the agents' memory").
                "failure_details": [
                    {"agent": f.agent, "path": f.path, "reason": f.reason} for f in result.failures
                ],
            },
        )
        return result

    async def _register_partition(self, touch: PartitionTouch, *, actor: str) -> None:
        """Give a newly-filled partition its Resource row — and nothing else.

        The row is created through the lifecycle opt-in: the kind sets
        ``generic_create_allowed=False`` so nothing but a pass can conjure a partition,
        which is "Provision partitions only from aggregation" — an agent's working directory
        must not bring one into existence merely by being read.

        One write, deliberately. This method used to follow the registration
        with a scope naming the agents the partition had been aggregated from,
        and that second write was the layer's worst bug: a partition filled
        only from Claude Code became invisible to Codex working in the very
        same repository. Registration is the whole job now.
        """
        await self._resources.register(
            kind=KIND_MEMORY,
            name=touch.placement.name,
            config=config_of(touch.placement),
            actor=actor,
            allow_lifecycle_kind=True,
        )

    async def _record_repository(self, uid: str, placement: Placement, *, actor: str) -> None:
        """Write a repository identity onto a partition that lacked one, or
        whose repository has moved on this disk.

        Only reached when the pass resolved something different from what the
        row says, so an unchanged partition is never rewritten and never
        records a spurious ``resource_updated`` event.
        """
        await self._resources.update_config(
            uid,
            config_of(placement),
            actor=actor,
            allow_lifecycle_kind=True,
        )

    # ----------------------------------------------------------------- #
    # Distil                                                             #
    # ----------------------------------------------------------------- #

    async def distil(self, uid: str, *, actor: str = "system") -> DistilResult:
        """Turn one partition's raw entries into notes, and rewrite its index.

        The partition is named by its **uid** and the directory to rewrite is
        read off the row: a pass spends a model and rewrites every note in a
        directory, so what it is aimed at must be what cannot be edited while
        it runs. The label can be, and is wanted here only for the path.

        Raises ``ResourceNotFound`` for a partition with no row, which is what the route
        answers 404 with: a directory nobody registered is not a partition (see "Create
        partitions only by aggregation"). The repository path travels into the pass
        because the index restates it — a partition has to explain itself to a human
        browsing it, and its directory name is only a slug (see "Identify a partition by
        its repository").

        Keeping a second concurrent pass off one partition (see "Run one distil pass
        per partition at a time") is the callers', not this method's: the record is
        per-daemon and lives in the shared upkeep-runs registry, which Update memory
        and the worker both already go through — both keyed on this uid.
        """
        row = await self._resources.get(uid)
        result = await distil_partition(
            row.name,
            completion=self._completion,
            model_selector=self._models,
            repository_path=placement_of(row).repository_path,
            secret_resolver=self._secret_resolver,
            read_timeout=self._read_timeout,
        )
        if self._propose_trigger is not None:
            for p in result.proposals:
                draft = TriggerDraft(
                    note=f"{row.name}/{p.slug}",
                    kind=p.kind,
                    command=p.command,
                    unless=p.unless,
                    error=p.error,
                )
                await self._propose_trigger(draft)
        await self._audit.record(
            AuditEventType.MEMORY_DISTILLED.value,
            resource=row,
            actor=actor,
            details={
                "merged": result.merged,
                "opened": result.opened,
                "retired": result.retired,
                "dropped": result.dropped,
                "model_used": result.model_used,
            },
        )
        return result

    # ----------------------------------------------------------------- #
    # Listing                                                            #
    # ----------------------------------------------------------------- #

    async def list_partitions(self) -> list[PartitionSummary]:
        """Every partition, counted from ``notes/`` — the management view (see
        "Present a partition as its memories")."""
        rows = await self._resources.list(kind=KIND_MEMORY)
        return [summary_of(row, placement_of(row)) for row in sorted(rows, key=lambda r: r.name)]

    async def list_notes(self, partition: str) -> tuple[Note, ...]:
        """Every note in ``partition``, read from its ``notes/`` directory now.

        No caller identity, because there is nothing to decide with one: a
        note is a file, and the payload composed at session start hands the
        agent the directory's absolute path anyway. Whether the partition is
        served at all is ``served_partitions`` below.
        """
        return store.list_notes(partition)

    async def served_partitions(self) -> list[str]:
        """The partitions Coffer serves — every one, to every agent (see "Serve
        every partition to every agent").

        There is no gate: the kind declares no enabled switch and no reach, so
        every registered partition is delivered and recalled. A partition leaves
        this list only by being deleted.
        """
        rows = await self._resources.list(kind=KIND_MEMORY)
        return sorted(r.name for r in rows)

    # ----------------------------------------------------------------- #
    # Lifecycle                                                          #
    # ----------------------------------------------------------------- #

    async def cleanup_partition(self, name: str) -> None:
        """Remove a partition's directory when its Resource is deleted.

        Safe because the tree is derived (see "Keep the memory tree derived and local"):
        the agents still hold everything it was built from, so a partition deleted by
        mistake comes back — equivalently, not identically — from the next two passes.
        """
        store.delete_partition(name)

    async def move_partition(self, old_name: str, new_name: str) -> None:
        """Move a partition's directory when its Resource is renamed.

        Unlike deletion this is not made safe by the tree being derived: a
        rename that moved nothing would leave the row naming an empty
        directory that the next pass refills from the agents' *current*
        memory, while every note the distil pass wrote and the retirement
        record that keeps deleted notes deleted sat under the old name,
        unreferenced. A move that cannot happen aborts the rename (``kind.py``).
        """
        store.rename_partition(old_name, new_name)


__all__ = [
    "KIND_MEMORY",
    "MemoryPartitionConfig",
    "MemoryService",
    "PartitionSummary",
]
