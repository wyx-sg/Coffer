"""The memory substrate the reorg service is built from (spec 007).

Kept out of the service file (budget) and separated so each service has a
clear dependency manifest. Reuses ``OrganizerCollaborators`` directly since the
reorg service needs exactly the same field set.
"""

from __future__ import annotations

from coffer.application.memory.organizer_deps import (
    OrganizerCollaborators,
    collaborators_from_service,
)
from coffer.application.memory.service import MemoryService

# Reuse the same collaborator shape — the reorg service needs exactly the same
# fields (resolve_store, get_config, store_ref, documents, retrieval, reconciler,
# audit, embedding_resolver). Alias to keep naming explicit.
ReorgCollaborators = OrganizerCollaborators


def reorg_collaborators_from_service(svc: MemoryService) -> ReorgCollaborators:
    """Project a live ``MemoryService`` onto the reorg's collaborators."""
    return collaborators_from_service(svc)
