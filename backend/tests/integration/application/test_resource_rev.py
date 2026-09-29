"""Every write to a resource bumps its revision and hints the reconciler.

Spec resource-framework "Carry a monotonic revision on every resource".
"""

from __future__ import annotations

import pathlib

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.reconcile.hints import HintingResourceRepo
from coffer.application.resource_service import ResourceService
from coffer.domain.reconcile import Changed
from coffer.domain.resource import Kind
from coffer.domain.scope import Scope
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo


class _Config(BaseModel):
    foo: int


async def _service(tmp_path: pathlib.Path) -> tuple[ResourceService, list[Changed]]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    hints: list[Changed] = []
    kinds = {
        "thing": Kind(
            name="thing", display_name="Thing", config_schema=_Config, supports_scope=True
        )
    }
    svc = ResourceService(
        kinds=kinds,
        repo=HintingResourceRepo(SqlAlchemyResourceRepo(sm), hints.append),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    return svc, hints


@pytest.mark.acceptance(
    spec="resource-framework", scenario="every write to a resource bumps its revision"
)
async def test_every_write_bumps_the_revision_and_hints_it(tmp_path: pathlib.Path) -> None:
    svc, hints = await _service(tmp_path)
    r = await svc.register(kind="thing", name="a", config={"foo": 1}, actor="cli")
    assert r.rev == 1
    await svc.update_config(r.uid, {"foo": 2}, actor="cli")
    await svc.set_enabled(r.uid, False, actor="cli")
    await svc.set_title(r.uid, "Shown", actor="cli")
    await svc.update_scope(r.uid, Scope(agents=["u1"]), actor="cli")
    await svc.rename(r.uid, "b", actor="cli")
    assert (await svc.get(r.uid)).rev == 6
    assert hints == [Changed("thing", r.uid, n) for n in range(1, 7)]

    await svc.delete(r.uid, actor="cli")
    assert hints[-1] == Changed("thing", r.uid, 7)


async def test_reads_never_hint(tmp_path: pathlib.Path) -> None:
    svc, hints = await _service(tmp_path)
    r = await svc.register(kind="thing", name="a", config={"foo": 1}, actor="cli")
    hints.clear()
    await svc.get(r.uid)
    await svc.list(kind="thing")
    await svc.find_by_name("thing", "a")
    assert hints == []


async def test_a_failing_hint_sink_never_fails_the_write(tmp_path: pathlib.Path) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    def _boom(_: Changed) -> None:
        raise RuntimeError("loop gone")

    svc = ResourceService(
        kinds={"thing": Kind(name="thing", display_name="Thing", config_schema=_Config)},
        repo=HintingResourceRepo(SqlAlchemyResourceRepo(sm), _boom),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    r = await svc.register(kind="thing", name="a", config={"foo": 1}, actor="cli")
    assert (await svc.update_config(r.uid, {"foo": 5}, actor="cli")).config == {"foo": 5}
