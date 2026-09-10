"""Scope-name ⇄ ``StoreRef`` plumbing for ``KnowledgeService``.

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling. These pure helpers translate between a resolved scope, its Resource
name (``global`` / ``project-<ulid>`` / a collection name), and the on-disk
``StoreRef`` the retrieval substrate takes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from coffer.application.knowledge.scope import is_project_scope_name
from coffer.domain.errors import MemoryStoreNotFound
from coffer.domain.knowledge.document import KIND_KNOWLEDGE, WORKSPACE_GLOBAL_PROJECT_ID
from coffer.domain.knowledge.retrieval import StoreRef
from coffer.domain.knowledge.scope import (
    PROJECT_SCOPE_PREFIX,
    KnowledgeScope,
    ResolvedScope,
    scope_kind_of,
)

ScopeDirFn = Callable[[str], Path]


def scope_name_for(resolved: ResolvedScope) -> str:
    """The Resource name backing a resolved scope."""
    return resolved.resource_name


def build_store_ref_for(scope_name: str, project_id: str, *, scope_dir: ScopeDirFn) -> StoreRef:
    """The retrieval ``StoreRef`` for a knowledge scope (kind + name + dir).

    ``scope_name`` / ``project_id`` are positional so the service can
    ``functools.partial`` the ``scope_dir`` away and hand the result to the
    write / recall dep bundles as a plain ``(name, project_id) -> StoreRef``."""
    return StoreRef(
        kind=KIND_KNOWLEDGE,
        resource_name=scope_name,
        project_id=project_id,
        docs_dir=str(scope_dir(scope_name)),
    )


def project_resolved_for_scope(scope_name: str, scope_dir: ScopeDirFn) -> ResolvedScope:
    """Recover a project ``ResolvedScope`` from its name (``project-<ulid>``
    encodes the ULID). ``global`` and named collections resolve through the
    ``ScopeResolver`` instead — the first provisions, the second must exist."""
    if not is_project_scope_name(scope_name):
        # Never strip a prefix that is not there — a mangled name would resolve
        # to a bogus on-disk dir.
        raise MemoryStoreNotFound(scope_name)
    return ResolvedScope(
        scope=KnowledgeScope.PROJECT,
        project_id=scope_name[len(PROJECT_SCOPE_PREFIX) :],
        store_dir=scope_dir(scope_name),
        resource_name=scope_name,
    )


def project_id_for(scope_name: str) -> str:
    """The ``documents.project_id`` a scope's rows carry, from its name alone.

    A project scope carries its ULID; ``global`` carries the installation-wide
    sentinel; a named collection carries its own name. Derived rather than
    stored so the two can never disagree.
    """
    kind = scope_kind_of(scope_name)
    if kind is KnowledgeScope.PROJECT:
        return scope_name[len(PROJECT_SCOPE_PREFIX) :]
    if kind is KnowledgeScope.GLOBAL:
        return WORKSPACE_GLOBAL_PROJECT_ID
    return scope_name


def store_ref_for(scope_name: str, *, scope_dir: ScopeDirFn) -> StoreRef:
    """The retrieval ``StoreRef`` for a scope from its name alone."""
    return build_store_ref_for(scope_name, project_id_for(scope_name), scope_dir=scope_dir)


def in_lane(path: str, lane: Path) -> bool:
    """Whether an indexed document's file belongs to a given lane.

    Both scanners — the note reconciler over ``notes/`` and the ingest scan
    over ``docs/`` — write rows under the same ``(kind, resource_name)``, so
    each prunes only what it owns. Without this they would delete each other's
    index rows on every pass.
    """
    try:
        return Path(path).is_relative_to(lane)
    except (OSError, ValueError):
        return False
