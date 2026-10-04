"""The ``attachments`` retention policy over the channel media directory (spec
resource-framework "Retain attachments on an adjustable policy").

The real composition-root retention service over a throwaway database, with the
media directory resolved from ``HOME`` under ``tmp_path``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.infrastructure.channel.media_root import default_media_dir
from coffer.infrastructure.persistence import models as _models  # noqa: F401  (registers tables)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.http.app_mcp_composition import build_retention_service


def _media(name: str, *, age_days: int, now: datetime) -> Path:
    directory = default_media_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"x")
    stamp = (now - timedelta(days=age_days)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


async def _service(tmp_path: Path):  # type: ignore[no-untyped-def]
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    audit = AuditService(SqlAlchemyAuditRepo(session_maker(engine)))
    return engine, build_retention_service(session_maker(engine), audit=audit)


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="attachments are kept for thirty days unless the user chose otherwise",
)
async def test_full_prune_sweeps_channel_media_by_age(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    now = datetime.now(tz=UTC)
    stale = _media("old.jpg", age_days=31, now=now)
    fresh = _media("new.jpg", age_days=1, now=now)

    engine, svc = await _service(tmp_path)
    try:
        await svc.initialize_defaults()
        result = await svc.prune(now=now)
    finally:
        await engine.dispose()

    assert result["attachments"] == 1
    assert not stale.exists()
    assert fresh.exists()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a changed attachments window decides what is deleted"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="attachments kept forever are never swept"
)
async def test_attachments_policy_is_adjustable_and_kept_forever_skips_the_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    now = datetime.now(tz=UTC)
    stale = _media("old.jpg", age_days=10, now=now)

    engine, svc = await _service(tmp_path)
    try:
        await svc.initialize_defaults()
        policy = next(p for p in await svc.list_policies() if p.name == "attachments")
        assert policy.retention_days == 30
        assert await svc.preview("attachments", 7, now=now) == (1, 1)
        assert await svc.preview("attachments", 30, now=now) == (1, 0)

        await svc.set_retention("attachments", None, actor="t")
        assert (await svc.prune(now=now))["attachments"] == 0
        assert stale.exists()

        await svc.set_retention("attachments", 7, actor="t")
        assert (await svc.prune("attachments", now=now)) == {"attachments": 1}
        assert not stale.exists()
    finally:
        await engine.dispose()
