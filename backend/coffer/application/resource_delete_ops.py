"""Credential-release helper for ``ResourceService.delete``.

Extracted to keep ``resource_service.py`` under the file-size limit. Free
function that takes the ``ResourceService`` instance and reaches into its
(private) attributes — conceptually private to the service, mirroring
``resource_scope_ops.py`` and ``skill/binding_ops.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind

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
    from coffer.application.resource_service import _extract_credential_refs

    if service._credentials is None:
        return []
    released: list[str] = []
    for cred_ref in dict.fromkeys(_extract_credential_refs(kind_def, config).values()):
        try:
            if not service._credentials.exists(cred_ref):
                continue
            if await service.find_credential_citations(cred_ref):
                continue
            service._credentials.delete(cred_ref)
            await service._audit.record(
                AuditEventType.CREDENTIAL_DELETED.value,
                actor=actor,
                details={"ref": cred_ref},
            )
            released.append(cred_ref)
        except Exception:
            _logger.exception("resource.credential_release_failed", extra={"ref": cred_ref})
    return released
