"""Rename path for ``ProviderService`` (spec provider-switching).

A rename moves the row and re-projects. It used to move three things, because
three places spelled the name out instead of pointing at the resource: the
vault entry ``provider/<name>/key``, the ``audit_log`` rows, and the projected
native agent config. Two of those are fixed at the source — the vault ref is
now minted opaque (``ProviderService._mint_ref``) and the audit rows carry the
resource id — so nothing here touches secrets or history any more.

The third stays, and is why this module still exists: the name is written into
ANOTHER tool's config (Claude Code's ``apiKeyHelper`` shells out
``coffer provider key --connection <name>``; Codex shows
``display_name = "Coffer (<name>)"``). That is an interface a human reads, not
a foreign key, so a rename legitimately rewrites it rather than hiding an
opaque id in someone else's file.

``ProviderService.rename`` stays a thin delegate, mirroring how
``ResourceService.update_scope`` delegates to ``resource_scope_ops``.
"""

from __future__ import annotations

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
    """Rename connection ``name`` to ``new_name``, then re-project it."""
    resource = await service.get(name)  # 404 before anything else

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

    # The vault is not touched: the ref is an address the config already holds,
    # and it does not spell the name out.
    await service._resources.rename(service._ref(name), new, actor)

    renamed = await service.get(new)
    await _reproject(service, new, renamed)
    return renamed


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
