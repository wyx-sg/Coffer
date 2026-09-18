"""Credential-release helper for ``ResourceService.delete``.

Extracted to keep ``resource_service.py`` under the file-size limit. Free
function that takes the ``ResourceService`` instance and reaches into its
(private) attributes — conceptually private to the service, mirroring
``resource_scope_ops.py`` and ``skill/binding_ops.py``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from coffer.application.resource_kind_hooks import extract_credential_refs
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind, Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)


async def release_orphaned_credentials(
    service: ResourceService,
    kind_def: Kind,
    config: dict[str, Any],
    actor: str,
) -> list[str]:
    """Drop a just-deleted resource's credentials that nothing cites anymore.

    Runs after the resource's row is removed, so the deleted resource no
    longer counts as a citation of its own refs. A failure must not turn the
    already-completed deletion into a caller-facing error — the credential
    then merely lingers, which was the status quo.
    """
    if service._credentials is None:
        return []
    released: list[str] = []
    for cred_ref in dict.fromkeys(extract_credential_refs(kind_def, config).values()):
        try:
            # Off the loop thread: the store is a blocking SQLite writer, and
            # calling it inline competes with the connection this coroutine is
            # already holding — the delete then fails with "database is locked",
            # gets swallowed by the except below, and the credential silently
            # lingers. Every other credential write in the codebase already
            # goes through a thread for exactly this reason.
            if not await asyncio.to_thread(service._credentials.exists, cred_ref):
                continue
            if await service.find_credential_citations(cred_ref):
                continue
            await asyncio.to_thread(service._credentials.delete, cred_ref)
            await service._audit.record(
                AuditEventType.CREDENTIAL_DELETED.value,
                actor=actor,
                details={"ref": cred_ref},
            )
            released.append(cred_ref)
        except Exception:
            _logger.exception("resource.credential_release_failed", extra={"ref": cred_ref})
    return released


async def citations_of(service: ResourceService, credential_ref: str) -> list[Resource]:
    """Return every resource whose config cites ``credential_ref``.

    A credential lives in the encrypted store and is referenced only by its ref
    from resource config (a channel's bot token, an mcp_server's auth header, a
    model's API key). Deleting the credential out from under a live resource
    silently breaks it, so the credential-delete route calls this first and
    refuses (409) when the list is non-empty. Each kind that stores secrets
    supplies a ``credential_ref_extractor``; kinds without one cite nothing and
    are skipped.

    Whole resources rather than identifiers, because both callers want more
    than the identity: the 409 names the citing resources back to the user, and
    the release above only has to know whether the list is empty.
    """
    citing: list[Resource] = []
    for resource in await service._repo.list():
        kind_def = service._kinds.get(resource.kind)
        if kind_def is None:
            continue
        if credential_ref in extract_credential_refs(kind_def, resource.config).values():
            citing.append(resource)
    return citing
