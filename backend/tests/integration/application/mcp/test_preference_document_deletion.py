"""Deleting a server's ``mcp-preferences`` document means "nothing disabled here".

Spec mcp-gateway, "Re-enable a server when its preference document is deleted",
driven through the real ``McpPreferenceSyncState`` over SQLite-backed resource
and preference repositories.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.sync_state import McpPreferenceSyncState
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)

_HTTP = {"transport": {"type": "http", "url": "http://127.0.0.1:9/mcp"}}


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="deleting a server's preference document re-enables everything on it",
)
@pytest.mark.asyncio
async def test_deleting_a_servers_document_re_enables_it_and_nothing_else(
    tmp_path: Path,
) -> None:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    try:
        rsvc = ResourceService(
            kinds={
                "mcp_server": Kind(
                    name="mcp_server", display_name="MCP Server", config_schema=MCPServerConfig
                )
            },
            repo=SqlAlchemyResourceRepo(sm),
            audit=AuditService(SqlAlchemyAuditRepo(sm)),
        )
        prefs = MCPCapabilityPreferenceRepo(sm)
        jira = await rsvc.register(kind="mcp_server", name="jira", config=_HTTP, actor="t")
        smart = await rsvc.register(kind="mcp_server", name="smart", config=_HTTP, actor="t")
        seen = datetime(2026, 1, 1, tzinfo=UTC)
        await prefs.insert(jira.id, "tool", "search", False, seen, seen)
        await prefs.insert(jira.id, "prompt", "summarize", False, seen, seen)
        await prefs.insert(jira.id, "tool", "write", True, seen, seen)
        await prefs.insert(smart.id, "tool", "deploy", False, seen, seen)

        state = McpPreferenceSyncState(rsvc, prefs)
        assert {rel for rel, _ in await state.export_docs()} == {jira.uid, smart.uid}

        await state.delete_docs([jira.uid, "0123456789abcdef0123456789abcdef"])

        jira_rows = await prefs.list_for(jira.id)
        assert {(p.capability_type, p.capability_key) for p in jira_rows} == {
            ("tool", "search"),
            ("prompt", "summarize"),
            ("tool", "write"),
        }, "the rows stay"
        assert all(p.enabled for p in jira_rows)
        assert all(p.last_seen_at.replace(tzinfo=UTC) == seen for p in jira_rows)

        smart_rows = await prefs.list_for(smart.id)
        assert [(p.capability_key, p.enabled) for p in smart_rows] == [("deploy", False)]

        docs = await state.export_docs()
        assert [rel for rel, _ in docs] == [smart.uid], "no document for a server with nothing off"
    finally:
        with suppress(asyncio.CancelledError, Exception):
            await engine.dispose()
