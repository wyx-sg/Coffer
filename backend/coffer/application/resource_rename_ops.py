"""Giving a resource a different name (spec resource-framework FR-010).

Split out of ``ResourceService`` for the same reason ``resource_scope_ops`` and
``resource_delete_ops`` were: that class is the lifecycle's front door, and it
stays under its line ceiling by keeping each operation's reasoning in its own
module rather than growing a longer method for each.

The reasoning here is one rule with two halves — which kinds may be renamed
through the kind-agnostic surface at all, and what a rename must leave alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError, RenameNotSupported
from coffer.domain.resource import Resource, ResourceRef

if TYPE_CHECKING:  # pragma: no cover - a cycle at runtime, types only
    from coffer.application.resource_service import ResourceService


async def rename(
    service: ResourceService,
    ref: ResourceRef,
    new_name: str,
    actor: str,
    *,
    allow_lifecycle_kind: bool = False,
) -> Resource:
    """Move a resource to ``new_name``.

    Its own operation rather than an ``update_config`` on the name because
    a name is not config — but all it does is move the row. The audit trail
    needs no repointing: rows carry the resource's stable id, so history
    follows it while each row keeps saying what the resource was called
    when that event happened. The rename is recorded as its own event.

    The KIND decides whether the KIND-AGNOSTIC surface may do it (FR-010).
    A name is a label, but it is also this framework's address, so a kind
    whose name is written out somewhere this move cannot reach — into
    another tool's config, into a folder on disk — would be left with that
    reference pointing at nothing. Those kinds declare no rename here and
    rename through their own service, which passes
    ``allow_lifecycle_kind`` and then repairs what it knows about. Exactly
    the seam ``update_config`` already draws for the same reason.
    """
    kind_def = service._require_kind(ref.kind)
    if not kind_def.supports_rename and not allow_lifecycle_kind:
        raise RenameNotSupported(ref.kind)
    # Same CODE-030 name check ``register`` applies, BEFORE any DB write.
    if kind_def.validate_name is not None:
        try:
            kind_def.validate_name(new_name)
        except ValueError as e:
            raise ConfigValidationError(str(e)) from e
    before = await service.get(ref)  # 404 for an absent resource, before anything moves
    if before.name == new_name:
        # The name it already has renames nothing and records nothing — a
        # dialog submitted with that field untouched has not renamed.
        return before
    renamed = await service._repo.rename(ref, new_name)
    await service._audit.record(
        AuditEventType.RESOURCE_RENAMED.value,
        ref=ResourceRef(ref.kind, new_name),
        actor=actor,
        details={"from": ref.name, "to": new_name},
    )
    return renamed
