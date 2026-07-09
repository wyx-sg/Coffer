"""Legacy path-derived stores adopt the portable id on first resolve
(spec 007 FR-004a, ADR-043)."""

from __future__ import annotations

import pathlib

import pytest
import pytest_asyncio

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.application.audit_service import AuditService
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.migration import make_store_migrator
from coffer.application.memory.scope import ScopeResolver, project_store_name
from coffer.application.resource_service import ResourceService
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.scope_fs import project_ulid
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


def _portable_id(_root: str) -> str:
    return "01PORTABLEID0000000000000A"


@pytest_asyncio.fixture
async def wired(tmp_path: pathlib.Path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService({}, SqlAlchemyResourceRepo(sm), audit)
    resources._kinds["memory"] = make_memory_kind(None)  # type: ignore[attr-defined,arg-type]
    roots = ProjectRootRepo(sm)
    labels = StoreLabelRepo(sm)

    project_root = tmp_path / "repo"
    project_root.mkdir()

    def fake_git_root(cwd: str):  # type: ignore[no-untyped-def]
        p = pathlib.Path(cwd)
        return project_root if str(p).startswith(str(project_root)) else None

    def resolver(project_fn):  # type: ignore[no-untyped-def]
        return ScopeResolver(
            resources=resources,
            git_root=fake_git_root,
            project_ulid=project_fn,
            store_dir=paths.memory_store_dir,
            record_project_root=roots.set,
            legacy_project_ulid=project_ulid,
            migrate_store=make_store_migrator(resources, roots, labels, paths.memory_store_dir),
        )

    try:
        yield resolver, resources, roots, labels, project_root
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="007-memory", scenario="project memory follows the repository across checkout paths"
)
async def test_legacy_store_adopted_under_portable_id(wired) -> None:  # type: ignore[no-untyped-def]
    resolver, resources, roots, labels, project_root = wired

    # A pre-portable-identity store: provisioned under the path-derived id.
    legacy_scope = ScopeResolver(
        resources=resources,
        git_root=lambda cwd: project_root,
        project_ulid=project_ulid,
        store_dir=paths.memory_store_dir,
        record_project_root=roots.set,
    )
    legacy = await legacy_scope.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    legacy_name = project_store_name(legacy.project_id)
    legacy_dir = paths.memory_store_dir(legacy.project_id)
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "fact.md").write_text("remembered\n", encoding="utf-8")
    await labels.set(legacy_name, "我的项目")

    # First resolve under the portable identity adopts the store.
    resolved = await resolver(_portable_id).resolve(
        scope=MemoryScope.PROJECT, cwd=str(project_root)
    )
    assert resolved.project_id == _portable_id("")
    new_name = project_store_name(resolved.project_id)

    # Files, root mapping, and label carried over; old store gone.
    assert (paths.memory_store_dir(resolved.project_id) / "fact.md").read_text() == "remembered\n"
    assert not legacy_dir.exists()
    assert await roots.get(new_name) == str(project_root)
    assert await labels.get(new_name) == "我的项目"
    names = {r.name for r in await resources.list(kind="memory")}
    assert new_name in names
    assert legacy_name not in names

    # Second resolve is a no-op (already migrated).
    again = await resolver(_portable_id).resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    assert again.project_id == resolved.project_id


async def test_fresh_project_provisions_directly_no_migration(wired) -> None:  # type: ignore[no-untyped-def]
    resolver, resources, _roots, _labels, project_root = wired
    resolved = await resolver(_portable_id).resolve(
        scope=MemoryScope.PROJECT, cwd=str(project_root)
    )
    assert resolved.project_id == _portable_id("")
    names = {r.name for r in await resources.list(kind="memory")}
    assert project_store_name(project_ulid(str(project_root))) not in names
