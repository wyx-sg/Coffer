"""Secret-release helper for ``ResourceService.delete``.

Extracted to keep ``resource_service.py`` under the file-size limit. Free
function that takes the ``ResourceService`` instance and reaches into its
(private) attributes — conceptually private to the service, mirroring
``resource_scope_ops.py`` and ``skill/binding_ops.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from coffer.application.resource_kind_ops import secret_refs
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind, Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)


class CitationIndexPort(Protocol):
    """``application.secret.citation_index.CitationIndex``: what cites each secret."""

    async def settled(self) -> None: ...

    def resource_citers(self) -> dict[str, list[str]]: ...

    def skill_citers(self, ref: str) -> list[str]: ...


@dataclasses.dataclass
class SecretHooks:
    #: ``(ref, resource uid) -> bool``: whether deleting that resource may
    #: release the secret.
    owns: Callable[[str, str], bool] | None = None
    #: What cites each secret; reads never rescan the resources or the skills.
    index: CitationIndexPort | None = None


async def release_orphaned_secrets(
    service: ResourceService,
    kind_def: Kind,
    config: dict[str, Any],
    actor: str,
    uid: str = "",
) -> list[str]:
    """Drop a just-deleted resource's secrets that nothing cites anymore.

    Runs after the resource's row is removed, so the deleted resource no
    longer counts as a citation of its own refs. A failure must not turn the
    already-completed deletion into a caller-facing error — the secret
    then merely lingers, which was the status quo.

    Only a secret minted for the deleted resource is released
    (``created_for`` in its notes), and only when no other resource and no
    skill file cites it; every other secret is kept and shows as not used
    (spec secret "Release unshared references when a resource is
    deleted").
    """
    if service._secrets is None:
        return []
    released: list[str] = []
    for cred_ref in dict.fromkeys(secret_refs(kind_def, config).values()):
        owns = service.secret_hooks.owns
        if owns is not None and not await asyncio.to_thread(owns, cred_ref, uid):
            continue
        try:
            # Off the loop thread: the store does file IO and, for a vault ref,
            # a git commit under the vault's write lock. The store's removal
            # hook forgets the ref's approved destinations.
            if not await asyncio.to_thread(service._secrets.exists, cred_ref):
                continue
            if await service.find_secret_citations(cred_ref):
                continue
            await asyncio.to_thread(service._secrets.delete, cred_ref)
            await service._audit.record(
                AuditEventType.SECRET_DELETED.value,
                actor=actor,
                details={"ref": cred_ref},
            )
            released.append(cred_ref)
        except Exception:
            _logger.exception("resource.secret_release_failed", extra={"ref": cred_ref})
    return released


async def citations_of(service: ResourceService, secret_ref: str) -> list[Resource]:
    """Return every resource whose config cites ``secret_ref``.

    A secret lives in the encrypted store and is referenced only by its ref
    from resource config (a channel's bot token, an mcp_server's auth header, a
    model's API key). Deleting the secret out from under a live resource
    silently breaks it, so the secret-delete route calls this first and
    refuses (409) when the list is non-empty. Each kind that stores secrets
    supplies a ``secret_ref_extractor``; kinds without one cite nothing and
    are skipped.

    Whole resources rather than identifiers, because both callers want more
    than the identity: the 409 names the citing resources back to the user, and
    the release above only has to know whether the list is empty.
    """
    index = service.secret_hooks.index
    if index is not None:
        await index.settled()
        uids = index.resource_citers().get(secret_ref, [])
        found = [await service._repo.find(uid) for uid in dict.fromkeys(uids)]
        return [r for r in found if r is not None]
    citing: list[Resource] = []
    for resource in await service._repo.list():
        kind_def = service._kinds.get(resource.kind)
        if kind_def is None:
            continue
        if secret_ref in secret_refs(kind_def, resource.config).values():
            citing.append(resource)
    return citing


async def all_citations(service: ResourceService) -> dict[str, list[Resource]]:
    """Every secret ref any registered resource cites, with its citers.

    The whole-vault form of ``citations_of``: one scan over every row, each
    kind asked through its own ``secret_ref_extractor``, so a channel's bot
    token and a provider connection's API key count as much as an MCP server's
    header. ``coffer secret list`` reads this to say which cited secrets
    the store is missing.
    """
    index = service.secret_hooks.index
    if index is not None:
        await index.settled()
        by_ref = index.resource_citers()
        resources = {
            uid: await service._repo.find(uid)
            for uid in dict.fromkeys(u for uids in by_ref.values() for u in uids)
        }
        return {
            ref: [r for u in dict.fromkeys(uids) if (r := resources.get(u)) is not None]
            for ref, uids in by_ref.items()
        }
    cited: dict[str, list[Resource]] = {}
    for resource in await service._repo.list():
        kind_def = service._kinds.get(resource.kind)
        if kind_def is None:
            continue
        for ref in dict.fromkeys(secret_refs(kind_def, resource.config).values()):
            cited.setdefault(ref, []).append(resource)
    return cited
