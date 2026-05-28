"""knowledge_base Kind wiring used by the composition root.

The `on_delete` hook is exposed as an *async* callable so ResourceService can
``await`` it: a previous fire-and-forget implementation scheduled the cleanup
with ``loop.create_task`` and let ``_rs.delete`` proceed in parallel — by the
time the background coroutine ran, the row was gone and the on-disk teardown
(rmtree of ``kb_dir``) could race with new operations on a re-created KB of
the same name (CODE22-007). Match the pattern used in
``application/skill/kind.py``.

The `on_update_config` hook enforces post-creation immutability of
``embedding_model`` (TEST22-021): swapping the embedding model after
documents have been ingested would invalidate every vector in the index,
so the service rejects the change up-front with a ``ConfigValidationError``.
"""

from __future__ import annotations

import contextlib
from typing import Any

from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.domain.errors import ConfigValidationError
from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.resource import Kind, ResourceRef


def make_kb_kind(service: KnowledgeBaseService) -> Kind:
    """Construct the `knowledge_base` Kind with lifecycle hooks.

    `on_delete`: drops the engine's per-KB state, removes `kb_documents` rows,
    and rmtrees the on-disk directory. Exceptions are suppressed so a
    half-broken KB still deletes its Resource row, but ResourceService
    *awaits* completion before removing the row (CODE22-007).

    `on_update_config`: rejects attempts to change `embedding_model` after
    creation. The vector index is built against a specific embedding model
    and swapping it would produce nonsensical similarity scores until every
    document is re-ingested (TEST22-021).
    """

    async def _on_delete(ref: ResourceRef) -> None:
        with contextlib.suppress(Exception):
            await service.cleanup_kb(ref.name)

    def _on_update_config(
        ref: ResourceRef,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        before_model = before.get("embedding_model")
        after_model = after.get("embedding_model")
        if before_model is not None and before_model != after_model:
            raise ConfigValidationError(
                f"embedding_model is immutable after KB creation "
                f"(was {before_model!r}, attempted {after_model!r}); "
                f"create a new knowledge base instead"
            )

    return Kind(
        name="knowledge_base",
        display_name="Knowledge Base",
        config_schema=KnowledgeBaseConfig,
        on_delete=_on_delete,
        on_update_config=_on_update_config,
    )
