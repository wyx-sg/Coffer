"""/api/v1/skills/* — skill manager HTTP routes (spec skill-manager)."""

from __future__ import annotations

import pathlib
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, Field

from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.skill import drift_view
from coffer.application.skill.builtin_seed import is_builtin
from coffer.application.skill.service import SkillService
from coffer.application.skill.source_service import SkillSourceService
from coffer.domain.resource import Resource
from coffer.domain.skill.binding import BindingState, LinkMode
from coffer.domain.skill.config import SkillConfig
from coffer.domain.skill.drift import DriftEntry, DriftKind
from coffer.domain.skill.requirements import requirements_from_skill_md
from coffer.domain.skill.source import (
    ArchiveImportSource,
    BuiltinSource,
    GitImportSource,
    LocalImportSource,
)
from coffer.domain.skill.source_status import SourceStatus
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.reconcile_dependencies import get_reconciler
from coffer.surfaces.http.schemas import ScopeOut
from coffer.surfaces.http.skill_dependencies import (
    get_optional_skill_source_service,
    get_skill_service,
)
from coffer.surfaces.http.skill_source_schemas import (
    ArchiveImportSourceOut,
    GitImportSourceOut,
    SkillRequirementOut,
    SkillSourceStatusOut,
    archive_source_out,
    git_source_out,
    requirement_out,
    status_out,
)

router = APIRouter(
    prefix="/api/v1/skills",
    tags=["skills"],
    dependencies=[Depends(require_token)],
)


# ---------- request schemas ----------


class SkillImportRequest(BaseModel):
    path: str = Field(min_length=1)
    overwrite: bool = False


# ---------- response schemas ----------


class SkillBindingOut(BaseModel):
    """One agent currently holding a delivered copy of this skill.

    Internal delivery bookkeeping surfaced read-only: there is no per-binding
    toggle any more, so a row here simply means "delivered". Which agents get a
    row is decided by ``SkillOut.enabled`` + ``SkillOut.scope``.

    Both halves of the agent's identity ride along: ``agent_uid`` is what a
    client follows to that agent, ``agent_name`` is what it prints. A delivery
    is a fact about an agent row, so it keeps pointing at the same agent when
    the user renames it (ADR resource-identity-is-an-immutable-uid).
    """

    agent_uid: str
    agent_name: str
    last_linked_at: datetime | None = None
    last_link_path: str | None = None
    link_mode: LinkMode | None = None


class LocalImportSourceOut(BaseModel):
    """A skill copied in from a folder on disk; the path is informational."""

    type: Literal["local_import"]
    original_path: str


class BuiltinSourceOut(BaseModel):
    """Coffer generated this skill. It carries no provenance fields at all:
    the master folder is rewritten from the running build at every start."""

    type: Literal["builtin"]


SkillSourceOut = Annotated[
    LocalImportSourceOut | ArchiveImportSourceOut | GitImportSourceOut | BuiltinSourceOut,
    Field(discriminator="type"),
]


def _source_out(
    source: LocalImportSource | ArchiveImportSource | GitImportSource | BuiltinSource,
) -> LocalImportSourceOut | ArchiveImportSourceOut | GitImportSourceOut | BuiltinSourceOut:
    if isinstance(source, LocalImportSource):
        return LocalImportSourceOut(type="local_import", original_path=source.original_path)
    if isinstance(source, ArchiveImportSource):
        return archive_source_out(source)
    if isinstance(source, GitImportSource):
        return git_source_out(source)
    return BuiltinSourceOut(type="builtin")


class SkillOut(BaseModel):
    # Identity first, label second — ``/api/v1/skills/{uid}`` is what every
    # other route here takes (ADR resource-identity-is-an-immutable-uid).
    uid: str
    #: Fixed once registered: the master folder, the delivered links and the
    #: SKILL.md ``name:`` all carry it (409 NAME_IMMUTABLE on a change).
    name: str
    description: str
    source: SkillSourceOut
    # Coffer's own: the folder is rewritten from the running build at every
    # boot, so deleting it is refused (409 RESOURCE_PROTECTED) while enabling,
    # disabling and narrowing its scope stay the owner's to decide. The surface
    # carries it as its own flag rather than making every reader re-derive it
    # from ``source["type"]``.
    builtin: bool
    # The two halves of the delivery predicate: a skill reaches an agent iff
    # ``enabled`` and that agent is inside ``scope``
    # (None = every agent; [] matches nothing).
    enabled: bool
    scope: ScopeOut | None
    version_hash: str
    master_path: str
    last_synced_from_source_at: datetime | None
    created_at: datetime
    updated_at: datetime
    bindings: list[SkillBindingOut]
    #: The commands its SKILL.md declares it needs, read from the master folder
    #: on each request (spec skill-manager "Show the commands a skill declares
    #: it needs").
    requires: list[SkillRequirementOut]
    #: A Git-imported skill's last update check on this machine; null for
    #: every other source.
    source_status: SkillSourceStatusOut | None


class SkillListOut(BaseModel):
    items: list[SkillOut]


class DriftEntryOut(BaseModel):
    """One disagreement between what Coffer delivered and what is on disk.

    By NAME, and deliberately so even now that ``DriftEntry`` carries uids:
    an entry is a finding about a PATH in a workspace, and two of the five
    kinds (``missing_master``, ``orphan_master``) are precisely the case where
    no resource stands behind the name — there would be nothing to put in a uid
    field. The report is read and acted on as a whole through
    ``POST /skills/repair``, never used to address one resource, so a uid here
    would be an identity nobody follows. The uids on the domain entry exist for
    the repair pass, which re-delivers against them so a skill renamed between
    verify and repair is still the skill that gets repaired; that is an
    internal guarantee, not a field of this report.
    """

    skill_name: str
    agent_name: str
    kind: DriftKind
    target_path: str
    suggested_remedy: str


class DriftReportOut(BaseModel):
    entries: list[DriftEntryOut]


class RepairReportOut(BaseModel):
    remediated: list[DriftEntryOut]
    remaining: DriftReportOut


# The skill master-folder viewer/editor schemas + routes live in
# ``skill_file_routes.py`` (split out for the component size cap).


# ---------- helpers ----------


def _actor(x_coffer_actor: str | None = Header(default=None)) -> str:
    return x_coffer_actor or "api"


# There is no surface-level name guard here any more. It existed because a
# skill's NAME was the URL path segment and also its folder name under
# ``~/.coffer/vault/skills/<name>/``, so a traversal attempt (``..``, ``/``, ``\``)
# arriving in the path had to be refused before it reached the filesystem. The
# path segment is now a uid the daemon minted, and a name only ever enters
# through ``ResourceService``, which validates it once for every kind
# (ADR resource-identity-is-an-immutable-uid). A second copy of that rule here
# would be a rule nothing can violate, kept alive for a route shape that is
# gone.


async def _agents_by_uid(svc: SkillService) -> dict[str, Resource]:
    """Build an agent-uid -> agent map once per request (avoids an N+1)."""
    return {a.uid: a for a in await svc.list_agents()}


def _drift_out(e: DriftEntry) -> DriftEntryOut:
    """One drift entry on the wire — used by both verify and repair."""
    return DriftEntryOut(
        skill_name=e.skill_name,
        agent_name=e.agent_name,
        kind=e.kind,
        target_path=e.target_path,
        suggested_remedy=e.suggested_remedy,
    )


def _requires(svc: SkillService, name: str) -> list[SkillRequirementOut]:
    try:
        text = (pathlib.Path(svc.master_path(name)) / "SKILL.md").read_text("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    return [requirement_out(q) for q in requirements_from_skill_md(text).requirements]


async def _to_skill_out(
    svc: SkillService,
    r: Resource,
    agents_by_uid: dict[str, Resource],
    *,
    bindings_by_skill: dict[str, list[BindingState]] | None = None,
    sources: SkillSourceService | None = None,
    statuses: dict[str, SourceStatus] | None = None,
) -> SkillOut:
    cfg = SkillConfig.model_validate(r.config)
    source_status: SkillSourceStatusOut | None = None
    if isinstance(cfg.source, GitImportSource):
        if statuses is not None:
            status = statuses.get(r.uid)
        else:
            status = await sources.status(r) if sources is not None else None
        source_status = status_out(status, cfg.source.commit)
    # Single-skill handlers (get / import) take the per-skill round-trip —
    # list handlers prebuild the map once via
    # ``svc.bindings_grouped_by_skill()`` to collapse N queries into 1.
    if bindings_by_skill is not None:
        bindings = bindings_by_skill.get(r.uid, [])
    else:
        bindings = await svc.bindings_for(r.uid)
    return SkillOut(
        uid=r.uid,
        name=r.name,
        description=cfg.skill_md_description,
        source=_source_out(cfg.source),
        builtin=is_builtin(r.config),
        enabled=r.enabled,
        scope=ScopeOut.of(r.scope),
        version_hash=cfg.version_hash,
        master_path=svc.master_path(r.name),
        last_synced_from_source_at=cfg.last_synced_from_source_at,
        created_at=r.created_at,
        updated_at=r.updated_at,
        # Only live deliveries: a spent binding row (reclaimed copy) is
        # bookkeeping, not something the agent holds.
        bindings=[_binding_out(b, agents_by_uid) for b in bindings if b.enabled],
        requires=_requires(svc, r.name),
        source_status=source_status,
    )


def _binding_out(b: BindingState, agents_by_uid: dict[str, Resource]) -> SkillBindingOut:
    """One delivery row on the wire.

    A binding whose agent row has gone is still reported, because the row is
    evidence that a copy was delivered somewhere and dropping it would make the
    delivery list quietly shorter than the truth. It is rendered with the
    agent's uid in both fields, which is what the binding still holds.
    """
    agent = agents_by_uid.get(b.agent_uid)
    fallback = b.agent_uid
    return SkillBindingOut(
        agent_uid=agent.uid if agent else fallback,
        agent_name=agent.name if agent else fallback,
        last_linked_at=b.last_linked_at,
        last_link_path=b.last_link_path,
        link_mode=b.link_mode,
    )


# ---------- routes ----------


@router.get("", response_model=SkillListOut)
async def list_skills(
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService | None = Depends(get_optional_skill_source_service),  # noqa: B008
) -> SkillListOut:
    rs = await svc.list_skills()
    agents_by_uid = await _agents_by_uid(svc)
    # Prebuild the binding lookup once — collapses what was a 2N+2 query
    # pattern (one ``list_for_skill`` + one ``get`` per skill) into ~3.
    bindings_by_skill = await svc.bindings_grouped_by_skill()
    statuses = await sources.statuses() if sources is not None else {}
    items = [
        await _to_skill_out(
            svc, r, agents_by_uid, bindings_by_skill=bindings_by_skill, statuses=statuses
        )
        for r in rs
    ]
    return SkillListOut(items=items)


@router.post("/import", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def import_skill(
    body: SkillImportRequest,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> SkillOut:
    r = await svc.import_local(path=body.path, actor=actor, overwrite=body.overwrite)
    return await _to_skill_out(svc, r, await _agents_by_uid(svc))


@router.get("/{uid}", response_model=SkillOut)
async def get_skill(
    uid: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    sources: SkillSourceService | None = Depends(get_optional_skill_source_service),  # noqa: B008
) -> SkillOut:
    r = await svc.get_skill(uid)
    return await _to_skill_out(svc, r, await _agents_by_uid(svc), sources=sources)


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_skill(
    uid: str,
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    actor: str = Depends(_actor),
) -> Response:
    await svc.remove(uid=uid, actor=actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/verify", response_model=DriftReportOut)
async def verify_skills(
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    reconciler: Reconciler = Depends(get_reconciler),  # noqa: B008
) -> DriftReportOut:
    # The ``skill_link`` target's dry-run plan, read as a drift report.
    report = await drift_view.verify(svc, reconciler)
    return DriftReportOut(entries=[_drift_out(e) for e in report.entries])


@router.post("/repair", response_model=RepairReportOut)
async def repair_skills(
    svc: SkillService = Depends(get_skill_service),  # noqa: B008
    reconciler: Reconciler = Depends(get_reconciler),  # noqa: B008
    actor: str = Depends(_actor),
) -> RepairReportOut:
    # The plan's repairable drift, applied through the reconciler.
    result = await drift_view.repair(svc, reconciler, actor=actor)
    return RepairReportOut(
        remediated=[_drift_out(e) for e in result.remediated],
        remaining=DriftReportOut(entries=[_drift_out(e) for e in result.remaining.entries]),
    )
