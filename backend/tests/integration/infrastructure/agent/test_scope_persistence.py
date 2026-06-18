"""Integration tests for AgentMcpScopeRepo against a real temp SQLite (ADR-026).

The scope tables FK→``resources.id`` with ``ON DELETE CASCADE``; the engine
factory enables ``PRAGMA foreign_keys = ON`` so the cascade is enforced here.
We seed real agent + mcp_server resource rows via the resource repo so the FK
targets exist, then drive the scope repo directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.agent.scope_persistence import AgentMcpScopeRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyResourceRepo


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _resource(kind: str, name: str) -> Resource:
    return Resource(
        id=0,
        kind=kind,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=_now(),
        updated_at=_now(),
    )


async def _setup(tmp_path):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    res_repo = SqlAlchemyResourceRepo(sm)
    agent = await res_repo.create(_resource("agent", "cc"))
    fs = await res_repo.create(_resource("mcp_server", "fs"))
    git = await res_repo.create(_resource("mcp_server", "git"))
    return AgentMcpScopeRepo(sm), res_repo, agent, fs, git, engine


@pytest.mark.asyncio
async def test_no_row_is_none_mode(tmp_path):
    repo, _res, agent, _fs, _git, engine = await _setup(tmp_path)
    try:
        # A brand-new agent has no scope row -> mode None (treated as auto).
        assert await repo.get_mode(agent.id) is None
        assert await repo.get_allowed_server_ids(agent.id) == set()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_set_get_mode_round_trips(tmp_path):
    repo, _res, agent, fs, _git, engine = await _setup(tmp_path)
    try:
        await repo.set(agent.id, "selected", [fs.id])
        assert await repo.get_mode(agent.id) == "selected"
        assert await repo.get_allowed_server_ids(agent.id) == {fs.id}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_allowlist_replaced_on_reset(tmp_path):
    repo, _res, agent, fs, git, engine = await _setup(tmp_path)
    try:
        await repo.set(agent.id, "selected", [fs.id, git.id])
        assert await repo.get_allowed_server_ids(agent.id) == {fs.id, git.id}
        # Re-set replaces (not merges) the allowlist.
        await repo.set(agent.id, "selected", [git.id])
        assert await repo.get_allowed_server_ids(agent.id) == {git.id}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_empty_selected_distinct_from_auto(tmp_path):
    repo, _res, agent, _fs, _git, engine = await _setup(tmp_path)
    try:
        # selected with an empty allowlist: mode persists, allowlist is empty —
        # this is NOT the same as auto (no row / mode None).
        await repo.set(agent.id, "selected", [])
        assert await repo.get_mode(agent.id) == "selected"
        assert await repo.get_allowed_server_ids(agent.id) == set()
        # Switching to auto clears the mode marker to 'auto'.
        await repo.set(agent.id, "auto", [])
        assert await repo.get_mode(agent.id) == "auto"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_agent_cascades_scope_rows(tmp_path):
    repo, res_repo, agent, fs, git, engine = await _setup(tmp_path)

    try:
        await repo.set(agent.id, "selected", [fs.id, git.id])
        assert await repo.get_allowed_server_ids(agent.id) == {fs.id, git.id}
        # Deleting the agent resource cascades to both scope tables.
        await res_repo.delete(ResourceRef("agent", "cc"))
        assert await repo.get_mode(agent.id) is None
        assert await repo.get_allowed_server_ids(agent.id) == set()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleting_server_cascades_allowlist_row(tmp_path):
    repo, res_repo, agent, fs, git, engine = await _setup(tmp_path)

    try:
        await repo.set(agent.id, "selected", [fs.id, git.id])
        # Deleting one server resource removes only its allowlist entry.
        await res_repo.delete(ResourceRef("mcp_server", "fs"))
        assert await repo.get_allowed_server_ids(agent.id) == {git.id}
        # The agent's mode row is untouched.
        assert await repo.get_mode(agent.id) == "selected"
    finally:
        await engine.dispose()
