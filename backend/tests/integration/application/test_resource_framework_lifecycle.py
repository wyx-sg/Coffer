"""Acceptance tests for the resource framework's creation seam and delete path.

Both run the real ``ResourceService`` over a temporary SQLite database; the
kind-agnostic create route is exercised through the real FastAPI router.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from typer.main import get_command

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Kind, Resource
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.cli.resource_cmd import app as resource_cli
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.resource_routes import router as resource_router


class _Config(BaseModel):
    foo: int


class _SecretConfig(BaseModel):
    secret_ref: str


async def _engine(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="refuse a generic create for a kind that owns its creation",
)
async def test_generic_create_refuses_a_kind_that_owns_its_creation(tmp_path):
    engine = await _engine(tmp_path)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    svc = ResourceService(
        kinds={
            "owned": Kind(
                name="owned",
                display_name="Owned",
                config_schema=_Config,
                generic_create_allowed=False,
            ),
        },
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(resource_router)
    app.dependency_overrides[get_resource_service] = lambda: svc
    set_active_token("test-token")
    try:
        async with AsyncClient(
            transport=ASGITransport(app),
            base_url="http://t",
            headers={"X-Coffer-Token": "test-token"},
        ) as c:
            r = await c.post(
                "/api/v1/resources",
                json={"kind": "owned", "name": "x", "config": {"foo": 1}},
            )
            assert r.status_code == 409, r.text
            assert r.json()["error"]["code"] == "GENERIC_CREATE_NOT_ALLOWED"

            listed = await c.get("/api/v1/resources")
            assert listed.status_code == 200
            assert listed.json()["resources"] == []
        assert await audit.query() == []

        # The kind's own surface can still create it — the seam is per kind.
        own = await svc.register("owned", "x", {"foo": 1}, "cli", allow_lifecycle_kind=True)
        assert own.name == "x"
    finally:
        await engine.dispose()

    commands = set(get_command(resource_cli).commands)  # type: ignore[attr-defined]
    assert "create" not in commands
    assert {"list", "show", "enable", "disable", "delete"} <= commands


class _FailingReleaseStore:
    """Holds the credential but refuses to delete it — recording each attempt,
    so a delete path that never tries the release cannot pass as "the release
    failed and the delete still completed"."""

    def __init__(self) -> None:
        self.store = {"only-mine": "value"}
        self.delete_calls: list[str] = []

    def get(self, ref: str) -> str | None:
        return self.store.get(ref)

    def exists(self, ref: str) -> bool:
        return ref in self.store

    def delete(self, ref: str) -> None:
        self.delete_calls.append(ref)
        raise RuntimeError("keychain unavailable")


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="deleting a resource runs its kind's cleanup and keeps its history",
)
async def test_delete_runs_cleanup_keeps_history_and_aborts_on_hook_failure(tmp_path):
    engine = await _engine(tmp_path)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    seen_during_hook: list[str] = []
    fail_hook = {"on": False}
    svc: ResourceService
    creds = _FailingReleaseStore()

    async def on_delete(resource: Resource) -> None:
        if fail_hook["on"]:
            raise RuntimeError("cleanup failed")
        # The resource must still resolve while its kind tears its half down.
        still_there = await svc.get(resource.uid)
        seen_during_hook.append(still_there.name)

    svc = ResourceService(
        kinds={
            "vault": Kind(
                name="vault",
                display_name="Vault",
                config_schema=_SecretConfig,
                credential_ref_extractor=lambda cfg: {"secret": cfg["secret_ref"]},
                on_delete=on_delete,
            ),
        },
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=creds,
    )
    try:
        created = await svc.register("vault", "a", {"secret_ref": "only-mine"}, "cli")
        await svc.set_enabled(created.uid, False, actor="cli")
        before = await audit.query(resource=created)
        assert len(before) >= 2

        # The credential release fails, yet the completed deletion is not an error.
        assert creds.delete_calls == []
        await svc.delete(created.uid, actor="cli")
        assert creds.delete_calls == ["only-mine"]  # the release really was attempted
        assert creds.store == {"only-mine": "value"}  # ...and really did fail
        assert seen_during_hook == ["a"]
        assert await svc.list() == []

        after = await audit.query(resource=created)
        before_ids = {(e.event_type, e.timestamp) for e in before}
        assert before_ids <= {(e.event_type, e.timestamp) for e in after}
        assert AuditEventType.RESOURCE_DELETED.value in {e.event_type for e in after}

        # A hook that raises aborts the deletion outright.
        fail_hook["on"] = True
        other = await svc.register("vault", "b", {"secret_ref": "only-mine"}, "cli")
        with pytest.raises(RuntimeError, match="cleanup failed"):
            await svc.delete(other.uid, actor="cli")
        assert (await svc.get(other.uid)).name == "b"
        assert creds.delete_calls == ["only-mine"]  # an aborted delete releases nothing
        deleted = await audit.query(event_type=AuditEventType.RESOURCE_DELETED.value)
        assert [e.resource_name for e in deleted] == ["a"]
    finally:
        await engine.dispose()
