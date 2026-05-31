"""memory Kind wiring used by the composition root.

The ``on_delete`` hook is exposed as an *async* callable so ResourceService
can ``await`` it: a previous fire-and-forget implementation scheduled the
cleanup with ``loop.create_task`` and let ``_rs.delete`` proceed in
parallel — by the time the background coroutine ran, the row was gone and
the on-disk teardown (rmtree of ``memory_store_dir``) could race with new
operations on a re-created store of the same name (regression noted in
PR #22 / CODE22-007). Match the pattern used in
``application/knowledge_base/kind.py``.

The ``on_update_config`` hook enforces post-creation immutability of
``embedding_model`` / ``llm_provider`` / ``llm_model``: mem0's vector index
is built against a specific embedding model and swapping any of these
fields after memories exist would invalidate similarity scores until every
memory is re-ingested. Reject the change up-front with a
``ConfigValidationError`` (CODE26-003).
"""

from __future__ import annotations

import contextlib
from typing import Any

from coffer.application.memory.service import MemoryService
from coffer.domain.errors import ConfigValidationError
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.resource import Kind, ResourceRef


def make_memory_kind(service: MemoryService) -> Kind:
    """Construct the `memory` Kind with lifecycle hooks."""

    async def _on_delete(ref: ResourceRef) -> None:
        with contextlib.suppress(Exception):
            await service.cleanup_store(ref.name)

    def _on_update_config(
        ref: ResourceRef,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        # Per spec 007 §FR (memory store config is immutable post-creation
        # except ``max_memory_chars``). Each immutable field is checked
        # independently so the error message names the specific drift.
        for field in ("embedding_model", "llm_provider", "llm_model"):
            before_val = before.get(field)
            after_val = after.get(field)
            if before_val is not None and before_val != after_val:
                raise ConfigValidationError(
                    f"{field} is immutable after memory store creation "
                    f"(was {before_val!r}, attempted {after_val!r}); "
                    f"create a new memory store instead"
                )

    return Kind(
        name="memory",
        display_name="Memory Store",
        config_schema=MemoryStoreConfig,
        on_delete=_on_delete,
        on_update_config=_on_update_config,
    )
