"""The memory substrate the reorg service is built from (spec 007).

Kept out of the service file (budget) and separated so each service has a
clear dependency manifest. Reuses ``OrganizerCollaborators`` directly since the
reorg service needs exactly the same field set.
"""

from __future__ import annotations

from coffer.application.knowledge.organizer_deps import (
    OrganizerCollaborators,
    collaborators_from_service,
)
from coffer.application.knowledge.service import KnowledgeService

# Reuse the same collaborator shape — the reorg service needs exactly the same
# fields (resolve_store, get_config, store_ref, documents, retrieval, reconciler,
# embedding_resolver). Alias to keep naming explicit.
ReorgCollaborators = OrganizerCollaborators


def reorg_collaborators_from_service(svc: KnowledgeService) -> ReorgCollaborators:
    """Project a live ``KnowledgeService`` onto the reorg's collaborators."""
    return collaborators_from_service(svc)
