"""Write-path orchestration for ``MemoryService`` — add / update / delete / clear.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These free functions own the full mutation pipeline: build / mutate a
``MemoryFact``, persist + reindex it (or remove it), then audit and fire the
change-notify hook. The service resolves the store first (scope + config +
store_ref) and delegates the mechanical work here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.retrieval import EmbeddingResolver, no_embedding
from coffer.application.memory.service_helpers import body_sha, derive_name, validate_fact
from coffer.application.memory.sync import MemoryReconciler
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.memory.fact import Actor, MemoryFact
from coffer.domain.memory.scope import ResolvedScope
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge.ids import new_ulid, slugify
from coffer.infrastructure.knowledge.paths import inbox_item_path
from coffer.infrastructure.memory.files import (
    FactFile,
    delete_fact_file,
    write_fact_file,
)

#: Post-write change hook installed by the composition root.
NotifyFn = Callable[[str], Awaitable[None]]
#: Builds a retrieval ``StoreRef`` (``store_name, project_id -> StoreRef``).
StoreRefFn = Callable[[str, str], StoreRef]


@dataclass(frozen=True)
class WriteDeps:
    """The collaborators every mutation needs, bundled by the service so the
    orchestrator call sites stay short. ``audit_and_notify`` records the audit
    event then fires the post-write change hook (every mutation ends this way)."""

    audit: AuditService
    reconciler: MemoryReconciler
    notify: NotifyFn
    store_ref: StoreRefFn
    # Resolves the GLOBAL embedding config (embedding is no longer per-store).
    embedding_resolver: EmbeddingResolver = no_embedding

    async def audit_and_notify(
        self,
        event: AuditEventType,
        *,
        store_name: str,
        actor: str,
        details: dict[str, object],
    ) -> None:
        await self.audit.record(
            event.value,
            ref=ResourceRef(KIND_MEMORY, store_name),
            actor=actor,
            details=details,
        )
        await self.notify(store_name)


def build_fact(
    *,
    name: str,
    description: str,
    body: str,
    actor: Actor,
    origin_session_id: str | None,
    max_fact_chars: int,
) -> MemoryFact:
    """Validate ``body`` and construct a fresh ``MemoryFact`` (id + timestamps)."""
    validate_fact(body, max_fact_chars)
    now = datetime.now(tz=UTC)
    return MemoryFact(
        id=new_ulid(),
        name=name.strip() or derive_name(body),
        description=description.strip() or derive_name(body),
        body=body,
        actor=actor,
        origin_session_id=origin_session_id,
        created_at=now,
        updated_at=now,
    )


def apply_fact_changes(
    fact: MemoryFact,
    *,
    new_body: str,
    new_name: str | None,
    new_description: str | None,
) -> MemoryFact:
    """Return a copy of ``fact`` with the supplied edits applied. ``None`` for an
    optional field leaves it unchanged (the REST/CLI edit-by-id path passes
    body only)."""
    changes: dict[str, object] = {
        "body": new_body,
        "updated_at": datetime.now(tz=UTC),
    }
    if new_name is not None and new_name.strip():
        changes["name"] = new_name.strip()
    if new_description is not None and new_description.strip():
        changes["description"] = new_description.strip()
    return dc_replace(fact, **changes)  # type: ignore[arg-type]


async def write_and_index(
    *,
    reconciler: MemoryReconciler,
    fact_path: Path,
    fact: MemoryFact,
    store_ref: StoreRef,
    config: MemoryStoreConfig,
    embedding_resolver: EmbeddingResolver,
) -> None:
    """Persist ``fact`` to ``fact_path`` and index it (no derived index)."""
    await asyncio.to_thread(write_fact_file, fact_path, fact)
    ff = FactFile(fact=fact, path=fact_path, content_sha256=body_sha(fact.body))
    embedding = await embedding_resolver() if config.vector_enabled else None
    await reconciler.index_one(store=store_ref, fact_file=ff, embedding=embedding)


def default_fact_path(store_dir: Path, fact: MemoryFact) -> Path:
    """The canonical on-disk path for a freshly-remembered item:
    ``<store_dir>/knowledge/inbox/<slug>-<id-tail>.md``."""
    return inbox_item_path(store_dir, f"{slugify(fact.name)}-{fact.id[-8:].lower()}")


async def delete_one(
    *,
    reconciler: MemoryReconciler,
    store_ref: StoreRef,
    fact_id: str,
    fact_path: Path,
) -> None:
    """Remove a single fact file + its index rows (no derived index)."""
    await asyncio.to_thread(delete_fact_file, fact_path)
    await reconciler.remove_one(store=store_ref, fact_id=fact_id)


async def clear_store(
    *,
    reconciler: MemoryReconciler,
    store_ref: StoreRef,
    files: dict[str, FactFile],
) -> int:
    """Remove every memory item under the store's ``knowledge/`` lane + their
    index rows; the store Resource (and ``handoff/``) is preserved. Returns the
    number of items cleared."""
    for fact_id, ff in files.items():
        await asyncio.to_thread(delete_fact_file, ff.path)
        await reconciler.remove_one(store=store_ref, fact_id=fact_id)
    return len(files)


async def add_new_fact(
    *,
    deps: WriteDeps,
    resolved: ResolvedScope,
    store_name: str,
    config: MemoryStoreConfig,
    name: str,
    description: str,
    body: str,
    actor: Actor,
    origin_session_id: str | None,
) -> MemoryFact:
    """Build, persist, index, audit, and notify for a brand-new fact in a
    resolved store. Shared by ``add_fact`` (scope→store) and
    ``add_fact_to_store`` (store-by-name)."""
    body = body.strip()
    fact = build_fact(
        name=name,
        description=description,
        body=body,
        actor=actor,
        origin_session_id=origin_session_id,
        max_fact_chars=config.max_fact_chars,
    )
    await write_and_index(
        reconciler=deps.reconciler,
        fact_path=default_fact_path(resolved.store_dir, fact),
        fact=fact,
        store_ref=deps.store_ref(store_name, resolved.project_id),
        config=config,
        embedding_resolver=deps.embedding_resolver,
    )
    await deps.audit_and_notify(
        AuditEventType.MEMORY_ADDED,
        store_name=store_name,
        actor=actor,
        details={"memory_id": fact.id, "scope": resolved.scope.value, "char_size": len(body)},
    )
    return fact


async def update_existing_fact(
    *,
    deps: WriteDeps,
    resolved: ResolvedScope,
    store_name: str,
    config: MemoryStoreConfig,
    existing: FactFile,
    new_body: str,
    actor: str,
    new_name: str | None = None,
    new_description: str | None = None,
) -> MemoryFact:
    """Apply edits to an existing fact, re-persist + reindex, audit, and notify."""
    new_body = new_body.strip()
    validate_fact(new_body, config.max_fact_chars)
    updated = apply_fact_changes(
        existing.fact,
        new_body=new_body,
        new_name=new_name,
        new_description=new_description,
    )
    await write_and_index(
        reconciler=deps.reconciler,
        fact_path=existing.path,
        fact=updated,
        store_ref=deps.store_ref(store_name, resolved.project_id),
        config=config,
        embedding_resolver=deps.embedding_resolver,
    )
    await deps.audit_and_notify(
        AuditEventType.MEMORY_UPDATED,
        store_name=store_name,
        actor=actor,
        details={"memory_id": existing.fact.id, "char_size": len(new_body)},
    )
    return updated


async def remove_fact(
    *,
    deps: WriteDeps,
    resolved: ResolvedScope,
    store_name: str,
    existing: FactFile,
    actor: str,
) -> None:
    """Delete a fact file + index rows, audit, notify."""
    await delete_one(
        reconciler=deps.reconciler,
        store_ref=deps.store_ref(store_name, resolved.project_id),
        fact_id=existing.fact.id,
        fact_path=existing.path,
    )
    await deps.audit_and_notify(
        AuditEventType.MEMORY_DELETED,
        store_name=store_name,
        actor=actor,
        details={"memory_id": existing.fact.id},
    )


async def clear_all_facts(
    *,
    deps: WriteDeps,
    resolved: ResolvedScope,
    store_name: str,
    files: dict[str, FactFile],
    actor: str,
) -> int:
    """Remove every fact in a store (keeping the Resource), audit, notify."""
    cleared = await clear_store(
        reconciler=deps.reconciler,
        store_ref=deps.store_ref(store_name, resolved.project_id),
        files=files,
    )
    await deps.audit_and_notify(
        AuditEventType.MEMORY_CLEARED,
        store_name=store_name,
        actor=actor,
        details={"cleared": cleared},
    )
    return cleared
