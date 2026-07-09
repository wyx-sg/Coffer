"""Legacy path-derived stores are adopted under the portable id
(spec 007 FR-004a, ADR-043) — merge-based, boot- and resolve-time."""

from __future__ import annotations

import pathlib

import pytest
import pytest_asyncio

import coffer.infrastructure.knowledge  # noqa: F401 — register ORM + FTS5 DDL
from coffer.application.audit_service import AuditService
from coffer.application.memory.consolidate import StoreConsolidator
from coffer.application.memory.kind import make_memory_kind
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

#: A portable id in valid Crockford base32 (no I/L/O/U), as project_identity emits.
PORTABLE = "0123456789ABCDEFGHJKMNPQRS"


def _portable_id(_root: str) -> str:
    return PORTABLE


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
    from coffer.application.memory.sync import MemoryReconciler
    from coffer.surfaces.http.wiring import build_substrate

    documents, retrieval, reindexer = build_substrate(sm)
    reconciler = MemoryReconciler(documents=documents, retrieval=retrieval, reindexer=reindexer)

    project_root = tmp_path / "repo"
    project_root.mkdir()

    def fake_git_root(cwd: str):  # type: ignore[no-untyped-def]
        p = pathlib.Path(cwd)
        return project_root if str(p).startswith(str(project_root)) else None

    adopter = StoreConsolidator(
        resources=resources,
        reconciler=reconciler,
        roots=roots,
        labels=labels,
        store_dir=paths.memory_store_dir,
        git_root=fake_git_root,
        project_ulid=_portable_id,
    )

    async def migrate_store(legacy_id: str, new_id: str, root: str) -> None:
        await adopter.adopt(project_store_name(legacy_id), project_store_name(new_id), root)

    resolver = ScopeResolver(
        resources=resources,
        git_root=fake_git_root,
        project_ulid=_portable_id,
        store_dir=paths.memory_store_dir,
        record_project_root=roots.set,
        legacy_project_ulid=project_ulid,
        migrate_store=migrate_store,
    )
    try:
        yield resolver, adopter, resources, roots, labels, project_root
    finally:
        await engine.dispose()


async def _provision_legacy(resources, roots, labels, project_root):  # type: ignore[no-untyped-def]
    legacy_scope = ScopeResolver(
        resources=resources,
        git_root=lambda cwd: project_root,
        project_ulid=project_ulid,
        store_dir=paths.memory_store_dir,
        record_project_root=roots.set,
    )
    legacy = await legacy_scope.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    legacy_dir = paths.memory_store_dir(legacy.project_id)
    (legacy_dir / "knowledge").mkdir(parents=True, exist_ok=True)
    (legacy_dir / "knowledge" / "fact.md").write_text("remembered\n", encoding="utf-8")
    await labels.set(project_store_name(legacy.project_id), "我的项目")
    return legacy.project_id


@pytest.mark.acceptance(
    spec="007-memory", scenario="project memory follows the repository across checkout paths"
)
async def test_legacy_store_adopted_under_portable_id(wired) -> None:  # type: ignore[no-untyped-def]
    resolver, _adopter, resources, roots, labels, project_root = wired
    legacy_id = await _provision_legacy(resources, roots, labels, project_root)
    legacy_name = project_store_name(legacy_id)

    resolved = await resolver.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    assert resolved.project_id == PORTABLE
    new_name = project_store_name(PORTABLE)

    merged = paths.memory_store_dir(PORTABLE) / "knowledge" / "fact.md"
    assert merged.read_text() == "remembered\n"
    assert await roots.get(new_name) == str(project_root)
    assert await labels.get(new_name) == "我的项目"
    names = {r.name for r in await resources.list(kind="memory")}
    assert new_name in names
    assert legacy_name not in names

    again = await resolver.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    assert again.project_id == PORTABLE


async def test_surviving_legacy_store_merges_even_when_portable_exists(wired) -> None:  # type: ignore[no-untyped-def]
    """The second-machine case: the portable store arrived via sync while this
    machine's own legacy store still holds its facts (review #287 finding 3)."""
    resolver, _adopter, resources, roots, labels, project_root = wired
    # Portable store already present (as if imported by sync).
    await resources.register(
        "memory",
        project_store_name(PORTABLE),
        {},
        "sync",
        allow_lifecycle_kind=True,
    )
    portable_dir = paths.memory_store_dir(PORTABLE) / "knowledge"
    portable_dir.mkdir(parents=True, exist_ok=True)
    (portable_dir / "fact-from-a.md").write_text("from A\n", encoding="utf-8")

    legacy_id = await _provision_legacy(resources, roots, labels, project_root)
    legacy_name = project_store_name(legacy_id)

    await resolver.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    # Both machines' facts coexist in the portable store; the legacy is retired.
    assert (portable_dir / "fact-from-a.md").read_text() == "from A\n"
    assert (portable_dir / "fact.md").read_text() == "remembered\n"
    names = {r.name for r in await resources.list(kind="memory")}
    assert legacy_name not in names


async def test_boot_consolidator_converges_and_stays_stable(wired) -> None:  # type: ignore[no-untyped-def]
    """The boot pass adopts legacy roots rows under the portable id and a
    second run is a no-op — no boot-time ping-pong (review #287 blocker 1)."""
    _resolver, adopter, resources, roots, labels, project_root = wired
    await _provision_legacy(resources, roots, labels, project_root)

    report = await adopter.run()
    assert report.changed
    names = {r.name for r in await resources.list(kind="memory")}
    assert project_store_name(PORTABLE) in names

    second = await adopter.run()
    assert not second.changed  # converged: nothing merges back


async def test_fresh_project_provisions_directly_no_migration(wired) -> None:  # type: ignore[no-untyped-def]
    resolver, _adopter, resources, _roots, _labels, project_root = wired
    resolved = await resolver.resolve(scope=MemoryScope.PROJECT, cwd=str(project_root))
    assert resolved.project_id == PORTABLE
    names = {r.name for r in await resources.list(kind="memory")}
    assert project_store_name(project_ulid(str(project_root))) not in names
