"""Find plaintext secrets in managed skills and MCP servers, and move them into the store.

Spec secret "Move plaintext secrets in managed resources into the store". Both
routes are open (no presence grant): neither returns a value, and a move only
puts a value the daemon already holds into the encrypted store and swaps a
reference in where it was.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.application.resource_service import ResourceService
from coffer.application.secret import plaintext_move
from coffer.application.secret.plaintext_move import Hit
from coffer.domain.audit import AuditEventType
from coffer.domain.secrets import LABEL_MAX, ORIGIN_DIALOG, ORIGIN_PAGE, SecretNote, secret_uri
from coffer.infrastructure.secret import plaintext_findings
from coffer.infrastructure.skill.master_store import default_master_root as skills_root
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_resource_service
from coffer.surfaces.http.secret_composition import get_secret_store
from coffer.surfaces.http.secret_notes_wiring import get_secret_notes
from coffer.surfaces.http.secret_schemas import (
    SecretImportIn,
    SecretImportMovedOut,
    SecretImportOut,
    SecretImportSkippedOut,
    SecretScanFindingOut,
    SecretScanOut,
)

router = APIRouter()

#: Skills Coffer renders itself: its guide quotes `coffer run --secret …` on purpose.
_COFFERS_OWN_SKILLS = frozenset({GUIDE_SKILL_NAME})


async def _hits(resources: ResourceService) -> tuple[list[Hit], int, int]:
    skill_hits, files = await asyncio.to_thread(
        plaintext_findings.scan_skills, skills_root(), _COFFERS_OWN_SKILLS
    )
    servers = await resources.list(kind="mcp_server")
    server_hits, checked = plaintext_findings.scan_servers(
        (r.uid, r.name, r.config) for r in servers
    )
    return skill_hits + server_hits, files, checked


def _finding_fields(h: Hit) -> dict[str, Any]:
    f = h.finding
    return {
        "id": f.id,
        "source": f.source,
        "resource": f.resource,
        "resource_uid": f.resource_uid,
        "path": f.path,
        "line": f.line,
        "field": f.field,
        "key": f.key,
        "proposed_name": f.proposed_name,
    }


@router.post("/scan", response_model=SecretScanOut)
async def scan_plaintext(
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> SecretScanOut:
    """Plaintext secrets in the skill master store and in MCP servers' env / headers."""
    hits, files, servers = await _hits(resources)
    return SecretScanOut(
        findings=[SecretScanFindingOut(**_finding_fields(h)) for h in hits],
        files_checked=files,
        servers_checked=servers,
    )


@router.post("/import", response_model=SecretImportOut)
async def import_plaintext(
    body: SecretImportIn,
    store: Any = Depends(get_secret_store),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SecretImportOut:
    """Move plaintext findings into the store, replacing each with its reference."""
    hits, _, _ = await _hits(resources)

    async def update_config(uid: str, config: dict[str, Any]) -> object:
        return await resources.update_config(uid, config, actor)

    notes = get_secret_notes()

    def set_note(ref: str, note: SecretNote) -> None:
        label = note.label[:LABEL_MAX] if note.label else None
        notes.put(
            ref,
            SecretNote(
                label=label,
                created_for=note.created_for,
                origin=ORIGIN_DIALOG if note.created_for else ORIGIN_PAGE,
            ),
            summary=f"describe secret {ref}",
            actor=actor,
        )

    result = await plaintext_move.move(
        hits,
        body.ids,
        store=store,
        rewrite=plaintext_findings.rewrite_file,
        update_config=update_config,
        set_note=set_note,
        dry_run=body.dry_run,
    )
    for details in result.stored:
        await audit.record(AuditEventType.SECRET_IMPORTED.value, actor=actor, details=details)
    return SecretImportOut(
        moved=[
            SecretImportMovedOut(
                id=m.id,
                source=m.source,  # type: ignore[arg-type]
                resource=m.resource,
                name=m.name,
                ref=m.ref,
                label=m.label,
                uri=secret_uri(m.name) if m.name else None,
            )
            for m in result.moved
        ],
        skipped=[
            SecretImportSkippedOut(
                id=s.id,
                source=s.source,  # type: ignore[arg-type]
                resource=s.resource,
                reason=s.reason,
                name=s.name,
                stored=s.stored,
            )
            for s in result.skipped
        ],
        dry_run=result.dry_run,
    )
