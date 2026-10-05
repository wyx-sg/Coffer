# backend/coffer/surfaces/http/secret_notes_routes.py
"""/api/v1/secrets/notes and /api/v1/secrets/uses — what a person said about a
secret, and who used it (spec secret "Label and describe a secret without
changing its reference" and "Audit every use of a secret by who used it").

Neither returns a value. The notes are one vault state document keyed by ref;
the uses are read from the audit log's ``secret_resolved`` rows.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.secret.notes import SecretNotesPort
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.secrets import SecretNote
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service,
)
from coffer.surfaces.http.secret_composition import get_secret_store
from coffer.surfaces.http.secret_notes_wiring import get_secret_notes
from coffer.surfaces.http.secret_routes import _checked_ref
from coffer.surfaces.http.secret_schemas import SecretNotesIn, SecretNotesOut, SecretUseOut

router = APIRouter(
    prefix="/api/v1/secrets",
    tags=["secrets"],
    dependencies=[Depends(require_token)],
)


@router.put("/notes", response_model=SecretNotesOut)
async def put_notes(
    body: SecretNotesIn,
    store: Any = Depends(get_secret_store),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    notes: SecretNotesPort = Depends(get_secret_notes),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SecretNotesOut:
    """Set a ref's label and description (spec secret "Label and describe a
    secret without changing its reference"). A field left out stays, an empty
    one is removed; the ref must be stored or cited (else 404). Audited by ref
    and field names, never the text."""
    ref = _checked_ref(body.ref)
    if not await asyncio.to_thread(store.exists, ref) and not await resources.find_secret_citations(
        ref
    ):
        raise ResourceNotFound(f"no secret {ref!r}")
    fields = [f for f in ("label", "description") if getattr(body, f) is not None]

    def merge(current: SecretNote | None) -> SecretNote:
        current = current or SecretNote()
        return SecretNote(
            created_for=current.created_for,
            origin=current.origin,
            label=(body.label or None) if body.label is not None else current.label,
            description=(body.description or None)
            if body.description is not None
            else current.description,
        )

    stored: SecretNote | None
    if fields:
        stored = await asyncio.to_thread(
            notes.update, ref, merge, summary=f"describe secret {ref}", actor=actor
        )
        await audit.record(
            AuditEventType.SECRET_NOTES_UPDATED.value,
            actor=actor,
            details={"ref": ref, "fields": fields},
        )
    else:
        stored = await asyncio.to_thread(notes.get, ref)
    merged = stored or SecretNote()
    return SecretNotesOut(ref=ref, label=merged.label, description=merged.description)


@router.get("/uses", response_model=list[SecretUseOut])
async def list_uses(
    ref: str,
    limit: int = Query(20, ge=1, le=100),
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
) -> list[SecretUseOut]:
    """Who had this secret decrypted for use, newest first, read from the audit
    log's ``secret_resolved`` rows (a resource's destination, or a `coffer run`
    child). Never a value."""
    ref = _checked_ref(ref)
    page = await audit.page(event_type=AuditEventType.SECRET_RESOLVED.value, q=ref, limit=200)
    out: list[SecretUseOut] = []
    for e in page.items:
        d = e.details
        if d.get("ref") != ref:
            continue
        run = "destination_kind" not in d
        out.append(
            SecretUseOut(
                at=e.timestamp.isoformat(),
                actor=e.actor,
                destination_kind="run" if run else str(d["destination_kind"]),
                destination_uid=None if run else d.get("destination_uid"),
                destination_name=str(d.get("name") if run else d.get("destination_name", "")),
                slot=d.get("slot"),
                argv0=d.get("argv0"),
                cwd=d.get("cwd"),
            )
        )
        if len(out) == limit:
            break
    return out
