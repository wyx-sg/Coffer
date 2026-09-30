# backend/coffer/surfaces/http/secret_routes.py
"""/api/v1/secrets — read and write secrets in the encrypted secret store.

Secrets are Fernet-encrypted into one file per ref; only ciphertext is persisted;
audit rows carry the ref only — secret values never appear in the audit log.

The UI uses this when importing MCP server JSON: any plaintext secret in the
pasted `env` is lifted into the secret store here, so it never lands in
Coffer's resource config unencrypted — the resource config only keeps a
secret ref.

Every lifecycle change is audited (spec resource-framework "Audit every lifecycle
change"). The audit row records the `ref` only — secret values never appear in
the audit log.

No route here returns a value (spec secret "Return no plaintext on any
route, command or tool"). A value leaves the daemon only through the
presence-gated reveal in ``secret_boundary_routes``, for the desktop app.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import SecretInUse
from coffer.domain.resource import Resource
from coffer.domain.secrets import secret_uri, standalone_name
from coffer.infrastructure.secret.plaintext_scan import skills_citing_secrets
from coffer.infrastructure.skill.master_store import default_master_root as skills_root
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service,
)
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.schemas import (
    SecretBindingOut,
    SecretCiterOut,
    SecretExistsOut,
    SecretListOut,
    SecretRefOut,
    SecretSetIn,
)
from coffer.surfaces.http.secret_boundary_wiring import approval_out, get_secret_boundary
from coffer.surfaces.http.secret_composition import get_secret_store
from coffer.surfaces.http.secret_schemas import SecretWriteOut

router = APIRouter(
    prefix="/api/v1/secrets",
    tags=["secrets"],
    dependencies=[Depends(require_token)],
)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={202: {"model": SecretWriteOut, "description": "Waiting for approval"}},
)
async def set_secret(
    body: SecretSetIn,
    store: Any = Depends(get_secret_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Store `value` under `ref` in the encrypted secret store.

    A new ref — or one nothing was ever sent to — is written at once (204).
    Replacing the value of a secret an approved destination receives, or of a
    standalone secret, waits for the desktop app (202, the value held as
    ciphertext): the new value changes what that destination gets (spec
    secret "Hold a replaced value in use until a person approves it").
    """
    boundary = get_secret_boundary()
    # to_thread: the store write is file IO and, for a vault ref, a git
    # commit under the vault's write lock — nothing for the event loop.
    approval = await asyncio.to_thread(boundary.write, body.ref, body.value, actor=actor)
    if approval is not None:
        await audit.record(
            AuditEventType.SECRET_APPROVAL_REQUESTED.value,
            actor=actor,
            details={"approval_id": approval.id, "op": approval.op, "ref": body.ref},
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=SecretWriteOut(approval=approval_out(approval)).model_dump(),
        )
    await audit.record(
        AuditEventType.SECRET_SET.value,
        actor=actor,
        details={"ref": body.ref},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=SecretListOut)
async def list_refs(
    store: Any = Depends(get_secret_store),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
) -> SecretListOut:
    """Every stored ref and every ref a resource cites, with who references it.

    Refs come from the store's own enumeration and from every kind's secret
    extractor (MCP server headers, channel bot tokens, provider API keys, ...),
    so a vault restored without its secrets can say which ones are missing and
    a secret nothing references any more shows up as ``unreferenced``. A
    standalone ``secret/<name>`` also lists the skills whose files cite its
    ``coffer://secret/<name>``. A stored ref whose ciphertext this Mac's key
    cannot open is ``locked``. Presence only — no value is decrypted, so
    nothing is audited.
    """
    cited = await resources.cited_secret_refs()
    rows_stored = await asyncio.to_thread(store.list_refs)
    stored = {ref for ref, _c, _u in rows_stored}
    created = {ref: c for ref, c, _u in rows_stored}
    last_used = await asyncio.to_thread(store.last_used)
    # Checked by each ciphertext's signature against this Mac's key — nothing
    # is decrypted (spec secret "Show a secret this Mac cannot open as missing
    # on this Mac").
    locked = set(await asyncio.to_thread(store.unreadable_refs))
    mentions = await asyncio.to_thread(skills_citing_secrets, skills_root())
    boundary = get_secret_boundary()
    bindings = await asyncio.to_thread(boundary.bindings)
    pending = await asyncio.to_thread(lambda: boundary.list(status="pending"))
    exposed = {
        ref
        for ref, citers in cited.items()
        for r in citers
        if r.kind == "mcp_server" and _stdio_carries(r, ref)
    }
    out: list[SecretRefOut] = []
    for ref in sorted(stored | set(cited)):
        name = standalone_name(ref)
        skills = sorted(mentions.get(name, set())) if name else []
        rows = [
            SecretBindingOut(
                destination_kind=b.destination_kind,
                destination_uid=b.destination_uid,
                slot=b.slot,
                status="approved",
            )
            for b in bindings
            if b.ref == ref
        ] + [
            SecretBindingOut(
                destination_kind=a.destination_kind or "",
                destination_uid=a.destination_uid or "",
                slot=a.slot or "",
                status="pending",
                approval_id=a.id,
            )
            for a in pending
            if a.op == "bind" and a.ref == ref
        ]
        out.append(
            SecretRefOut(
                ref=ref,
                present=ref in stored,
                locked=ref in locked,
                created_at=created.get(ref),
                last_used_at=last_used.get(ref),
                cited_by=[
                    SecretCiterOut(uid=r.uid, kind=r.kind, name=r.name) for r in cited.get(ref, [])
                ],
                uri=secret_uri(name) if name else None,
                mentioned_by_skills=skills,
                unreferenced=not cited.get(ref) and not skills,
                bindings=rows,
                # A standalone secret reaches a `coffer run` child's
                # environment; a stdio server's secret its initial environment.
                readable_by_local_processes=bool(name) or ref in exposed,
            )
        )
    return SecretListOut(refs=out)


def _skill_folder(name: str) -> Resource:
    epoch = datetime.fromtimestamp(0, tz=UTC)
    return Resource(
        uid="",
        kind="skill",
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=epoch,
        updated_at=epoch,
    )


def _stdio_carries(resource: Resource, ref: str) -> bool:
    transport = resource.config.get("transport") or {}
    refs = transport.get("secret_refs") or {}
    return transport.get("type") == "stdio" and ref in refs.values()


# There is deliberately no `GET /{ref:path}`: no route returns a value (spec
# secret "Return no plaintext on any route, command or tool").
@router.get("/{ref:path}/exists", response_model=SecretExistsOut)
async def secret_exists(
    ref: str,
    store: Any = Depends(get_secret_store),  # noqa: B008
) -> SecretExistsOut:
    """Report whether a secret is stored under `ref`.

    Presence only — the value is never decrypted or read out for this check,
    so no audit event is recorded and a corrupt (undecryptable) row can't
    500 the probe; it still reports present.
    """
    # to_thread: a store read is blocking file IO; on the loop it would stall
    # every other request meanwhile.
    return SecretExistsOut(present=await asyncio.to_thread(store.exists, ref))


@router.delete(
    "/{ref:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_secret(
    ref: str,
    store: Any = Depends(get_secret_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    resources: ResourceService = Depends(get_resource_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Remove `ref` from the secret store. Idempotent — absent is fine,
    and audited only when a row was actually removed.

    Refuses with 409 SECRET_IN_USE when a resource config still references
    this secret: deleting it would silently break that channel / model /
    mcp_server, whose config only keeps the secret ref. The 409 names the
    citing resources so the user knows what to detach first.
    """
    citations = await resources.find_secret_citations(ref)
    name = standalone_name(ref)
    if name:
        # A standalone secret's citers are mostly files: a skill that still
        # cites its URI would break the next command it runs.
        mentions = await asyncio.to_thread(skills_citing_secrets, skills_root())
        for skill in sorted(mentions.get(name, set())):
            row = await resources.find_by_name("skill", skill)
            # A master folder with no row yet still cites it; the refusal only
            # needs its kind and name to say what to edit first.
            citations.append(row if row is not None else _skill_folder(skill))
    if citations:
        # The error composes the reference strings itself, from the rows. It is
        # NOT given a list of strings built here: ``find_secret_citations``
        # returns whole resources now, and rendering one with ``str()`` would
        # put its entire config — secret refs included — into the response
        # body of a request that was refused for naming a secret.
        exc = SecretInUse(ref, citations)
        return error_response(
            exc.code,
            str(exc),
            {
                "references": exc.references,
                # The uid rides along for a client that wants to link straight
                # to the resource; the human-readable half stays the names.
                "resources": [{"uid": c.uid, "kind": c.kind, "name": c.name} for c in citations],
            },
        )
    # to_thread: the removal is file IO and, for a vault ref, a git commit
    # under the vault's write lock — nothing for the event loop.
    removed = await asyncio.to_thread(store.remove, ref)
    # 204 either way, but only a real removal is a lifecycle change worth an
    # audit row (spec secret "Delete a secret idempotently").
    if removed:
        await asyncio.to_thread(get_secret_boundary().forget, ref)
        await audit.record(
            AuditEventType.SECRET_DELETED.value,
            actor=actor,
            details={"ref": ref},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
