"""Integration: a project store records its originating project root (finding #10).

A per-project store is keyed by a one-way ULID of its git-root, so the path is
not recoverable from the name. The ScopeResolver records ``store_name ->
project_root`` at provisioning time so the surface can echo it back; the global
store has no project root.
"""

from __future__ import annotations

import pathlib

import pytest_asyncio

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.application.audit_service import AuditService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.scope import ScopeResolver, project_store_name
from coffer.application.resource_service import ResourceService
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.scope_fs import project_ulid
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


@pytest_asyncio.fixture
async def wired(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService({}, SqlAlchemyResourceRepo(sm), audit)
    roots = ProjectRootRepo(sm)

    project_root = tmp_path / "repo"
    project_root.mkdir()

    def fake_git_root(cwd: str):  # type: ignore[no-untyped-def]
        p = pathlib.Path(cwd)
        return project_root if str(p).startswith(str(project_root)) else None

    scope = ScopeResolver(
        resources=resources,
        git_root=fake_git_root,
        project_ulid=project_ulid,
        store_dir=paths.memory_store_dir,
        record_project_root=roots.set,
    )
    # The scope resolver provisions the store Resource on resolve → needs the
    # kind registered. ``cleanup_store`` (the only place ``service`` is used) is
    # never invoked in these tests, so a ``None`` service is fine.
    resources._kinds["memory"] = make_memory_kind(None)  # type: ignore[attr-defined,arg-type]
    try:
        yield scope, roots, project_root
    finally:
        await engine.dispose()


async def test_resolving_project_scope_records_root(wired) -> None:
    scope, roots, project_root = wired
    resolved = await scope.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root / "src"))
    store_name = project_store_name(resolved.project_id)
    assert await roots.get(store_name) == str(project_root)


async def test_global_scope_has_no_project_root(wired) -> None:
    scope, roots, _ = wired
    await scope.resolve(scope=MemoryScope.GLOBAL, cwd=None)
    assert await roots.get("global") is None


async def test_project_root_repo_upsert_is_idempotent(wired) -> None:
    _, roots, _ = wired
    await roots.set("project-X", "/a/b")
    await roots.set("project-X", "/c/d")  # overwrite
    assert await roots.get("project-X") == "/c/d"
