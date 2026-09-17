"""``/api/v1/upkeep/*`` — what this daemon is rewriting right now.

One route, and deliberately only one: ``GET /upkeep/runs`` answers for
everything in flight at once rather than making each kind grow a near-identical
"is my pass running?" endpoint of its own.

That shape follows what the fact is. A pass is not a property of a partition or
of a collection; it is a property of the daemon, which is running some set of
them and can name the set in one read (``application.upkeep_runs``). Coffer
already keeps its cross-kind facts in cross-kind families for the same reason —
``/api/v1/resources``, ``/api/v1/audit``, ``/api/v1/retention`` — so a second
per-kind pair would have split one table across two surfaces and left every new
kind to remember to add a third.

The list is the whole answer: a target NOT named here has no pass running. A
caller asking about one partition or one collection filters the list; it never
needs a lookup route, and it gets the rest of the picture for free.

Read-only. A pass is started by the kind's own route (``POST
/api/v1/memory/partitions/{name}/organise``, ``POST
/api/v1/knowledge/collections/{name}/curate``), each of which refuses a second
concurrent pass over the same target with ``UPKEEP_ALREADY_RUNNING`` (409).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.application.upkeep_runs import UPKEEP_RUNS
from coffer.surfaces.http.auth import require_token

router = APIRouter(
    prefix="/api/v1/upkeep",
    tags=["upkeep"],
    dependencies=[Depends(require_token)],
)


class UpkeepRunOut(BaseModel):
    """One pass in flight."""

    kind: str = Field(description="The kind whose pass this is: `memory` or `knowledge`.")
    name: str = Field(description="The partition or collection being rewritten.")
    started_at: datetime = Field(description="When this daemon started the pass.")


class UpkeepRunListOut(BaseModel):
    """Every pass in flight, oldest first. Empty means nothing is running."""

    runs: list[UpkeepRunOut]


@router.get("/runs", response_model=UpkeepRunListOut)
async def list_runs() -> UpkeepRunListOut:
    return UpkeepRunListOut(
        runs=[
            UpkeepRunOut(kind=run.kind, name=run.name, started_at=run.started_at)
            for run in UPKEEP_RUNS.list_running()
        ]
    )
