"""Resolving the ``{uid}`` in ``/api/v1/memory/partitions/{uid}/…``.

One function, in a module of its own, because all three partition-scoped route
modules need it and none of them should be importing another's routes to get
it — the same reason ``surfaces/http/mcp/capability_views.py`` exists beside
that family's route modules.
"""

from __future__ import annotations

from coffer.application.memory.service import KIND_MEMORY
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource


async def require_partition(uid: str, resources: ResourceService) -> Resource:
    """The ``memory`` Resource ``uid`` names, or 404.

    Hands the **row** back rather than only asserting it exists, because every
    caller needs the name off it: a partition's directory under the memory root
    is called by its label, so a route addressed by identity still has to learn
    the label before it can open anything. Resolving once here is what keeps
    that from being a lookup each handler repeats — and what keeps the label a
    handler uses to the one the row carried at this instant.

    404 (``RESOURCE_NOT_FOUND``) for a uid nothing answers to — the generic,
    already-mapped error, since inventing a memory-specific "no such partition"
    code would duplicate it for no reason. A uid belonging to some *other* kind
    is refused the same way, and that check is not ceremony: a uid is unique
    across kinds, so without it a knowledge collection's uid would resolve here
    and these handlers would walk a directory under the wrong root.
    """
    row = await resources.get(uid)
    if row.kind != KIND_MEMORY:
        raise ResourceNotFound(uid)
    return row
