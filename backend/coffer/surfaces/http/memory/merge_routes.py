"""Merge-scan + merge routes (spec 007 amendment 2026-07-10, FR-056-059).

Registered on the shared memory ``router`` (like ``lane_routes.py``). The
route paths are literal collection-level segments (``/merge_scan``,
``/merge``) — they cannot collide with ``/{name}`` because store names are
validated to ``global`` / ``project-<ULID>`` shapes everywhere else.
"""

from __future__ import annotations

from fastapi import Depends
from pydantic import BaseModel, Field

from coffer.application.memory.merge import MergeProposal, StoreMergeService
from coffer.application.memory.merge_prompt import StoreEvidence
from coffer.domain.errors import MemoryStoreNotFound, ResourceNotFound
from coffer.domain.memory.fact import Actor
from coffer.surfaces.http.memory.merge_state import get_merge_service
from coffer.surfaces.http.memory.routes import _actor, router

# --- wire shapes (contracts/api.openapi.yaml) --------------------------------


class StoreEvidenceOut(BaseModel):
    store: str
    label: str | None = None
    root: str | None = None
    remote: str | None = None
    facts: int

    @classmethod
    def from_evidence(cls, e: StoreEvidence) -> StoreEvidenceOut:
        return cls(store=e.store, label=e.label, root=e.root, remote=e.remote, facts=e.facts)


class MergeProposalOut(BaseModel):
    source: str
    target: str
    confidence: str
    judged_by: str
    reason: str
    source_evidence: StoreEvidenceOut
    target_evidence: StoreEvidenceOut

    @classmethod
    def from_proposal(cls, p: MergeProposal) -> MergeProposalOut:
        return cls(
            source=p.source,
            target=p.target,
            confidence=p.confidence,
            judged_by=p.judged_by,
            reason=p.reason,
            source_evidence=StoreEvidenceOut.from_evidence(p.source_evidence),
            target_evidence=StoreEvidenceOut.from_evidence(p.target_evidence),
        )


class MergeScanOut(BaseModel):
    engine: str
    truncated: bool
    proposals: list[MergeProposalOut]


class MergeIn(BaseModel):
    source: str
    target: str
    organize: bool = Field(default=True)


class MergeOut(BaseModel):
    target: str
    merged_files: int
    label_moved: bool
    root_moved: bool
    aliases: list[str]
    reorg_status: str


# --- routes -------------------------------------------------------------------


@router.post("/merge_scan", response_model=MergeScanOut)
async def merge_scan(
    svc: StoreMergeService = Depends(get_merge_service),  # noqa: B008
) -> MergeScanOut:
    """Propose same-project store pairs (FR-056). Read-only."""
    result = await svc.scan()
    return MergeScanOut(
        engine=result.engine,
        truncated=result.truncated,
        proposals=[MergeProposalOut.from_proposal(p) for p in result.proposals],
    )


@router.post("/merge", response_model=MergeOut)
async def merge_stores(
    body: MergeIn,
    svc: StoreMergeService = Depends(get_merge_service),  # noqa: B008
    actor: Actor = Depends(_actor),  # noqa: B008
) -> MergeOut:
    """Merge one project store into another (FR-057/FR-058/FR-059)."""
    try:
        result = await svc.merge(
            source=body.source, target=body.target, organize=body.organize, actor=actor
        )
    except ResourceNotFound as exc:
        raise MemoryStoreNotFound(exc.name) from exc
    return MergeOut(
        target=result.outcome.target,
        merged_files=result.outcome.merged_files,
        label_moved=result.outcome.label_moved,
        root_moved=result.outcome.root_moved,
        aliases=result.outcome.aliases,
        reorg_status=result.reorg_status,
    )
