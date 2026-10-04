"""The ``config_backups`` retention policy over ``~/.coffer/config-backups`` (spec
resource-framework "Retain config backups on an adjustable policy")."""

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


def _backup(path: Path, age_days: float) -> Path:
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
def backups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path / ".coffer" / "config-backups"


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="old config backups are swept but each file's newest is kept",
)
@pytest.mark.asyncio
async def test_old_backups_are_swept_but_each_files_newest_is_kept(
    tmp_path: Path, backups: Path
) -> None:
    first = backups / "settings.json-aaaaaaaaaaaa"
    second = backups / "config.toml-bbbbbbbbbbbb"
    gone = [
        _backup(first / "20260825T000000000000Z.json", 40),
        _backup(first / "20260830T000000000000Z.json", 35),
        _backup(second / "20260705T000000000000Z.toml", 90),
    ]
    kept = [
        _backup(first / "20261002T000000000000Z.json", 2),
        _backup(second / "20260805T000000000000Z.toml", 60),
    ]
    svc, engine = await _service(tmp_path)
    try:
        policy = next(p for p in await svc.list_policies() if p.name == "config_backups")
        assert policy.retention_days == 30
        result = await svc.prune(now=NOW)
    finally:
        await engine.dispose()
    assert result["config_backups"] == 3
    assert not any(p.exists() for p in gone)
    assert all(p.exists() for p in kept)


@pytest.mark.acceptance(
    spec="resource-framework", scenario="config backups kept forever are never swept"
)
@pytest.mark.asyncio
async def test_config_backups_kept_forever_are_never_swept(tmp_path: Path, backups: Path) -> None:
    files = [
        _backup(backups / "a.json-aaaaaaaaaaaa" / "1.json", 400),
        _backup(backups / "a.json-aaaaaaaaaaaa" / "2.json", 500),
    ]
    svc, engine = await _service(tmp_path)
    try:
        await svc.set_retention("config_backups", None, actor="t")
        result = await svc.prune(now=NOW)
    finally:
        await engine.dispose()
    assert result["config_backups"] == 0
    assert all(p.exists() for p in files)


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the config backups preview counts files and deletes none",
)
@pytest.mark.asyncio
async def test_the_config_backups_preview_counts_files_and_deletes_none(
    tmp_path: Path, backups: Path
) -> None:
    folder = backups / "a.json-aaaaaaaaaaaa"
    files = [_backup(folder / f"{age:02d}.json", age) for age in (1, 3, 10, 20, 40)]
    svc, engine = await _service(tmp_path)
    try:
        assert await svc.preview("config_backups", 7, now=NOW) == (5, 3)
    finally:
        await engine.dispose()
    assert all(f.exists() for f in files)


@pytest.mark.asyncio
async def test_a_sweep_keeps_a_lone_old_backup_the_root_and_symlinks(
    tmp_path: Path, backups: Path
) -> None:
    # A folder whose only file is old keeps it (the newest); the root and symlinks stay.
    only = _backup(backups / "a.json-aaaaaaaaaaaa" / "1.json", 400)
    outside = tmp_path / "outside"
    behind = _backup(outside / "old.txt", 60)
    (backups / "link").symlink_to(outside, target_is_directory=True)
    svc, engine = await _service(tmp_path)
    try:
        result = await svc.prune("config_backups", now=NOW)
    finally:
        await engine.dispose()
    assert result == {"config_backups": 0}
    assert only.exists() and behind.exists()
    assert backups.is_dir() and (backups / "link").is_symlink()
