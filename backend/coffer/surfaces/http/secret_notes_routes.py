# backend/coffer/surfaces/http/secret_notes_routes.py
"""/api/v1/secrets/notes — what a person said about a secret (spec secret
"Label and describe a secret without changing its reference").

It returns no value. The notes are one vault state document keyed by ref.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

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
from coffer.surfaces.http.secret_schemas import SecretNotesIn, SecretNotesOut

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
