"""The post-register seam for kinds that send a secret somewhere.

Spec secret "Approve a secret's binding when its destination is registered".
:class:`~coffer.application.resource_service.ResourceService` calls
:func:`settle_bindings` once after a resource is created or its config changes,
whatever the kind and whichever surface made the change, so the secret boundary
is applied while the person is registering and not only at the first use. The
service does not know what a destination is; the composition root supplies the
implementation.
"""

from __future__ import annotations

import logging
from typing import Protocol

from coffer.domain.resource import Resource

_logger = logging.getLogger(__name__)


class BindingSettlerPort(Protocol):
    async def settle(self, resource: Resource, actor: str) -> None: ...


async def settle_bindings(
    settler: BindingSettlerPort | None, resource: Resource, actor: str
) -> None:
    """Run the seam. A failure here never undoes the write: the binding is
    evaluated again, with no approval skipped, at every use."""
    if settler is None:
        return
    try:
        await settler.settle(resource, actor)
    except Exception:
        _logger.warning(
            "resource.bindings.settle_failed",
            extra={"kind": resource.kind, "uid": resource.uid},
            exc_info=True,
        )


__all__ = ["BindingSettlerPort", "settle_bindings"]
