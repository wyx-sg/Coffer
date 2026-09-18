"""/api/v1/audit — read-only query over the audit log."""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEntry
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_audit_service, get_resource_service
from coffer.surfaces.http.schemas import AuditEntryOut, AuditListOut

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["audit"],
    dependencies=[Depends(require_token)],
)

# Match a *trailing* tz offset that arrived space-mangled (because the browser
# encoded '+' as ' ' per x-www-form-urlencoded). Anchored at end-of-string with
# look-behind so it only fires on a real timezone offset, never on internal
# fractional-second whitespace (CODE-019). Pattern only matches when the prior
# chars look like a time (HH:MM:SS or HH:MM:SS.ffffff).
_TZ_SPACE_RE = re.compile(r"(\d{2}:\d{2}:\d{2}(?:\.\d+)?) (\d{2}:\d{2})$")


def _parse_since(raw: str | None) -> datetime | None:
    """Parse ``since`` as ISO-8601, repairing a space-mangled '+' tz offset.

    Browsers/x-www-form-urlencoded transports replace '+' with ' '; the regex
    flip handles that single edge case without losing strict parsing on
    everything else. Clients SHOULD url-encode '+' as ``%2B`` themselves.
    """
    if raw is None:
        return None
    fixed = _TZ_SPACE_RE.sub(r"\1+\2", raw)
    try:
        return datetime.fromisoformat(fixed)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid 'since' datetime: {exc}. "
                "Clients should url-encode '+' as '%2B' in tz offsets."
            ),
        ) from exc


def _to_out(e: AuditEntry) -> AuditEntryOut:
    return AuditEntryOut(
        id=e.id or 0,
        timestamp=e.timestamp,
        event_type=e.event_type,
        resource_kind=e.resource_kind,
        resource_name=e.resource_name,
        actor=e.actor,
        details=e.details,
    )


@router.get("", response_model=AuditListOut)
async def list_audit(
    kind: str | None = Query(default=None),
    resource_uid: str | None = Query(
        default=None,
        description=(
            "One resource's whole trail, including the rows written while it "
            "carried a different name. Filtering by name was removed with the "
            "identity change: it could not tell a renamed resource from a "
            "deleted one whose name was later reused, and rendered two "
            "objects' histories as one."
        ),
    ),
    event_type: str | None = Query(default=None),
    event_prefix: str | None = Query(default=None),
    since: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    svc: AuditService = Depends(get_audit_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> AuditListOut:
    since_dt = _parse_since(since)
    # 404 for an unknown uid rather than an empty list: "no such resource" and
    # "that resource has no events" are different answers and the caller acts
    # on them differently.
    resource = await resources.get(resource_uid) if resource_uid is not None else None
    entries = await svc.query(
        resource=resource,
        kind=kind,
        event_type=event_type,
        event_prefix=event_prefix,
        since=since_dt,
        limit=limit,
    )
    return AuditListOut(entries=[_to_out(e) for e in entries])
