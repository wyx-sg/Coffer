"""Title path for ``ResourceService.set_title``.

Extracted to keep ``resource_service.py`` under the file-size limit, beside
``resource_rename_ops.py``: a free function that takes the ``ResourceService``
instance and reaches into its (private) attributes.

A title is display text a person chose (spec resource-framework "Carry an
optional editable title on the kinds that have one"); a kind that carries none
(``Kind.titled`` — `agent`, `mcp_server`, `skill`) refuses a non-empty one. It
is deliberately NOT routed through ``update_config``, for two reasons:

- A title has no on-disk artifact behind it for the generic path to desync, so
  the lifecycle seam that refuses a kind's config rewrite has nothing to guard.
- Writing it re-validates nothing, probes no secret and fires no kind hook:
  a title edit refused because a secret the config cites has since been
  deleted would be a refusal about something the caller did not touch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.resource_actor import acting_as
from coffer.application.resource_kind_ops import checked_title
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService


async def set_title(
    service: ResourceService,
    uid: str,
    title: str | None,
    actor: str,
) -> Resource:
    """Set, change or clear a resource's title; see ``ResourceService.set_title``."""
    before = await service.get(uid)  # 404 before anything is written
    wanted = checked_title(service._require_kind(before.kind), title)
    if wanted == before.title:
        # Idempotent and silent, like a rename to the name it already has.
        return before
    with acting_as(actor):
        updated = await service._repo.set_title(uid, wanted)
    # Audited as the update it is. ``details`` says which field moved, so the
    # trail does not read as a config edit with identical before and after.
    await service._audit.record(
        AuditEventType.RESOURCE_UPDATED.value,
        resource=updated,
        actor=actor,
        details={"title": {"before": before.title, "after": wanted}},
    )
    return updated
