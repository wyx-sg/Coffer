"""Renaming a resource is an ordinary edit.

See spec resource-framework "Treat a resource's name as a mutable label".

The point of the identity change is that a rename costs nothing: the row keeps
its uid, so every reference to it — a kind-owned table's foreign key, the audit
trail, the credential its config cites — keeps pointing at the same thing and
nothing has to be rewritten. This file asserts that by renaming a resource that
has one of each and checking that none of them moved.

``mcp_capability_preferences`` stands in for "a table the kind owns". It is
imported for its side effect on ``Base.metadata`` and then written directly:
going through the MCP service would test the MCP service, and what is under
test here is that a rename does not disturb a row joined by the integer id.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import text

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError, ResourceAlreadyExists
from coffer.domain.resource import Kind
from coffer.domain.scope import Scope
from coffer.infrastructure.mcp.persistence import (  # noqa: F401  (registers the table)
    MCPCapabilityPreferenceModel,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)


class _Config(BaseModel):
    credential_ref: str = ""


def _cited(config: dict) -> dict[str, str]:
    ref = config.get("credential_ref")
    return {"token": ref} if isinstance(ref, str) and ref else {}


class _Store:
    """The smallest credential store the service will talk to."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.values.get(ref)

    def exists(self, ref: str) -> bool:
        return ref in self.values

    def delete(self, ref: str) -> None:
        self.values.pop(ref, None)


async def _service(tmp_path, *, on_rename=None):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    kinds = {
        "thing": Kind(
            name="thing",
            display_name="Thing",
            config_schema=_Config,
            supports_scope=True,
            credential_ref_extractor=_cited,
            on_rename=on_rename,
        )
    }
    store = _Store()
    store.values["thing/secret"] = "s3cret"
    svc = ResourceService(
        kinds=kinds,
        repo=SqlAlchemyResourceRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
        credentials=store,
    )
    return svc, AuditService(SqlAlchemyAuditRepo(sm)), store, engine, sm


@pytest.mark.acceptance(
    spec="resource-framework", scenario="renaming a resource is an ordinary edit"
)
async def test_rename_moves_the_label_and_nothing_else(tmp_path):
    svc, audit, store, engine, sm = await _service(tmp_path)
    try:
        created = await svc.register(
            kind="thing",
            name="before",
            config={"credential_ref": "thing/secret"},
            actor="test",
        )
        await svc.update_scope(created.uid, Scope(agents=["agent-uid-1"]), actor="test")
        await svc.set_enabled(created.uid, False, actor="test")
        # A row in a table the kind owns, joined by the INTEGER id.
        async with sm() as session:
            await session.execute(
                text(
                    "INSERT INTO mcp_capability_preferences "
                    "(resource_id, capability_type, capability_key, enabled,"
                    " first_seen_at, last_seen_at) "
                    "VALUES (:rid, 'tool', 'search', 0, :ts, :ts)"
                ),
                {"rid": created.id, "ts": created.created_at},
            )
            await session.commit()

        renamed = await svc.rename(created.uid, "after", actor="test")

        # Same resource: the identity did not move, only the label.
        assert renamed.uid == created.uid
        assert renamed.id == created.id
        assert renamed.name == "after"

        # Reach untouched — a rename is not a decision about who may reach it.
        assert renamed.scope == Scope(agents=["agent-uid-1"])
        assert renamed.enabled is False

        # The credential is still in the store and still cited by this resource.
        assert store.exists("thing/secret")
        assert [r.uid for r in await svc.find_credential_citations("thing/secret")] == [created.uid]

        # The kind-owned row did not cascade away, because it was never keyed
        # on the name.
        async with sm() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT resource_id FROM mcp_capability_preferences "
                        "WHERE resource_id = :rid"
                    ),
                    {"rid": created.id},
                )
            ).fetchall()
        assert len(rows) == 1

        # The trail comes back whole, and the earlier rows still say what the
        # resource was called when they were written.
        trail = await audit.query(resource=renamed, limit=50)
        types = [e.event_type for e in trail]
        assert AuditEventType.RESOURCE_CREATED.value in types
        assert AuditEventType.RESOURCE_RENAMED.value in types
        created_row = next(
            e for e in trail if e.event_type == AuditEventType.RESOURCE_CREATED.value
        )
        assert created_row.resource_name == "before"
    finally:
        await engine.dispose()


async def test_rename_refuses_a_taken_label_and_an_invalid_one(tmp_path):
    svc, _audit, _store, engine, _sm = await _service(tmp_path)
    try:
        a = await svc.register(kind="thing", name="a", config={}, actor="test")
        await svc.register(kind="thing", name="b", config={}, actor="test")

        with pytest.raises(ResourceAlreadyExists):
            await svc.rename(a.uid, "b", actor="test")
        with pytest.raises(ConfigValidationError):
            await svc.rename(a.uid, "not a legal name", actor="test")

        # Neither refusal moved anything.
        assert (await svc.get(a.uid)).name == "a"
    finally:
        await engine.dispose()


async def test_a_failing_on_rename_hook_aborts_with_nothing_moved(tmp_path):
    """The hook is the kind's veto, and it fires BEFORE the row moves.

    A kind whose name is also a directory has to be able to stop a rename it
    cannot carry out, or the row ends up pointing at a directory that is not
    there.
    """
    calls: list[tuple[str, str]] = []

    def refuse(resource, new_name: str) -> None:
        calls.append((resource.name, new_name))
        raise OSError("the directory could not be moved")

    svc, _audit, _store, engine, _sm = await _service(tmp_path, on_rename=refuse)
    try:
        r = await svc.register(kind="thing", name="before", config={}, actor="test")
        with pytest.raises(OSError):
            await svc.rename(r.uid, "after", actor="test")
        assert calls == [("before", "after")]
        assert (await svc.get(r.uid)).name == "before"
    finally:
        await engine.dispose()


async def test_renaming_to_the_current_name_is_a_silent_no_op(tmp_path):
    svc, audit, _store, engine, _sm = await _service(tmp_path)
    try:
        r = await svc.register(kind="thing", name="same", config={}, actor="test")
        again = await svc.rename(r.uid, "same", actor="test")
        assert again.name == "same"
        trail = await audit.query(resource=r, limit=50)
        assert AuditEventType.RESOURCE_RENAMED.value not in [e.event_type for e in trail]
    finally:
        await engine.dispose()
