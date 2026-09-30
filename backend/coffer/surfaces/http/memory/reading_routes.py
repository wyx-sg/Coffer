"""``GET /api/v1/memory/reading`` — when Coffer last read the agents' memory,
and whose it could not (spec memory "Report the last read of the agents'
memory").

What the Memory page's header reads: "Read 14 min ago", and "· 1 agent
failed" with a banner when the last read left an agent's memory unread. The
answer comes from the audit log (``application.memory.reading``), so it is the
same whether the timer, Update memory or ``coffer memory sync`` did the read.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from coffer.application.audit_service import AuditService
from coffer.application.memory.reading import last_reading
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_audit_service

router = APIRouter(
    prefix="/api/v1/memory",
    tags=["memory"],
    dependencies=[Depends(require_token)],
)


class ReadFailureOut(BaseModel):
    """One agent's memory the last read could not parse."""

    agent: str = Field(description="The agent's resource name; empty when not recorded.")
    path: str = Field(description="The native source that would not parse.")
    reason: str = Field(description="Why it would not parse.")
    last_read_at: datetime | None = Field(
        default=None,
        description="When that agent's memory was last read with nothing failing, if known. "
        "Its memories stay as that read left them.",
    )


class ReadingOut(BaseModel):
    """The last read of the agents' memory."""

    read_at: datetime | None = Field(
        default=None, description="When the last read finished; null before the first."
    )
    failures: list[ReadFailureOut] = Field(default_factory=list)


@router.get("/reading", response_model=ReadingOut)
async def reading(
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> ReadingOut:
    found = await last_reading(audit)
    return ReadingOut(
        read_at=found.read_at,
        failures=[
            ReadFailureOut(agent=f.agent, path=f.path, reason=f.reason, last_read_at=f.last_read_at)
            for f in found.failures
        ],
    )
