"""``MemoryService`` — the two passes, and the reads every other surface makes.

The layer has two passes and they own two directories. **Aggregation** reads
every registered, enabled agent's native memory and writes what it read,
verbatim, under each partition's hidden ``.raw/`` (``aggregate.py``).
**Distil** turns those entries into Coffer's own notes and rewrites the index
(``distil.py``). This service is where each pass meets the database: which
agents are registered, which partitions have a Resource row, which repository
each row records, and the audit event that says a pass happened.

**A partition carries no per-agent reach (FR-013), and the read path here has
no ``agent`` parameter to narrow by.** It used to: a new partition was scoped
to the agents it had been aggregated from, which on a real vault meant
``coffer`` was scoped to ``claude-code`` alone and Codex got no project memory
at all, while the ``account*`` partitions were scoped to ``codex`` and Claude
Code got nothing from them. Memory aggregated from several agents exists so
each of them can read what the others learned, so ``enabled`` is now the only
gate — see ``kind.py``.

Everything it hands back it reads **from disk at call time**, and that is
structural rather than stylistic. A note has no status any more: a retirement
takes the file out of ``notes/`` and records it in ``RETIRED.md`` (FR-025), so
there is nothing to filter — the note is simply not in the directory. That
guarantee holds only as far as the read does. The previous design served
``list_facts`` from a value it had already computed, and went on handing back
11 facts it had itself marked superseded; ``list_notes`` below opens the
directory every time so that cannot recur, and ``context.py`` and ``recall.py``
both state it as the promise they rely on.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

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
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.memory.note import Note
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.domain.memory.reader import MemoryReader
from coffer.domain.resource import Resource
from coffer.infrastructure.memory import store
from coffer.infrastructure.memory.readers import ClaudeCodeMemoryReader, CodexMemoryReader

KIND_MEMORY = "memory"


class MemoryPartitionConfig(BaseModel):
    """``Resource.config`` payload when ``kind == 'memory'``.

    Two fields, because a partition is keyed on a **repository** and a
    repository is two things: an identity that two clones agree on, and a place
    on this disk.

    ``repository_key`` is what a working directory is resolved to —
    ``remote:<host>/<path>`` when the repository has an ``origin``, so the main
    checkout, a worktree and a second clone all land here, and ``path:<abs>``
    when it has none. ``repository_path`` is the absolute root, which FR-014
    requires be recorded on the Resource and which ``context.py`` matches a
    session's ``cwd`` against. Both are empty for ``global``, which is not a
    repository.

    This replaces a single ``project_root``, whose value was the raw working
    directory an entry happened to be learned in — the key that split a
    worktree from its own checkout and made six dated scratch folders into six
    permanent partitions (FR-015).
    """

    model_config = ConfigDict(extra="forbid")

    repository_key: str = ""
    repository_path: str = ""


@dataclass(frozen=True)
class PartitionSummary:
    """One partition as the management surface lists it (FR-037).

    ``unresolvable`` is computed here rather than stored, and it is the whole
    of FR-016: a partition whose repository is no longer on this disk can never
    be resolved from any working directory again, so it is delivered to nobody.
    It is **surfaced rather than hidden**, because only the developer can
    decide whether that repository is coming back — an orphaned partition on
    the maintainer's live vault simply sat there, undeliverable and unmentioned.
    A partition that carries no ``repository_path`` at all is unresolvable for
    the same reason, and for one more: it predates repository identity, so
    nothing will ever match it either.
    """

    #: The partition's identity — what a surface addresses it by, and what the
    #: distil sweep and the Distil button both claim, so neither can be aimed
    #: at a different partition by a label that moved in between.
    uid: str
    name: str
    repository_key: str
    repository_path: str
    note_count: int
    unresolvable: bool


#: The two readers this layer supports (spec memory FR-004, FR-045 — a third
#: agent earns an abstraction, not before). Built once; a caller that wants a
#: fake substitutes the whole mapping rather than reaching inside it.
DEFAULT_READERS: Mapping[str, MemoryReader] = {
    "claude_code": ClaudeCodeMemoryReader(),
    "codex": CodexMemoryReader(),
}


class MemoryService:
    """The two passes' database half, and the one read path over ``notes/``.

    The three internal-engine arguments all default to ``None``, and that
    default is a configuration rather than a gap: ``distil_partition`` treats a
    missing selector, a selector with no connection on it and a missing
    completion port as one answer — FR-024's mechanical pass, where each raw
    entry becomes a note of its own and the index is still written. So a vault
    with no internal connection and a service constructed without the provider
    kind take the same path, and there is no null adapter in between whose
    behaviour could differ from the real absence it stands for.
    """

    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        agent_source_resolver: AgentSourceResolver,
        readers: Mapping[str, MemoryReader] | None = None,
        completion: LlmCompletionPort | None = None,
        model_selector: ModelSelectorPort | None = None,
        credential_resolver: Callable[[str], str] | None = None,
        read_timeout: TimeoutReader | None = None,
    ) -> None:
        self._read_timeout = read_timeout
        self._resources = resources
        self._audit = audit
        self._resolve_agent_source = agent_source_resolver
        self._readers: Mapping[str, MemoryReader] = (
            dict(readers) if readers is not None else DEFAULT_READERS
        )
        self._completion = completion
        self._models = model_selector
        self._credential_resolver = credential_resolver

    # ----------------------------------------------------------------- #
    # Aggregation                                                        #
    # ----------------------------------------------------------------- #

    async def aggregate(self, *, actor: str = "system") -> AggregationResult:
        """One pass over every registered, enabled agent (FR-001, FR-007).

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
            known=[_placement_of(row) for row in memory_rows],
        )

        for touch in outcome.touched:
            row = known.get(touch.placement.name)
            if row is None:
                await self._register_partition(touch, actor=actor)
            elif _placement_of(row) != touch.placement:
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
            },
        )
        return result

    async def _register_partition(self, touch: PartitionTouch, *, actor: str) -> None:
        """Give a newly-filled partition its Resource row — and nothing else.

        The row is created through the lifecycle opt-in (CODE-REG): the kind
        sets ``generic_create_allowed=False`` so nothing but a pass can conjure
        a partition, which is FR-012 — an agent's working directory must not
        bring one into existence merely by being read.

        One write, deliberately. This method used to follow the registration
        with a scope naming the agents the partition had been aggregated from,
        and that second write was the layer's worst bug: a partition filled
        only from Claude Code became invisible to Codex working in the very
        same repository. Registration is the whole job now.
        """
        await self._resources.register(
            kind=KIND_MEMORY,
            name=touch.placement.name,
            config=_config_of(touch.placement),
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
            _config_of(placement),
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

        Raises ``ResourceNotFound`` for a partition with no row, which is what
        the route answers 404 with: a directory nobody registered is not a
        partition (FR-012). The repository path travels into the pass because
        the index restates it — a partition has to explain itself to a human
        browsing it, and its directory name is only a slug (FR-014).

        Refusing a second concurrent pass over one partition (FR-041) is the
        surface's, not this method's: the record is per-daemon and lives in the
        shared upkeep-runs registry, which the HTTP layer and the worker both
        already go through — both keyed on this uid.
        """
        row = await self._resources.get(uid)
        result = await distil_partition(
            row.name,
            completion=self._completion,
            model_selector=self._models,
            repository_path=_placement_of(row).repository_path,
            credential_resolver=self._credential_resolver,
            read_timeout=self._read_timeout,
        )
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
        """Every partition, counted from ``notes/`` — the management view
        (FR-037), which includes the disabled ones the read path below skips."""
        rows = await self._resources.list(kind=KIND_MEMORY)
        return [_summary_of(row, _placement_of(row)) for row in sorted(rows, key=lambda r: r.name)]

    async def list_notes(self, partition: str) -> tuple[Note, ...]:
        """Every note in ``partition``, read from its ``notes/`` directory now.

        No caller identity, because there is nothing to decide with one: a
        note is a file, and the payload composed at session start hands the
        agent the directory's absolute path anyway. Whether the partition is
        served at all is ``enabled_partitions`` below.
        """
        return store.list_notes(partition)

    async def enabled_partitions(self) -> list[str]:
        """The partitions Coffer serves — every enabled one, to every agent
        (FR-013).

        ``enabled`` is the whole gate, and that is the point: it is a switch
        the developer sets, not a default derived from which agent happened to
        contribute first. Mirrors ``KnowledgeService``'s own read path.

        It gates what *Coffer* serves and nothing more. A note is a file, and
        a disabled partition is one nothing points the agent at — not a
        directory the agent is prevented from opening. FR-013 asks the layer
        to say so wherever it presents the flag rather than let it be read as
        a filesystem boundary it is not.
        """
        rows = await self._resources.list(kind=KIND_MEMORY, enabled=True)
        return sorted(r.name for r in rows)

    # ----------------------------------------------------------------- #
    # Lifecycle                                                          #
    # ----------------------------------------------------------------- #

    async def cleanup_partition(self, name: str) -> None:
        """Remove a partition's directory when its Resource is deleted.

        Safe because the tree is derived (FR-019): the agents still hold
        everything it was built from, so a partition deleted by mistake comes
        back — equivalently, not identically — from the next two passes.
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


def _placement_of(row: Resource) -> Placement:
    """One ``memory`` Resource row as the pass's own value object."""
    return Placement(
        name=row.name,
        repository_key=str(row.config.get("repository_key", "") or ""),
        repository_path=str(row.config.get("repository_path", "") or ""),
    )


def _config_of(placement: Placement) -> dict[str, str]:
    return {
        "repository_key": placement.repository_key,
        "repository_path": placement.repository_path,
    }


def _summary_of(row: Resource, placement: Placement) -> PartitionSummary:
    return PartitionSummary(
        uid=row.uid,
        name=row.name,
        repository_key=placement.repository_key,
        repository_path=placement.repository_path,
        note_count=len(store.list_notes(row.name)),
        unresolvable=_is_unresolvable(placement),
    )


def _is_unresolvable(placement: Placement) -> bool:
    """Can any working directory still resolve to this partition? (FR-016)

    ``global`` always can — it is delivered wherever the developer is working,
    which is what it is for. Every other partition needs a repository path that
    is still a directory on this disk.
    """
    if placement.name == GLOBAL_PARTITION:
        return False
    if not placement.repository_path:
        return True
    return not pathlib.Path(placement.repository_path).is_dir()


__all__ = [
    "DEFAULT_READERS",
    "KIND_MEMORY",
    "MemoryPartitionConfig",
    "MemoryService",
    "PartitionSummary",
]
