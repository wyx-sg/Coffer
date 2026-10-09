"""Renaming a resource is an ordinary edit.

See spec resource-framework "Treat a resource's name as a mutable label".

The point of the identity change is that a rename costs nothing: the file keeps
its uid, so every reference to it — reach, the audit trail, the secret its
config cites — keeps pointing at the same thing and nothing has to be
rewritten. This file asserts that by renaming a resource that has one of each
and checking that none of them moved.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError, ResourceAlreadyExists
from coffer.domain.resource import Kind
from coffer.domain.scope import Scope
from coffer.domain.vault.errors import VaultFileStale
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.vault.home import vault_root
from tests.support.vault_stores import make_resource_repo


class _Config(BaseModel):
    secret_ref: str = ""


def _cited(config: dict) -> dict[str, str]:
    ref = config.get("secret_ref")
    return {"token": ref} if isinstance(ref, str) and ref else {}


class _Store:
    """The smallest secret store the service will talk to."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self.values.get(ref)

    def exists(self, ref: str) -> bool:
        return ref in self.values

    def delete(self, ref: str) -> None:
        self.values.pop(ref, None)


async def _service(tmp_path, *, on_rename=None, on_delete=None):
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
            secret_ref_extractor=_cited,
            on_rename=on_rename,
            on_delete=on_delete,
        )
    }
    store = _Store()
    store.values["thing/secret"] = "s3cret"
    svc = ResourceService(
        kinds=kinds,
        repo=make_resource_repo(),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
        secrets=store,
    )
    return svc, AuditService(SqlAlchemyAuditRepo(sm)), store, engine, sm


@pytest.mark.acceptance(
    spec="resource-framework", scenario="renaming a resource is an ordinary edit"
)
@pytest.mark.acceptance(
    spec="resource-framework", scenario="a rename and a knowledge edit say what changed"
)
async def test_rename_moves_the_label_and_nothing_else(tmp_path):
    svc, audit, store, engine, _sm = await _service(tmp_path)
    try:
        created = await svc.register(
            kind="thing",
            name="before",
            config={"secret_ref": "thing/secret"},
            actor="test",
        )
        await svc.update_scope(created.uid, Scope(agents=["agent-uid-1"]), actor="test")
        await svc.set_enabled(created.uid, False, actor="test")
        renamed = await svc.rename(created.uid, "after", actor="test")

        # Same resource: the identity did not move, only the label.
        assert renamed.uid == created.uid
        assert renamed.name == "after"

        # Reach untouched — a rename is not a decision about who may reach it.
        assert renamed.scope == Scope(agents=["agent-uid-1"])
        assert renamed.enabled is False

        # The secret is still in the store and still cited by this resource.
        assert store.exists("thing/secret")
        assert [r.uid for r in await svc.find_secret_citations("thing/secret")] == [created.uid]

        # The trail comes back whole, and the earlier rows still say what the
        # resource was called when they were written.
        trail = await audit.query(resource=renamed, limit=50)
        types = [e.event_type for e in trail]
        assert AuditEventType.RESOURCE_CREATED.value in types
        assert AuditEventType.RESOURCE_RENAMED.value in types
        renamed_row = next(
            e for e in trail if e.event_type == AuditEventType.RESOURCE_RENAMED.value
        )
        # The row says what the label was and became, not only that it moved.
        assert renamed_row.details["from"] == "before"
        assert renamed_row.details["to"] == "after"
        assert renamed_row.details["moved_folder"] is False
        assert "title" in renamed_row.details
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


def _edit_on_disk(svc, uid: str) -> None:
    """A person's edit to the resource's file that is not committed yet."""
    path = vault_root() / svc._repo.files.by_uid()[uid].path
    path.write_bytes(path.read_bytes() + b" ")


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kind whose name is a directory moves it with the rename"
)
async def test_a_file_that_cannot_be_written_is_refused_before_the_hook_moves_anything(tmp_path):
    moved: list[tuple[str, str]] = []

    def on_rename(resource, new_name):
        moved.append((resource.name, new_name))

    svc, _audit, _store, engine, _sm = await _service(tmp_path, on_rename=on_rename)
    try:
        a = await svc.register(kind="thing", name="a", config={}, actor="test")
        _edit_on_disk(svc, a.uid)
        with pytest.raises(VaultFileStale):
            await svc.rename(a.uid, "b", actor="test")
        assert moved == []
        assert (await svc.get(a.uid)).name == "a"
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a kind whose name is a directory moves it with the rename"
)
async def test_a_write_that_fails_after_the_hook_moves_the_directory_back(tmp_path):
    moved: list[tuple[str, str]] = []

    def on_rename(resource, new_name):
        moved.append((resource.name, new_name))

    svc, _audit, _store, engine, _sm = await _service(tmp_path, on_rename=on_rename)
    try:
        a = await svc.register(kind="thing", name="a", config={}, actor="test")

        async def refuse(uid: str, new_name: str):
            raise VaultFileStale("resources/x.json", "raced")

        svc._repo.rename = refuse  # the write fails after the pre-checks passed
        with pytest.raises(VaultFileStale):
            await svc.rename(a.uid, "b", actor="test")
        assert moved == [("a", "b"), ("b", "a")]
    finally:
        await engine.dispose()


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a file that cannot be written stops a deletion before the cleanup runs",
)
async def test_a_file_that_cannot_be_removed_is_refused_before_the_cleanup_runs(tmp_path):
    cleaned: list[str] = []
    svc, _audit, _store, engine, _sm = await _service(
        tmp_path, on_delete=lambda r: cleaned.append(r.name)
    )
    try:
        a = await svc.register(kind="thing", name="a", config={}, actor="test")
        _edit_on_disk(svc, a.uid)
        with pytest.raises(VaultFileStale):
            await svc.delete(a.uid, actor="test")
        assert cleaned == []
        assert (await svc.get(a.uid)).name == "a"
    finally:
        await engine.dispose()
