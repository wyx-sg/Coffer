"""The engine's rows, rendered as the wire models in ``schemas``.

Split out of ``schemas`` so that the five route modules render a row one way
rather than five, and because the two halves answer different questions: the
models say what the contract promises, and these say how a row satisfies it.

Every one of them takes a structural row Protocol from
``application.workflow.ports``, never an ORM class — the surface reads rows, it
does not know what wrote them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from coffer.application.workflow.commands import parse_snapshot
from coffer.application.workflow.ports import (
    ApprovalRow,
    ArtifactEntry,
    AttemptRow,
    EventRow,
    RunRow,
)
from coffer.domain.workflow.errors import TemplateInvalid
from coffer.domain.workflow.events import ActorKind, EventActor
from coffer.domain.workflow.links import classify_link
from coffer.domain.workflow.run import RunInput as RunInputValue
from coffer.domain.workflow.run import RunInputKind
from coffer.domain.workflow.template import WorkflowTemplate
from coffer.surfaces.http.workflow.schemas import (
    ApprovalOut,
    ArtifactOut,
    EventActorOut,
    EventOut,
    NodeAttemptOut,
    RunInput,
    RunOut,
)

#: ``X-Coffer-Actor``'s value when the caller did not name themselves
#: (``surfaces.http.dependencies.get_actor``). It names the surface, not a
#: person, so it is not carried into the event log as an ``actor_id``.
_ANONYMOUS_ACTOR = "api"


def event_actor(actor: str) -> EventActor:
    """Who the event log attributes a command from this surface to.

    The kind is always ``user``: every route in this package is a person (or
    their CLI) asking for something. The engine's own moves are attributed by
    the engine, with its own actors.
    """
    return EventActor(
        actor_kind=ActorKind.USER,
        actor_id=None if actor == _ANONYMOUS_ACTOR else actor,
        source_surface="api",
    )


def _frozen(run: RunRow) -> WorkflowTemplate | None:
    """The template this run froze (FR-010), or ``None`` if it no longer parses.

    ``None`` rather than raising: refusing to show a run over a snapshot this
    build cannot read would hide the very run whose template is broken.
    """
    try:
        return parse_snapshot(run.template_snapshot)
    except (TemplateInvalid, ValueError, TypeError):
        return None


def _stage_name(template: WorkflowTemplate | None, stage_key: str | None) -> str | None:
    """What the developer CALLED the stage a run is at.

    A key is an identity the engine reads no meaning from and the developer
    never typed (FR-003, FR-060), so a list that printed one would be showing
    them a name they did not choose. Read from the run's own frozen snapshot,
    which is the only place that still knows what the stage was called when
    this run started.
    """
    if template is None or stage_key is None:
        return None
    stage = template.stage(stage_key)
    return None if stage is None else stage.name


def run_out(run: RunRow, *, owned_here: bool) -> RunOut:
    """One run row on the wire. ``owned_here`` comes from the run service."""
    frozen = _frozen(run)
    return RunOut(
        id=run.id,
        title=run.title,
        # Required and non-nullable on the wire: a run always executes a
        # template, and the column is nullable only because a deleted resource
        # must not cascade into the run that froze it.
        template_ref=run.template_ref or "",
        status=run.status,
        version=run.version,
        workdir=run.workdir,
        machine_id=run.machine_id,
        owned_here=owned_here,
        current_stage_key=run.current_stage_key,
        current_stage_name=_stage_name(frozen, run.current_stage_key),
        current_node_key=run.current_node_key,
        tokens_spent=run.tokens_spent,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def inputs_out(items: Iterable[Mapping[str, Any]]) -> list[RunInput]:
    """Mounted inputs, as the ``inputs`` JSON column holds them.

    Takes the entries rather than the run, because the same rendering serves
    two callers: a run's detail, which reads the column off the row it already
    has, and the four ``/inputs`` routes, which are handed the list the store
    wrote. An entry missing ``kind`` or ``ref`` is skipped rather than raised
    on — a malformed row should not make the run unreadable.
    """
    out: list[RunInput] = []
    for item in items:
        kind = item.get("kind")
        ref = item.get("ref")
        if not isinstance(kind, str) or not isinstance(ref, str):
            continue
        label = item.get("label")
        size = item.get("size")
        path = item.get("path")
        mount = item.get("mount")
        out.append(
            RunInput(
                kind=RunInputKind(kind),
                ref=ref,
                label=label if isinstance(label, str) else None,
                size=size if isinstance(size, int) else None,
                path=path if isinstance(path, str) else None,
                mount=mount if isinstance(mount, str) else None,
                provider=_provider_of(RunInputKind(kind), ref),
            )
        )
    return out


def _provider_of(kind: RunInputKind, ref: str) -> str | None:
    """What a link points at, derived on every read (FR-065).

    Derived and not stored, so a link mounted before its provider was
    recognisable becomes recognisable the moment the table grows — no
    migration, and nothing on disk to go stale. Only a link has one: a
    collection, a file and a repository are already named by their kind.
    """
    return classify_link(ref) if kind is RunInputKind.LINK else None


def mounted_out(items: Iterable[RunInputValue]) -> list[RunInput]:
    """Mounted inputs as ``WorkflowInputsService`` answers with them.

    The sibling above renders the raw JSON column, which is what a run's detail
    has in hand; this renders the value objects, which is what the four
    ``/inputs`` routes get back. Two functions rather than one that guesses:
    each side has exactly one shape, and a converter that sniffed would be
    wrong about a mapping that happened to have attributes.
    """
    return [
        RunInput(
            kind=item.kind,
            ref=item.ref,
            label=item.label,
            size=item.size,
            path=getattr(item, "path", None),
            mount=getattr(item, "mount", None),
            provider=_provider_of(item.kind, item.ref),
        )
        for item in items
    ]


def attempt_out(row: AttemptRow) -> NodeAttemptOut:
    return NodeAttemptOut(
        id=row.id,
        node_key=row.node_key,
        stage_key=row.stage_key,
        attempt=row.attempt,
        status=row.status,
        conversation_id=row.conversation_id,
        summary=row.summary,
        failure_reason=row.failure_reason,
        instructions=row.instructions,
        tokens=row.tokens,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def event_out(row: EventRow) -> EventOut:
    actor = row.actor or {}
    return EventOut(
        id=row.id,
        sequence=row.sequence,
        event_type=row.event_type,
        actor=EventActorOut(
            actor_kind=str(actor.get("actor_kind", "system")),
            actor_id=_optional_str(actor.get("actor_id")),
            source_surface=str(actor.get("source_surface", "")),
        ),
        stage_key=row.stage_key,
        node_key=row.node_key,
        payload=dict(row.payload or {}),
        created_at=row.created_at,
    )


def artifact_out(entry: ArtifactEntry) -> ArtifactOut:
    return ArtifactOut(
        name=entry.name,
        node_key=entry.node_key,
        attempt=entry.attempt,
        path=entry.path,
        size=entry.size,
        modified_at=entry.modified_at,
    )


def approval_out(row: ApprovalRow) -> ApprovalOut:
    return ApprovalOut(
        id=row.id,
        run_id=row.run_id,
        attempt_id=row.attempt_id,
        kind=row.kind,
        tool_name=row.tool_name,
        status=row.status,
        payload=dict(row.payload or {}),
        decided_by=row.decided_by,
        decided_surface=row.decided_surface,
        comment=row.comment,
        expires_at=row.expires_at,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
