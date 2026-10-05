"""Find plaintext secrets in managed skills and MCP servers, and move them into the store.

Spec secret "Move plaintext secrets in managed resources into the store". Both
routes are open (no presence grant): neither returns a value, and a move only
puts a value the daemon already holds into the encrypted store and swaps a
reference in where it was.
"""

from __future__ import annotations

import asyncio
import pathlib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.application.resource_service import ResourceService
from coffer.application.secret import plaintext_move
from coffer.application.secret.plaintext_ignore import IgnoredValue, fingerprinter
from coffer.application.secret.plaintext_move import Hit
from coffer.domain.audit import AuditEventType
from coffer.domain.secret_errors import SecretLocked
from coffer.domain.secrets import LABEL_MAX, ORIGIN_DIALOG, ORIGIN_PAGE, SecretNote, secret_uri
from coffer.infrastructure.secret import plaintext_findings
from coffer.infrastructure.secret.plaintext_ignore_store import JsonPlaintextIgnores
from coffer.infrastructure.skill.master_store import default_master_root as skills_root
from coffer.infrastructure.vault.home import vault_root
from coffer.surfaces.http.dependencies import get_actor, get_audit_service, get_resource_service
from coffer.surfaces.http.secret_composition import get_master_key_manager, get_secret_store
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


class SecretIgnoreIn(BaseModel):
    #: Finding ids to remember (or forget) as not secrets.
    ids: list[str]


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
        "rule": f.rule,
    }


def _place(h: Hit) -> str:
    """Where a value was found: a skill file relative to the vault, or the server's slot."""
    f = h.finding
    if f.source == "skill":
        path = pathlib.Path(f.path or "")
        try:
            return path.relative_to(vault_root()).as_posix()
        except ValueError:
            return path.as_posix()
    return f"mcp_server/{f.resource}/{f.field}"


def _fingerprint_of() -> Any:
    return fingerprinter(lambda: get_master_key_manager().current)


async def _scan_out(resources: ResourceService) -> SecretScanOut:
    hits, files, servers = await _hits(resources)
    of = _fingerprint_of()
    ignored = await asyncio.to_thread(JsonPlaintextIgnores().fingerprints)
    out: list[SecretScanFindingOut] = []
    for h in hits:
        fields = _finding_fields(h)
        fields["ignored"] = bool(ignored) and of(h.value) in ignored
        out.append(SecretScanFindingOut(**fields))
    return SecretScanOut(findings=out, files_checked=files, servers_checked=servers)


@router.post("/scan", response_model=SecretScanOut)
async def scan_plaintext(
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> SecretScanOut:
    """Plaintext secrets in the skill master store and in MCP servers' env / headers."""
    return await _scan_out(resources)


async def _chosen(resources: ResourceService, ids: list[str]) -> list[tuple[Hit, str]]:
    """The findings named by ``ids`` with their fingerprints; locked without a master key."""
    of = _fingerprint_of()
    wanted = set(ids)
    hits, _, _ = await _hits(resources)
    chosen = [h for h in hits if h.finding.id in wanted]
    pairs: list[tuple[Hit, str]] = []
    for h in chosen:
        fp = of(h.value)
        if fp is None:
            raise SecretLocked("the master key is not available")
        pairs.append((h, fp))
    if not chosen and of("") is None:
        raise SecretLocked("the master key is not available")
    return pairs


@router.post("/scan/ignore", response_model=SecretScanOut)
async def ignore_plaintext(
    body: SecretIgnoreIn,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SecretScanOut:
    """Remember the chosen values as not secrets: scans keep listing them, marked."""
    pairs = await _chosen(resources, body.ids)
    now = datetime.now(UTC).isoformat()
    entries = [
        IgnoredValue(
            fingerprint=fp,
            rule=h.finding.rule,
            place=_place(h),
            key=h.finding.key,
            actor=actor,
            ignored_at=now,
        )
        for h, fp in pairs
    ]
    await asyncio.to_thread(JsonPlaintextIgnores().add, entries)
    if entries:
        await audit.record(
            AuditEventType.SECRET_PLAINTEXT_IGNORED.value,
            actor=actor,
            details={"places": [f"{e.place}:{e.rule}" for e in entries]},
        )
    return await _scan_out(resources)


@router.post("/scan/unignore", response_model=SecretScanOut)
async def unignore_plaintext(
    body: SecretIgnoreIn,
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> SecretScanOut:
    """Report the chosen values again."""
    pairs = await _chosen(resources, body.ids)
    await asyncio.to_thread(JsonPlaintextIgnores().remove, [fp for _, fp in pairs])
    if pairs:
        await audit.record(
            AuditEventType.SECRET_PLAINTEXT_UNIGNORED.value,
            actor=actor,
            details={"places": [f"{_place(h)}:{h.finding.rule}" for h, _ in pairs]},
        )
    return await _scan_out(resources)


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
