"""``/api/v1/settings/call-content`` — whether calls record their content.

Spec mcp-gateway "Switch call content recording per machine": the setting is
kept in ``daemon-config.json`` and held by ``call_content``; a change applies
to the next call in every session, and is audited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from coffer.application.audit_service import AuditService
from coffer.application.mcp import call_content
from coffer.application.mcp.call_content import CallContentRecording
from coffer.domain.audit import AuditEventType
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor, get_audit_service
from coffer.surfaces.http.log_schemas import CallContentSettingIn, CallContentSettingOut

router = APIRouter(
    prefix="/api/v1/settings",
    tags=["settings"],
    dependencies=[Depends(require_token)],
)


def get_call_content_recording() -> CallContentRecording:
    recording = call_content.current()
    if recording is None:
        raise HTTPException(status_code=503, detail="call content setting not initialised")
    return recording


@router.get("/call-content", response_model=CallContentSettingOut)
async def get_call_content(
    recording: CallContentRecording = Depends(get_call_content_recording),  # noqa: B008
) -> CallContentSettingOut:
    """Whether calls record their arguments and results on this machine."""
    return CallContentSettingOut(enabled=recording.enabled)


@router.put("/call-content", response_model=CallContentSettingOut)
async def put_call_content(
    body: CallContentSettingIn,
    recording: CallContentRecording = Depends(get_call_content_recording),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> CallContentSettingOut:
    """Switch recording; the file is written before the answer, and the change audited."""
    before = recording.set(body.enabled)
    if before != body.enabled:
        await audit.record(
            AuditEventType.CALL_CONTENT_RECORDING_UPDATED.value,
            actor=actor,
            details={"from": before, "to": body.enabled},
        )
    return CallContentSettingOut(enabled=recording.enabled)
