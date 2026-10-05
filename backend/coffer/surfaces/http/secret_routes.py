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
import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from coffer.application.audit_service import AuditService
from coffer.application.resource_delete_ops import SecretHooks
from coffer.application.resource_service import ResourceService
from coffer.application.secret.local_access import local_access_of
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError
from coffer.domain.model_proxy.state import PROXY_TOKEN_REF_PREFIX
from coffer.domain.resource import Resource
from coffer.domain.secret_errors import SecretInUse
from coffer.domain.secrets import (
    ORIGIN_PAGE,
    SecretNote,
    is_minted_ref,
    mint_secret_name,
    secret_ref,
    secret_uri,
    slot_of,
    standalone_name,
)
from coffer.infrastructure.secret.plaintext_scan import skills_citing_secrets
from coffer.infrastructure.skill.master_store import default_master_root as skills_root
from coffer.infrastructure.sync.local_state import JsonRemoteStore
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import (
    get_actor,
    get_audit_service,
    get_resource_service,
)
from coffer.surfaces.http.errors import error_response
from coffer.surfaces.http.secret_boundary_wiring import approval_applied, get_secret_boundary
from coffer.surfaces.http.secret_composition import get_secret_store
from coffer.surfaces.http.secret_notes_wiring import get_secret_notes, optional_secret_notes
from coffer.surfaces.http.secret_schemas import (
    SecretBindingOut,
    SecretCiterOut,
    SecretExistsOut,
    SecretListOut,
    SecretMintedOut,
    SecretRefOut,
    SecretSetIn,
)

router = APIRouter(
    prefix="/api/v1/secrets",
    tags=["secrets"],
    dependencies=[Depends(require_token)],
)


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={201: {"model": SecretMintedOut, "description": "Stored under a minted id."}},
)
async def set_secret(
    body: SecretSetIn,
    store: Any = Depends(get_secret_store),  # noqa: B008
    audit: AuditService = Depends(get_audit_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> Response:
    """Store `value` under `ref` in the encrypted secret store, at once (204).

    Whoever supplies a value already has it, so a new ref and a replacement are
    both written without approval (spec secret "Store a secret through the
    API"). A replacement is audited as such, never with a value, and whatever
    holds the old value, such as the model proxy, picks the new one up.

    Without a `ref`, a `label` names it: the id `secret/<uuid4 hex>` is minted,
    the label stored as its note, and the answer is 201 with the ref and uri
    (spec secret "Mint every secret's id; a person names it").
    """
    minted = body.ref is None
    ref = body.ref if body.ref is not None else secret_ref(mint_secret_name())
    # to_thread: the store write is file IO and, for a vault ref, a git
    # commit under the vault's write lock — nothing for the event loop.
    replaced = await asyncio.to_thread(store.exists, ref)
    if not minted and not replaced and not is_minted_ref(ref):
        # A person names a secret (a label); Coffer mints every id.
        raise ConfigValidationError(
            f"{ref!r} is not a secret that exists, and a new secret's id is minted "
            "by Coffer: omit the ref (and send a label) to create one"
        )
    await asyncio.to_thread(store.set, ref, body.value)
    approval_applied()
    await audit.record(
        AuditEventType.SECRET_SET.value,
        actor=actor,
        details={"ref": ref, "replaced": replaced},
    )
    if body.label or body.created_for or minted:
        notes = get_secret_notes()

        def merge(before: SecretNote | None) -> SecretNote:
            before = before or SecretNote()
            return SecretNote(
                label=body.label or before.label,
                description=before.description,
                created_for=body.created_for or before.created_for,
                # Added on the page (no ref sent): a person made it for itself.
                origin=ORIGIN_PAGE if minted else before.origin,
            )

        await asyncio.to_thread(
            notes.update, ref, merge, summary=f"describe secret {ref}", actor=actor
        )
    if not minted:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    name = standalone_name(ref)
    assert name is not None
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=SecretMintedOut(ref=ref, uri=secret_uri(name)).model_dump(),
    )


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
    cannot open is ``locked``. An agent's model-proxy token
    (``proxy-token/<agent name>``) is not listed: Coffer mints it, the agent
    fetches it, and no person enters, replaces or cites it. Presence only — no
    value is decrypted, so nothing is audited.
    """
    cited = await resources.cited_secret_refs()
    notes = optional_secret_notes()
    noted = await asyncio.to_thread(notes.all) if notes is not None else {}
    rows_stored = [
        row
        for row in await asyncio.to_thread(store.list_refs)
        if not row[0].startswith(PROXY_TOKEN_REF_PREFIX)
    ]
    stored = {ref for ref, _c, _u in rows_stored}
    created = {ref: c for ref, c, _u in rows_stored}
    last_used = await asyncio.to_thread(store.last_used)
    # Checked by each ciphertext's signature against this Mac's key — nothing
    # is decrypted (spec secret "Show a secret this Mac cannot open as missing
    # on this Mac").
    locked = set(await asyncio.to_thread(store.unreadable_refs))
    skill_citers = await _skill_citers(resources)
    sync_ref = await _sync_remote_ref()
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
    for ref in sorted(stored | set(cited) | ({sync_ref} if sync_ref else set())):
        name = standalone_name(ref)
        skills = skill_citers(ref) if name else []
        local = local_access_of(bindings, pending, ref) if name else None
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
        note = noted.get(ref)
        out.append(
            SecretRefOut(
                ref=ref,
                label=note.label if note else None,
                description=note.description if note else None,
                present=ref in stored,
                locked=ref in locked,
                created_for=note.created_for if note else None,
                created_at=created.get(ref),
                last_used_at=last_used.get(ref),
                cited_by=[
                    SecretCiterOut(
                        uid=r.uid, kind=r.kind, name=r.name, slot=_slot(resources, r, ref)
                    )
                    for r in cited.get(ref, [])
                ]
                + (
                    [SecretCiterOut(uid=_SYNC_UID, kind=_SYNC_KIND, name=_SYNC_NAME, slot="token")]
                    if ref == sync_ref
                    else []
                ),
                uri=secret_uri(name) if name else None,
                mentioned_by_skills=skills,
                unreferenced=not cited.get(ref) and not skills and ref != sync_ref,
                bindings=rows,
                # A standalone secret reaches a `coffer run` child's environment
                # only once a person granted it; a stdio server's secret its
                # initial environment.
                readable_by_local_processes=local == "on" or ref in exposed,
                local_access=local,
            )
        )
    return SecretListOut(refs=out)


_SYNC_KIND = "sync_remote"
_SYNC_UID = "remote"
_SYNC_NAME = "Vault sync"


async def _sync_remote_ref() -> str | None:
    """The secret this machine's sync remote pushes with, if one is set. It is
    machine-local settings, not a resource, so the citation index does not see
    it; it still uses the secret (spec secret "List every stored and cited
    secret with what uses it")."""
    remote = await asyncio.to_thread(JsonRemoteStore().get)
    return remote.secret_ref if remote is not None and remote.secret_ref else None


def _sync_remote_row() -> Resource:
    """The sync remote as a citer row, for the in-use refusal."""
    row = _skill_folder(_SYNC_NAME)
    return dataclasses.replace(row, uid=_SYNC_UID, kind=_SYNC_KIND)


async def _skill_citers(resources: ResourceService) -> Callable[[str], list[str]]:
    """``ref -> skills whose files cite it``, from the citation index (the files
    are rescanned only where no index is wired, such as a bare test app)."""
    hooks: SecretHooks | None = getattr(resources, "secret_hooks", None)
    index = hooks.index if hooks is not None else None
    if index is not None:
        await index.settled()
        return index.skill_citers
    mentions = await asyncio.to_thread(skills_citing_secrets, skills_root())
    return lambda ref: sorted(mentions.get(standalone_name(ref) or "", set()))


def _slot(resources: ResourceService, resource: Resource, ref: str) -> str | None:
    keys = [k for k, v in resources.secret_slots(resource).items() if v == ref]
    return slot_of(resource.kind, keys[0]) if keys else None


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


def _checked_ref(ref: str) -> str:
    """A ref in a URL path, refused (422) when a segment is empty or only dots:
    the store maps a ref to a file, and ``.``/``..`` name none."""
    if any(not s or set(s) == {"."} for s in ref.split("/")):
        raise ConfigValidationError(f"not a secret ref: {ref!r}")
    return ref


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
    return SecretExistsOut(present=await asyncio.to_thread(store.exists, _checked_ref(ref)))


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
    ref = _checked_ref(ref)
    citations = await resources.find_secret_citations(ref)
    name = standalone_name(ref)
    if name:
        # A standalone secret's citers are mostly files: a skill that still
        # cites its URI would break the next command it runs.
        for skill in (await _skill_citers(resources))(ref):
            row = await resources.find_by_name("skill", skill)
            # A master folder with no row yet still cites it; the refusal only
            # needs its kind and name to say what to edit first.
            citations.append(row if row is not None else _skill_folder(skill))
    if await _sync_remote_ref() == ref:
        citations.append(_sync_remote_row())
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
        await audit.record(
            AuditEventType.SECRET_DELETED.value,
            actor=actor,
            details={"ref": ref},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
