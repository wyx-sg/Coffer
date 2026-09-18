"""What every workflow command does the same way (spec workflow).

The run service and the node service are two vocabularies over one mechanism:
read the run, refuse the caller who may not act, append to the log, then write
the projection the log now folds to. That mechanism lives here so both
services perform it identically — a guard honoured on one path and not the
other is no guard at all.

Two decisions are worth stating, because neither is obvious from the code:

* **The events are appended before the projection is written.** The log is the
  record of truth (FR-014), so the write that matters goes first; the
  projection is a cache of a fold over it. A caller that loses the version race
  therefore leaves its events behind while its projection write is refused —
  and that is recoverable exactly because the log is the truth:
  ``rebuild_projection`` folds them in. The alternative, writing the projection
  first, would leave the opposite and unrecoverable state, a run that claims a
  position no event ever produced.
* **The projection is a fold of the whole log, never a patch.** Computing it
  incrementally would give two ways to arrive at a position, and the restart
  test only proves one of them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from coffer.application.workflow.ports import (
    AttemptRepoPort,
    AttemptRow,
    EventRepoPort,
    EventRow,
    MachineIdPort,
    RunRepoPort,
    RunRow,
)
from coffer.domain.errors import ResourceNotFound
from coffer.domain.workflow.errors import WorkflowVersionConflict
from coffer.domain.workflow.events import (
    ActorKind,
    EventActor,
    EventType,
    WorkflowEvent,
    project,
)
from coffer.domain.workflow.run import NodeStatus, RunProjection, RunStatus
from coffer.domain.workflow.template import WorkflowTemplate, parse_template
from coffer.domain.workflow.transitions import (
    ensure_owning_machine,
    ensure_run_mutable,
    ensure_version,
)

_logger = logging.getLogger(__name__)

#: A run is not a Resource (FR-011), so there is no ``RunNotFound`` of its own.
#: ``ResourceNotFound`` is reused for one practical reason: every surface
#: already maps it to 404, and a bespoke error would have to be wired into each
#: of them before an unknown run id answered anything but 500.
KIND_RUN = "workflow_run"

#: Who a command is attributed to when the caller does not say. The surfaces
#: pass their own; this default keeps a test or a CLI one-liner from having to
#: construct an actor to append an event.
DEFAULT_ACTOR = EventActor(actor_kind=ActorKind.USER, source_surface="api")

#: The engine moving a run on its own — the advancer, the driver collecting a
#: turn's result. Distinct from the developer's own commands in the log.
ENGINE_ACTOR = EventActor(actor_kind=ActorKind.WORKFLOW, source_surface="daemon")

#: The daemon doing something *to* a run rather than advancing it: rebuilding a
#: projection, reporting a turn that a restart interrupted (FR-027).
SYSTEM_ACTOR = EventActor(actor_kind=ActorKind.SYSTEM, source_surface="daemon")


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PendingEvent:
    """One event a command intends to append, before it has a sequence.

    A command decides WHAT happened; ``RunCommands.commit`` decides when it is
    written and folds the result. Keeping the two apart is what lets a command
    append several events and still produce exactly one projection write — and
    therefore one version bump — rather than a partial run visible in between.
    """

    event_type: EventType
    stage_key: str | None = None
    node_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult:
    """What an accepted command did: the run as it now stands, and the events
    it appended. The events are returned rather than looked up again because a
    caller reacting to a command — the advancer, a surface rendering a toast —
    wants to know *which* thing happened, and "run failed" versus "node
    started" is exactly the distinction the run row cannot express."""

    run: RunRow
    events: tuple[EventType, ...]
    attempt: AttemptRow | None = None

    def appended(self, event_type: EventType) -> bool:
        return event_type in self.events


def actor_dict(actor: EventActor) -> dict[str, Any]:
    """The ``actor`` column's JSON shape (data-model: ``workflow_events``)."""
    return {
        "actor_kind": actor.actor_kind.value,
        "actor_id": actor.actor_id,
        "source_surface": actor.source_surface,
    }


def to_domain_event(row: EventRow) -> WorkflowEvent | None:
    """One stored row as the fold wants it, or ``None`` for a type this build
    does not know.

    An unknown type is skipped rather than raised: the vocabulary is closed and
    only this layer writes it, so a row outside it means a database written by
    a newer build — and refusing to fold it would strand every run on the older
    one rather than the one run that carries it.
    """
    try:
        event_type = EventType(row.event_type)
    except ValueError:
        _logger.warning(
            "workflow.event.unknown_type",
            extra={"run_id": row.run_id, "sequence": row.sequence, "type": row.event_type},
        )
        return None
    return WorkflowEvent(
        sequence=row.sequence,
        event_type=event_type,
        stage_key=row.stage_key,
        node_key=row.node_key,
        payload=row.payload,
        created_at=row.created_at,
    )


def parse_snapshot(snapshot: Mapping[str, Any]) -> WorkflowTemplate:
    """A frozen snapshot as value objects (FR-010).

    Parsed without ``known_skills`` or ``allowed_agents`` on purpose: the
    snapshot passed those checks when the template was written, and re-applying
    them now would strand a run whose skill has since been renamed.
    """
    return parse_template(dict(snapshot))


def template_of(run: RunRow) -> WorkflowTemplate:
    """The template this run executes — its own frozen copy, never the
    resource as it stands today (FR-010)."""
    return parse_snapshot(run.template_snapshot)


class RunCommands:
    """The read-guard-append-project cycle, shared by both services."""

    def __init__(
        self,
        *,
        runs: RunRepoPort,
        events: EventRepoPort,
        attempts: AttemptRepoPort,
        machine: MachineIdPort,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._runs = runs
        self._events = events
        self._attempts = attempts
        self._machine = machine
        self._clock = clock

    @property
    def clock(self) -> Callable[[], datetime]:
        return self._clock

    @property
    def machine_id(self) -> str:
        return self._machine.current()

    async def require_run(self, run_id: str) -> RunRow:
        run = await self._runs.get_run(run_id)
        if run is None:
            raise ResourceNotFound(KIND_RUN, run_id)
        return run

    def guard(self, run: RunRow, attempted: str, version: int | None) -> RunStatus:
        """Refuse every caller who may not issue this command.

        The order is deliberate. Machine first (FR-012): a run this machine does
        not own is read-only here whatever version the caller holds, and telling
        them their version is stale would send them to re-read a run they still
        could not advance. Terminal next (FR-013, FR-016): "never again" is a
        better answer than "not at this version". Version last (FR-015).

        ``version=None`` is the engine acting on its own behalf — the driver
        recording the result of a turn it just ran. It has no observed version
        to be stale about; the caller with one always passes it.
        """
        ensure_owning_machine(run.id, run.machine_id, self.machine_id)
        status = RunStatus(run.status)
        ensure_run_mutable(status, attempted, run.id)
        if version is not None:
            ensure_version(
                run.id,
                run.version,
                version,
                status=status,
                stage_key=run.current_stage_key,
                node_key=run.current_node_key,
            )
        return status

    async def domain_events(self, run_id: str) -> list[WorkflowEvent]:
        rows = await self._events.list_events(run_id)
        return [event for event in (to_domain_event(row) for row in rows) if event is not None]

    async def fold(self, run_id: str) -> RunProjection:
        """The projection the run's whole log produces right now (FR-014)."""
        projection = project(await self.domain_events(run_id))
        return RunProjection(
            status=projection.status.value,
            current_stage_key=projection.current_stage_key,
            current_node_key=projection.current_node_key,
            tokens_spent=projection.tokens_spent,
        )

    async def append(self, run_id: str, pending: PendingEvent, actor: EventActor) -> None:
        await self._events.append_event(
            event_id=uuid4().hex,
            run_id=run_id,
            event_type=pending.event_type.value,
            actor=actor_dict(actor),
            stage_key=pending.stage_key,
            node_key=pending.node_key,
            payload=dict(pending.payload),
            now=self._clock(),
        )

    async def commit(
        self,
        run: RunRow,
        pending: Sequence[PendingEvent],
        *,
        actor: EventActor,
        attempt: AttemptRow | None = None,
    ) -> CommandResult:
        """Append the events, then write the projection they fold to.

        The projection write carries the version the run was read at, so two
        clients that both passed the version check still produce one change:
        the second one's ``update_run_projection`` finds the version moved and
        the command is refused (FR-015). It is not retried — the caller's
        decision was made against a run that has since changed, and re-deciding
        it here would be this layer inventing an intent.
        """
        for item in pending:
            await self.append(run.id, item, actor)
        projection = await self.fold(run.id)
        updated = await self._runs.update_run_projection(
            run.id, run.version, projection, now=self._clock()
        )
        if updated is None:
            current = await self._runs.get_run(run.id)
            raise WorkflowVersionConflict(
                run.id,
                expected=run.version,
                current=current.version if current is not None else run.version,
                status=current.status if current is not None else None,
                stage_key=current.current_stage_key if current is not None else None,
                node_key=current.current_node_key if current is not None else None,
            )
        return CommandResult(
            run=updated,
            events=tuple(item.event_type for item in pending),
            attempt=attempt,
        )

    async def latest_attempts(self, run_id: str) -> dict[str, AttemptRow]:
        """The attempt that counts now for each node key.

        ``list_attempts`` is ordered by node then attempt, so the last row seen
        for a key is its highest-numbered one — the one every status question
        about that node is really asking about.
        """
        latest: dict[str, AttemptRow] = {}
        for row in await self._attempts.list_attempts(run_id):
            current = latest.get(row.node_key)
            if current is None or row.attempt >= current.attempt:
                latest[row.node_key] = row
        return latest

    @staticmethod
    def attempts_used(latest: Mapping[str, AttemptRow]) -> dict[str, int]:
        """How many attempts each node has spent — what the ceiling counts."""
        return {key: row.attempt for key, row in latest.items()}

    @staticmethod
    def settled_keys(latest: Mapping[str, AttemptRow]) -> tuple[set[str], set[str]]:
        """``(completed, skipped)`` — what ``next_node`` treats as done.

        A failed node is in neither: whether the run walks past it is its
        ``on_failure`` behaviour's answer (FR-024), not the walk's.
        """
        completed = {k for k, row in latest.items() if row.status == NodeStatus.COMPLETED.value}
        skipped = {k for k, row in latest.items() if row.status == NodeStatus.SKIPPED.value}
        return completed, skipped
