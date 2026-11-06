"""A session lists from the saved catalogue and starts a server only for a call.

ADR session-subprocess-model; spec mcp-gateway "Forward tools, resources and
prompts". Real fake_mcp_server processes; each session is its own supervisor
and discovery over one shared catalogue, as in the daemon.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.mcp.catalogue_store import McpCatalogueStore
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import MCPCapabilityPreferenceStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from tests.fixtures.keyring import install_in_memory_keyring
from tests.support.vault_stores import derived_sm, make_resource_repo

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _config(*tools: str) -> dict:  # type: ignore[type-arg]
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", *tools],
        },
    }


class _Counting(SubprocessSupervisor):
    spawns: list[str]

    async def _spawn_under_lock(self, entry, server_name):  # type: ignore[no-untyped-def]
        self.spawns.append(server_name)
        return await super()._spawn_under_lock(entry, server_name)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a session lists a server's tools without starting it"
)
async def test_a_session_lists_from_the_catalogue_and_starts_the_server_for_a_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_in_memory_keyring(monkeypatch)
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    rsvc = ResourceService(
        kinds={
            "mcp_server": Kind(
                name="mcp_server", display_name="MCP Server", config_schema=MCPServerConfig
            )
        },
        repo=make_resource_repo(),
        audit=AuditService(SqlAlchemyAuditRepo(session_maker(engine))),
    )
    await rsvc.register(kind="mcp_server", name="fs", config=_config("read_file"), actor="t")
    shared = derived_sm()
    prefs = MCPCapabilityPreferenceStore(shared)
    catalogue = McpCatalogueStore(shared)
    supervisors: list[_Counting] = []

    def session() -> tuple[CapabilityDiscovery, _Counting]:
        sup = _Counting(
            upstream_factory=build_upstream,
            resource_service=rsvc,
            secret_resolver=SecretResolver(KeyringAdapter()),
        )
        sup.spawns = []
        supervisors.append(sup)
        return CapabilityDiscovery(
            resource_service=rsvc, supervisor=sup, preferences=prefs, catalogue=catalogue
        ), sup

    try:
        # Never listed on this machine: the first session asks the server.
        first, first_sup = session()
        assert [t.original_name for t in await first.list_tools("fs")] == ["read_file"]
        assert await first.list_resources("fs") == []
        assert first_sup.spawns == ["fs"]

        # The next session answers from the catalogue and starts nothing...
        second, second_sup = session()
        tools = await second.list_tools("fs")
        assert [t.prefixed_name for t in tools] == ["fs__read_file"]
        assert tools[0].input_schema == (await first.list_tools("fs"))[0].input_schema
        assert await second.list_resources("fs") == []
        assert second_sup.spawns == []
        # ...until a call needs the server.
        conn = await second_sup.get_or_spawn("fs")
        await conn.request("tools/call", {"name": "read_file", "arguments": {}})
        assert second_sup.spawns == ["fs"]

        # A changed config is listed live again, under the new config.
        row = await rsvc.get_by_name("mcp_server", "fs")
        await rsvc.update_config(row.uid, _config("read_file", "write_file"), actor="t")
        third, third_sup = session()
        assert {t.original_name for t in await third.list_tools("fs")} == {
            "read_file",
            "write_file",
        }
        assert third_sup.spawns == ["fs"]
        fourth, fourth_sup = session()
        assert len(await fourth.list_tools("fs")) == 2
        assert fourth_sup.spawns == []
    finally:
        for sup in supervisors:
            await sup.dispose()
        await engine.dispose()
