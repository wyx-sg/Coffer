"""Rename path for ``ProviderService`` (spec provider-switching).

WHY a rename is not a config PATCH: a connection's NAME is its identity, and
three other places spell that identity out rather than pointing at a row id —
the Fernet vault entry ``provider/<name>/key`` the connection owns, the
``audit_log`` rows recorded against ``(kind, name)``, and the PROJECTED native
agent config (Claude Code's ``apiKeyHelper``, which shells out
``coffer provider key --connection <name>``, and Codex's
``display_name = "Coffer (<name>)"``). A PATCH edits one connection's config in
place and touches none of them; a rename must move all four together or the
connection is left half-renamed — an orphaned secret nothing will ever collect,
a history stranded under a name that resolves to nothing, or a live agent
invoking a connection name that no longer exists.

The body lives here rather than in ``provider/service.py`` because that module
is at its file-size ceiling; ``ProviderService.rename`` stays a thin delegate,
mirroring how ``ResourceService.update_scope`` delegates to
``resource_scope_ops``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from coffer.domain.errors import ConfigValidationError, ResourceAlreadyExists
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.provider.service import ProviderService

KIND = "provider"

#: Same bound the create route enforces on ``ProviderCreate.name`` — a rename
#: must not be able to produce a name the create path would have rejected.
_MAX_NAME_LEN = 64


async def rename(
    service: ProviderService,
    name: str,
    new_name: str,
    *,
    actor: str,
) -> Resource:
    """Rename connection ``name`` to ``new_name``, repointing everything that
    spells the old name out (see the module docstring for what those are)."""
    resource = await service.get(name)  # 404 before anything else
    cfg = service._cfg(resource)

    new = new_name.strip()
    if new == name:
        return resource  # idempotent no-op: nothing to move
    if not new:
        raise ConfigValidationError("connection name must not be empty")
    if len(new) > _MAX_NAME_LEN:
        raise ConfigValidationError(f"connection name too long: at most {_MAX_NAME_LEN} characters")
    # Checked explicitly, before any write, so a collision is a clean 409 that
    # has moved nothing — the (kind, name) unique constraint still backs this up
    # for a racing writer (``ResourceRepo.rename`` translates it identically).
    if any(r.name == new for r in await service.list()):
        raise ResourceAlreadyExists(KIND, new)

    old_ref = service._owned_ref(name)
    new_ref = service._owned_ref(new)
    secret = await _secret_to_move(service, cfg.credential_ref, old_ref, name)

    # Order of operations, chosen so no step can leave a dangling reference:
    # the NEW vault entry is written FIRST (a briefly duplicated secret is
    # harmless; a briefly missing one breaks a live agent), the row moves next,
    # the config is repointed at the new ref, and only THEN is the old entry
    # dropped. A failed row move rewinds the new entry, so nothing is orphaned.
    if secret is not None:
        await asyncio.to_thread(service._credentials.set, new_ref, secret)
    try:
        await service._resources.rename(service._ref(name), new, actor)
    except BaseException:
        if secret is not None:
            await asyncio.to_thread(service._credentials.delete, new_ref)
        raise
    if secret is not None:
        config = dict(resource.config)
        config["credential_ref"] = new_ref
        await service._resources.update_config(service._ref(new), config, actor)
        await asyncio.to_thread(service._credentials.delete, old_ref)

    renamed = await service.get(new)
    await _reproject(service, new, renamed)
    return renamed


async def _secret_to_move(
    service: ProviderService,
    credential_ref: str | None,
    old_ref: str,
    name: str,
) -> str | None:
    """The secret value to re-file under the new name, or ``None`` to leave the
    vault alone.

    Only a credential the connection OWNS (``provider/<name>/key``, the ref this
    service mints for an inline secret) moves — a shared or user-supplied ref is
    somebody else's name. And even an owned ref stays put if another resource
    cites it: renaming a vault entry out from under another citer would break
    that resource's key lookup, and the entry's name is not worth that.
    """
    if credential_ref != old_ref:
        return None
    citers = await service._resources.find_credential_citations(old_ref)
    if any(not (c.kind == KIND and c.name == name) for c in citers):
        return None
    # Nothing to move if the vault holds no value under the ref (a connection
    # created against a ref that was since deleted).
    value: str | None = await asyncio.to_thread(service._credentials.get, old_ref)
    return value


async def _reproject(service: ProviderService, new: str, renamed: Resource) -> None:
    """Re-write the native agent config of an ACTIVE connection under its new name.

    The projection embeds the name (``apiKeyHelper``, Codex's ``display_name``),
    so an active connection renamed without this leaves its agent shelling out
    to a connection that no longer resolves. The projector writes only when the
    content actually changed, so this is a no-op for an inactive connection's
    agents and for anything the rename did not touch.
    """
    cfg = service._cfg(renamed)
    if not cfg.is_active:
        return
    agents = await service._agents.list()
    for agent_type in service._compat(cfg):
        service._projector.project_type(new, cfg, agents, agent_type)
