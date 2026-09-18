"""Scope-mutation path for ``ResourceService.update_scope``.

Extracted to keep ``resource_service.py`` under the file-size limit. Like
``skill/binding_ops.py`` this is a free function that takes the
``ResourceService`` instance and reaches into its (private) attributes — it
is conceptually private to the service, and ``update_scope`` stays a thin
delegate so callers see no change in behavior or signature.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound, ScopeInvalidError
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope, validate_scope

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService


async def update_scope(
    service: ResourceService,
    uid: str,
    scope: Scope | None,
    *,
    actor: str,
) -> Resource:
    """Set (or clear) a resource's activation scope (ADR per-agent-resource-scope).

    Framework-level: unlike ``update_config``/``delete``, this is NOT gated
    on ``allow_lifecycle_kind`` — scope is orthogonal to a kind's creation
    invariants, so it applies uniformly to lifecycle kinds (skill) too.
    ``scope`` is validated against the kind's declared ``supports_scope``
    (False means the kind does not support scope at all).
    """
    # Read first: the kind is a property of the row, not of the request, so
    # there is nothing to validate the scope against until we have it.
    before = await service.get(uid)
    kind_def = service._require_kind(before.kind)
    try:
        # ``ScopeValidationError`` is itself a ``ValueError`` subclass.
        validate_scope(scope, supports_scope=kind_def.supports_scope)
    except ValueError as e:
        raise ScopeInvalidError(str(e)) from e
    # Kind-level pre-validation: runs BEFORE persistence + audit, the exact
    # opposite of its neighbour ``on_scope_changed`` at the end of this
    # function. The two differ because they answer different questions: this one
    # may REJECT the edit, so it must see the row as it still is and leave it
    # untouched when it raises, while a reconciliation reacts to an edit that
    # already happened and has to read the stored scope to do so. A kind that
    # supplies neither is unaffected.
    if kind_def.validate_scope_for is not None:
        try:
            pre_result = kind_def.validate_scope_for(before, scope)
            if inspect.isawaitable(pre_result):
                await pre_result
        except ValueError as e:
            # Same envelope as the shape check above (SCOPE_INVALID → 422), so
            # the wire contract is one code for "this scope is not acceptable".
            raise ScopeInvalidError(str(e)) from e
    updated = await service._repo.update_scope(uid, scope)
    if updated is None:
        raise ResourceNotFound(uid)
    await service._audit.record(
        AuditEventType.RESOURCE_SCOPE_UPDATED.value,
        resource=updated,
        actor=actor,
        # Scope carries only agent uids — no secrets — so it is audited
        # verbatim (no redactor needed, unlike config), in the same shape the
        # column stores.
        details={"scope": scope.to_json() if scope is not None else None},
    )
    # Kind-level reconciliation: runs AFTER persistence +
    # audit, unlike ``on_update_config`` — by the time this fires the new
    # scope is already the row's scope, so a hook re-reading the resource
    # (e.g. skill delivery reconciliation) sees the edit that triggered it.
    if kind_def.on_scope_changed is not None:
        hook_result = kind_def.on_scope_changed(updated)
        if inspect.isawaitable(hook_result):
            await hook_result
    return updated
