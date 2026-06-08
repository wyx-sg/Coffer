"""Store-name ⇄ scope plumbing for ``MemoryService``.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These pure helpers translate between a resolved scope, a store's
Resource name (``global`` / ``project-<ulid>``), and the on-disk
``StoreRef``. The global store's *provisioning* stays in the service /
``ScopeResolver`` (it has a side effect); only the name-encoding logic lives
here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coffer.application.memory.scope import GLOBAL_STORE_NAME, project_store_name
from coffer.domain.knowledge.document import KIND_MEMORY
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.memory.scope import MemoryScope, ResolvedScope

StoreDirFn = Callable[[str], Path]


def store_name_for(resolved: ResolvedScope) -> str:
    """The Resource name backing a resolved scope."""
    if resolved.is_global:
        return GLOBAL_STORE_NAME
    return project_store_name(resolved.project_id)


def build_store_ref_for(store_name: str, project_id: str, *, store_dir: StoreDirFn) -> StoreRef:
    """The retrieval ``StoreRef`` for a memory store (kind + name + docs dir).

    ``store_name`` / ``project_id`` are positional so the service can
    ``functools.partial`` the ``store_dir`` away and hand the result to the
    write / recall dep bundles as a plain ``(name, project_id) -> StoreRef``."""
    return StoreRef(
        kind=KIND_MEMORY,
        resource_name=store_name,
        project_id=project_id,
        docs_dir=str(store_dir(project_id)),
    )


def project_resolved_for_store(store_name: str, store_dir: StoreDirFn) -> ResolvedScope:
    """Recover a project ``ResolvedScope`` from its store name (``project-<ulid>``
    encodes the ULID). The global store is resolved via the ``ScopeResolver``
    instead, because it provisions on first access."""
    project_id = store_name[len("project-") :]
    return ResolvedScope(
        scope=MemoryScope.PROJECT,
        project_id=project_id,
        store_dir=store_dir(project_id),
    )
