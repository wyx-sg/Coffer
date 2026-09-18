"""Rename path for ``ResourceService.rename``.

Extracted to keep ``resource_service.py`` under the file-size limit, beside
``resource_scope_ops.py`` and ``resource_delete_ops.py``: a free function that
takes the ``ResourceService`` instance and reaches into its (private)
attributes, conceptually private to the service.

A rename is one column. What lives here is not the write but everything that
has to be true around it — the two name rules, the collision check, and the one
hook a kind gets when its name is also a directory.
"""

from __future__ import annotations

import dataclasses
import inspect
from typing import TYPE_CHECKING

from coffer.application.resource_kind_hooks import check_name
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceAlreadyExists
from coffer.domain.resource import Kind, Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService


async def _fire(kind_def: Kind, resource: Resource, new_name: str) -> None:
    if kind_def.on_rename is None:
        return
    result = kind_def.on_rename(resource, new_name)
    if inspect.isawaitable(result):
        await result


async def rename(
    service: ResourceService,
    uid: str,
    new_name: str,
    actor: str,
) -> Resource:
    """Change a resource's LABEL; see ``ResourceService.rename`` for the contract."""
    before = await service.get(uid)  # 404 for an absent resource, before anything moves
    if new_name == before.name:
        # Idempotent, and silent: a client re-sending the same PATCH should not
        # litter the trail with renames that renamed nothing.
        return before
    kind_def = service._require_kind(before.kind)
    check_name(kind_def, new_name)
    # Checked explicitly, before any write, so a collision is a clean 409 that
    # has moved nothing — neither the row nor a kind's directory. The
    # (kind, name) unique constraint still backs this up for a racing writer;
    # ``ResourceRepo.rename`` translates it into the same error.
    if await service._repo.find_by_name(before.kind, new_name) is not None:
        raise ResourceAlreadyExists(before.kind, new_name)
    await _fire(kind_def, before, new_name)
    try:
        renamed = await service._repo.rename(uid, new_name)
    except ResourceAlreadyExists:
        # The racing writer the pre-check cannot exclude. The hook has already
        # moved the kind's directory, so ask it to move it back before the
        # failure propagates — otherwise the row keeps its old name while its
        # directory sits under the new one.
        await _fire(kind_def, dataclasses.replace(before, name=new_name), before.name)
        raise
    await service._audit.record(
        AuditEventType.RESOURCE_RENAMED.value,
        resource=renamed,
        actor=actor,
        details={"from": before.name, "to": new_name},
    )
    return renamed
