"""The ``skill_data`` retention policy over ``~/.coffer/skill-data`` (spec
resource-framework "Retain skill working files on an adjustable policy")."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.infrastructure.chat import persistence_models as _chat_models  # noqa: F401
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http.app_mcp_composition import build_retention_service

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _file(path: Path, age_days: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    ts = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (ts, ts))
    return path


async def _service(tmp_path: Path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    svc = build_retention_service(sm, audit=AuditService(SqlAlchemyAuditRepo(sm)))
    await svc.initialize_defaults()
    return svc, engine


@pytest.fixture
def skill_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path / ".coffer" / "skill-data"


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="skill working files are swept recursively and kept thirty days by default",
)
@pytest.mark.asyncio
async def test_skill_data_is_swept_recursively_and_kept_thirty_days_by_default(
    tmp_path: Path, skill_data: Path
) -> None:
    old_nested = _file(skill_data / "alpha" / "logs" / "run.log", 31)
    recent = _file(skill_data / "alpha" / "journal.txt", 2)
    old_other = _file(skill_data / "beta" / "tmp.bin", 40)
    svc, engine = await _service(tmp_path)
    try:
        policy = next(p for p in await svc.list_policies() if p.name == "skill_data")
        assert policy.retention_days == 30
        result = await svc.prune(now=NOW)
    finally:
        await engine.dispose()
    assert result["skill_data"] == 2
    assert not old_nested.exists() and not old_other.exists()
    assert recent.exists()


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a sweep removes emptied folders but never the root or a symlink",
)
@pytest.mark.asyncio
async def test_a_sweep_removes_emptied_folders_but_never_the_root_or_a_symlink(
    tmp_path: Path, skill_data: Path
) -> None:
    _file(skill_data / "beta" / "deep" / "old.log", 60)
    outside = tmp_path / "outside"
    behind = _file(outside / "old.txt", 60)
    skill_data.mkdir(parents=True, exist_ok=True)
    (skill_data / "gamma").symlink_to(outside, target_is_directory=True)
    (skill_data / "link.txt").symlink_to(behind)
    svc, engine = await _service(tmp_path)
    try:
        result = await svc.prune("skill_data", now=NOW)
    finally:
        await engine.dispose()
    assert result == {"skill_data": 1}
    assert not (skill_data / "beta").exists()
    assert skill_data.is_dir()
    assert (skill_data / "gamma").is_symlink() and (skill_data / "link.txt").is_symlink()
    assert behind.exists()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="skill working files kept forever are never swept"
)
@pytest.mark.asyncio
async def test_skill_data_kept_forever_is_never_swept(tmp_path: Path, skill_data: Path) -> None:
    old = _file(skill_data / "alpha" / "old.log", 400)
    svc, engine = await _service(tmp_path)
    try:
        await svc.set_retention("skill_data", None, actor="t")
        result = await svc.prune(now=NOW)
    finally:
        await engine.dispose()
    assert result["skill_data"] == 0
    assert old.exists()


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the skill working files preview counts files and deletes none",
)
@pytest.mark.asyncio
async def test_the_skill_data_preview_counts_files_and_deletes_none(
    tmp_path: Path, skill_data: Path
) -> None:
    files = [
        _file(skill_data / "a" / "1.log", 1),
        _file(skill_data / "a" / "sub" / "2.log", 3),
        _file(skill_data / "b" / "3.log", 10),
        _file(skill_data / "b" / "4.log", 20),
    ]
    svc, engine = await _service(tmp_path)
    try:
        assert await svc.preview("skill_data", 7, now=NOW) == (4, 2)
    finally:
        await engine.dispose()
    assert all(f.exists() for f in files)
