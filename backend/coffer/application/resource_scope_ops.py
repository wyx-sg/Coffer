"""Scope-mutation path for ``ResourceService.update_scope``.

Extracted to keep ``resource_service.py`` under the file-size limit. Like
``skill/binding_ops.py`` this is a free function that takes the
``ResourceService`` instance and reaches into its (private) attributes — it
is conceptually private to the service, and ``update_scope`` stays a thin
delegate so callers see no change in behavior or signature.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound, ScopeInvalidError
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope import ScopeValidationError, validate_scope

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService


async def update_scope(
    service: ResourceService,
    ref: ResourceRef,
    scope: dict[str, Any] | None,
    *,
    actor: str,
) -> Resource:
    """Set (or clear) a resource's machine x agent activation scope (ADR-045).

    Framework-level: unlike ``update_config``/``delete``, this is NOT gated
    on ``allow_lifecycle_kind`` — scope is orthogonal to a kind's creation
    invariants, so it applies uniformly to lifecycle kinds (skill, agent,
    channel) too. ``scope`` is validated against the kind's declared
    ``scope_axes`` (empty means the kind does not support scope at all).
    """
    kind_def = service._require_kind(ref.kind)
    try:
        validate_scope(scope, axes=kind_def.scope_axes)
    except ScopeValidationError as e:
        raise ScopeInvalidError(str(e)) from e
    # Confirms existence up front (raises ResourceNotFound) — mirrors
    # update_config's before-read.
    await service.get(ref)
    updated = await service._repo.update_scope(ref, scope)
    if updated is None:
        raise ResourceNotFound(ref.kind, ref.name)
    await service._audit.record(
        AuditEventType.RESOURCE_SCOPE_UPDATED.value,
        ref=ref,
        actor=actor,
        # Scope carries only machine ids / agent names — no secrets — so it
        # is audited verbatim (no redactor needed, unlike config).
        details={"scope": scope},
    )
    # Kind-level reconciliation (Task 11 Fix 2): runs AFTER persistence +
    # audit, unlike ``on_update_config`` — by the time this fires the new
    # scope is already the row's scope, so a hook re-reading the resource
    # (e.g. skill delivery reconciliation) sees the edit that triggered it.
    if kind_def.on_scope_changed is not None:
        hook_result = kind_def.on_scope_changed(ref)
        if inspect.isawaitable(hook_result):
            await hook_result
    service._notify_change()
    return updated
