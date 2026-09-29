"""Enable/disable path for ``ResourceService.set_enabled``.

Extracted to keep ``resource_service.py`` under the file-size limit, in the
shape of ``resource_scope_ops``: a free function that takes the service and
reaches into its private attributes, with ``set_enabled`` a thin delegate.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotToggleable
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService


async def set_enabled(service: ResourceService, uid: str, enabled: bool, *, actor: str) -> Resource:
    """Set a resource's enabled flag, auditing and reconciling a real transition.

    A kind that declares ``toggleable=False`` is refused BEFORE the idempotent
    check, so enabling an already-enabled collection is refused too: the
    answer to "may this be switched" does not depend on which way it was
    asked (spec resource-framework "Address every resource by an immutable
    uid through one kind-agnostic surface"). Every caller — the enable and
    disable routes, the CLI through them, a bulk bar issuing one request per
    row — goes through here, so the refusal is in one place.
    """
    before = await service.get(uid)
    kind_def = service._require_kind(before.kind)
    if not kind_def.toggleable:
        raise ResourceNotToggleable(before.kind, uid)
    if before.enabled == enabled:
        return before  # idempotent — no audit, no hook
    updated = await service._repo.set_enabled(uid, enabled)
    event = AuditEventType.RESOURCE_ENABLED if enabled else AuditEventType.RESOURCE_DISABLED
    await service._audit.record(event.value, resource=updated, actor=actor)
    # Kind-level reconciliation, exactly as ``update_scope`` fires
    # ``on_scope_changed``: AFTER persistence + audit, and handed the row
    # carrying the flag that triggered it. Fired only on a real transition
    # (the idempotent early return above skips it).
    if kind_def.on_enabled_changed is not None:
        hook_result = kind_def.on_enabled_changed(updated)
        if inspect.isawaitable(hook_result):
            await hook_result
    return updated
