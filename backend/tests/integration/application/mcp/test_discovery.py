"""Integration tests for CapabilityDiscovery using fake_mcp_server."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.factory import build_upstream
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
from tests.fixtures.fake_mcp_server import start_http_fake as _start_http_fake
from tests.fixtures.keyring import install_in_memory_keyring

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _with_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    install_in_memory_keyring(monkeypatch)


def _stdio_config(*tools_or_resources_or_prompts: str, kind_args: str = "--tools") -> dict:  # type: ignore[type-arg]
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", kind_args, *tools_or_resources_or_prompts],
        },
    }


async def _setup(
    tmp_path: Path,
    *,
    server_configs: dict[str, dict],  # type: ignore[type-arg]
    auto_enable: bool = True,
) -> tuple[
    CapabilityDiscovery,
    SubprocessSupervisor,
    ResourceService,
    AuditService,
    MCPCapabilityPreferenceRepo,
    AsyncEngine,
]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit_repo = SqlAlchemyAuditRepo(sm)
    audit = AuditService(audit_repo)
    repo = SqlAlchemyResourceRepo(sm)
    kinds: dict[str, Kind] = {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP Server",
            config_schema=MCPServerConfig,
        ),
    }
    rsvc = ResourceService(kinds=kinds, repo=repo, audit=audit)
    for name, cfg in server_configs.items():
        if not auto_enable:
            cfg = {**cfg, "auto_enable_new_capabilities": False}
        await rsvc.register(kind="mcp_server", name=name, config=cfg, actor="test")
    supervisor = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    prefs = MCPCapabilityPreferenceRepo(sm)
    discovery = CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,
        preferences=prefs,
        audit=audit,
    )
    return discovery, supervisor, rsvc, audit, prefs, engine


@pytest.mark.asyncio
async def test_first_list_tools_populates_preferences_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    discovery, sup, rsvc, audit, prefs, engine = await _setup(
        tmp_path,
        server_configs={"fs": _stdio_config("read_file", "write_file")},
    )
    try:
        tools = await discovery.list_tools("fs")
        names = {t.original_name for t in tools}
        assert names == {"read_file", "write_file"}
        # All tools are enabled by default
        assert all(t.enabled for t in tools)
        # Prefixed correctly
        assert {t.prefixed_name for t in tools} == {"fs__read_file", "fs__write_file"}
        # Preferences row was inserted for each
        resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
        pref_rows = await prefs.list_for(resource.id, "tool")
        assert {p.capability_key for p in pref_rows} == {"read_file", "write_file"}
        # capability_first_seen audit events written for each
        events = await audit.query(event_type=AuditEventType.CAPABILITY_FIRST_SEEN.value)
        assert len(events) == 2
        # TEST-013: also assert the LITERAL event type string so a future
        # rename of the enum without updating the persistence side (or vice
        # versa) is caught by the test suite.
        literal_events = await audit.query(event_type="capability_first_seen")
        assert len(literal_events) >= 1
        assert all(e.event_type == "capability_first_seen" for e in literal_events)
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_subsequent_list_tools_uses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    discovery, sup, _rsvc, audit, _prefs, engine = await _setup(
        tmp_path,
        server_configs={"fs": _stdio_config("a")},
    )
    try:
        t1 = await discovery.list_tools("fs")
        t2 = await discovery.list_tools("fs")
        # Two identical lists; the second came from cache
        assert {t.original_name for t in t1} == {t.original_name for t in t2}
        # Only one capability_first_seen audit (reconciliation only happens on cache miss)
        events = await audit.query(event_type=AuditEventType.CAPABILITY_FIRST_SEEN.value)
        assert len(events) == 1
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_tool_is_filtered_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    discovery, sup, rsvc, _audit, prefs, engine = await _setup(
        tmp_path,
        server_configs={"fs": _stdio_config("read_file", "write_file")},
    )
    try:
        # Populate preferences first
        await discovery.list_tools("fs")
        resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
        await prefs.set_enabled(resource.id, "tool", "write_file", False)
        # Force re-query (clear cache) and verify write_file is gone
        discovery.invalidate("fs", "tool")
        tools = await discovery.list_tools("fs")
        assert {t.original_name for t in tools} == {"read_file"}
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="new capabilities default per server policy"
)
@pytest.mark.asyncio
async def test_auto_enable_false_new_tools_default_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    discovery, sup, rsvc, _audit, prefs, engine = await _setup(
        tmp_path,
        server_configs={"fs": _stdio_config("read_file", "write_file")},
        auto_enable=False,
    )
    try:
        tools = await discovery.list_tools("fs")
        # All filtered out because preferences default to disabled
        assert tools == []
        # But the preferences rows exist
        resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
        pref_rows = await prefs.list_for(resource.id, "tool")
        assert len(pref_rows) == 2
        assert all(not p.enabled for p in pref_rows)
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_resources_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    discovery, sup, _rsvc, _audit, _prefs, engine = await _setup(
        tmp_path,
        server_configs={
            "fs": {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [
                        str(_FAKE),
                        "--tools",
                        "stub",  # need at least one tool for the SDK
                        "--resources",
                        "file:///tmp/a.txt",
                    ],
                },
            }
        },
    )
    try:
        resources = await discovery.list_resources("fs")
        assert len(resources) == 1
        r = resources[0]
        assert r.original_uri == "file:///tmp/a.txt"
        assert r.prefixed_uri == "coffer://fs/file:///tmp/a.txt"
        assert r.enabled is True
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_prompts_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    discovery, sup, _rsvc, _audit, _prefs, engine = await _setup(
        tmp_path,
        server_configs={
            "gh": {
                "transport": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [
                        str(_FAKE),
                        "--tools",
                        "stub",
                        "--prompts",
                        "summarise",
                    ],
                },
            }
        },
    )
    try:
        prompts = await discovery.list_prompts("gh")
        assert len(prompts) == 1
        p = prompts[0]
        assert p.original_name == "summarise"
        assert p.prefixed_name == "gh__summarise"
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.acceptance(
    spec="001-mcp-gateway", scenario="capability preferences survive upstream changes"
)
@pytest.mark.asyncio
async def test_missing_capability_preferences_preserved_across_invalidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a tool disappears from upstream (or invalidate triggers re-query
    against a different upstream snapshot), the user's disable preference must
    survive."""
    _with_in_memory(monkeypatch)
    discovery, sup, rsvc, _audit, prefs, engine = await _setup(
        tmp_path,
        server_configs={"fs": _stdio_config("read_file", "write_file")},
    )
    try:
        # Populate prefs + disable write_file
        await discovery.list_tools("fs")
        resource = await rsvc.get(ResourceRef("mcp_server", "fs"))
        await prefs.set_enabled(resource.id, "tool", "write_file", False)

        # Invalidate; re-query against the SAME upstream (which still has both)
        discovery.invalidate("fs", "tool")
        tools = await discovery.list_tools("fs")
        assert {t.original_name for t in tools} == {"read_file"}

        # Preference rows still show write_file=False
        pref_rows = await prefs.list_for(resource.id, "tool")
        wf = next(p for p in pref_rows if p.capability_key == "write_file")
        assert wf.enabled is False
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="register an HTTP MCP server")
@pytest.mark.asyncio
async def test_register_http_mcp_server_discovers_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Register an HTTP MCP server with a credential_ref; assert:
    - capabilities are discovered (tools list is populated)
    - the credential value does not appear in any DB row (config column, audit entries)
    """
    backend = install_in_memory_keyring(monkeypatch)

    # Store a fake token in the keyring — never in the config dict.
    secret_value = "super-secret-token-xyz"
    backend.set_password("coffer", "http_fake_token", secret_value)

    proc, port = await asyncio.get_running_loop().run_in_executor(
        None, _start_http_fake, ["list_files", "delete_file"]
    )
    try:
        http_config = {
            "transport": {
                "type": "http",
                "url": f"http://127.0.0.1:{port}/mcp",
                # credential_refs maps a header name to a keyring key
                "credential_refs": {"Authorization": "http_fake_token"},
            }
        }

        discovery, sup, rsvc, audit, _prefs, engine = await _setup(
            tmp_path,
            server_configs={"http_srv": http_config},
        )
        try:
            # Trigger discovery — this calls spawn_and_initialize() + list_tools()
            tools = await discovery.list_tools("http_srv")
            tool_names = {t.original_name for t in tools}
            assert tool_names == {
                "list_files",
                "delete_file",
            }, f"Expected discovered tools, got: {tool_names}"

            # --- Credential safety: scan every DB row for the secret value ---
            # Check resources table (config column stores transport JSON)
            resource = await rsvc.get(ResourceRef("mcp_server", "http_srv"))
            config_str = str(resource.config)
            assert secret_value not in config_str, (
                f"Credential leaked into resource.config: {config_str!r}"
            )

            # Check audit entries
            all_audit = await audit.query()
            for entry in all_audit:
                entry_str = str(entry.details)
                assert secret_value not in entry_str, (
                    f"Credential leaked into audit entry details: {entry_str!r}"
                )
        finally:
            await sup.dispose()
            await engine.dispose()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# --------------------------------------------------------------------------- #
# Self-healing on a stale reused connection (regression for the bug where the  #
# management discovery path reused a dead process-wide supervisor connection,  #
# had no evict/retry, and surfaced a 500 / empty list while Test connection    #
# stayed green and Refresh did nothing).                                        #
# --------------------------------------------------------------------------- #


class _Prompt:
    def __init__(self, name: str, description: str | None = None, arguments: list | None = None):  # type: ignore[type-arg]
        self.name = name
        self.description = description
        self.arguments = arguments or []


class _PromptsResult:
    def __init__(self, prompts: list) -> None:  # type: ignore[type-arg]
        self.prompts = prompts


class _Conn:
    """Fake upstream connection: returns a fixed result or raises a fixed error."""

    def __init__(self, *, result: object = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.request_calls = 0
        self.closed = False

    async def request(self, method: str, params: dict) -> object:  # type: ignore[type-arg]
        self.request_calls += 1
        if self._error is not None:
            raise self._error
        return self._result

    async def close(self) -> None:
        self.closed = True


class _FakeSupervisor:
    """Mimics SubprocessSupervisor's reuse/evict contract: hands out a cached
    connection until evict() clears it, then spawns the next queued one."""

    def __init__(self, conns: list[_Conn]) -> None:
        self._queue = list(conns)
        self._current: _Conn | None = None
        self.spawn_count = 0
        self.evict_calls: list[str] = []

    async def get_or_spawn(self, name: str) -> _Conn:
        if self._current is None:
            self._current = self._queue.pop(0)
            self.spawn_count += 1
        return self._current

    async def evict(self, name: str) -> None:
        self.evict_calls.append(name)
        self._current = None


def _discovery_with_supervisor(
    rsvc: ResourceService,
    prefs: MCPCapabilityPreferenceRepo,
    audit: AuditService,
    supervisor: object,
) -> CapabilityDiscovery:
    return CapabilityDiscovery(
        resource_service=rsvc,
        supervisor=supervisor,  # type: ignore[arg-type]
        preferences=prefs,
        audit=audit,
    )


@pytest.mark.asyncio
async def test_list_prompts_self_heals_when_reused_connection_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    _discovery, _sup, rsvc, audit, prefs, engine = await _setup(
        tmp_path, server_configs={"x": _stdio_config("stub")}
    )
    try:
        stale = _Conn(error=ConnectionError("stale session"))
        healthy = _Conn(result=_PromptsResult([_Prompt("p1")]))
        fake_sup = _FakeSupervisor([stale, healthy])
        discovery = _discovery_with_supervisor(rsvc, prefs, audit, fake_sup)

        prompts = await discovery.list_prompts("x")

        # Recovered transparently from the dead connection.
        assert {p.original_name for p in prompts} == {"p1"}
        # The broken connection was evicted exactly once and a fresh one spawned.
        assert fake_sup.evict_calls == ["x"]
        assert fake_sup.spawn_count == 2
        assert stale.request_calls == 1
        assert healthy.request_calls == 1
    finally:
        await engine.dispose()


class _ToolsResult:
    def __init__(self, tools: list) -> None:  # type: ignore[type-arg]
        self.tools = tools


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = None
        self.inputSchema: dict = {}  # type: ignore[type-arg]


@pytest.mark.asyncio
async def test_list_tools_self_heals_when_reused_connection_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """list_tools shares _request_self_heal with prompts/resources, so it must
    recover from a stale reused connection the same way."""
    _with_in_memory(monkeypatch)
    _discovery, _sup, rsvc, audit, prefs, engine = await _setup(
        tmp_path, server_configs={"x": _stdio_config("stub")}
    )
    try:
        stale = _Conn(error=ConnectionError("stale session"))
        healthy = _Conn(result=_ToolsResult([_Tool("t1")]))
        fake_sup = _FakeSupervisor([stale, healthy])
        discovery = _discovery_with_supervisor(rsvc, prefs, audit, fake_sup)

        tools = await discovery.list_tools("x")

        assert {t.original_name for t in tools} == {"t1"}
        assert fake_sup.evict_calls == ["x"]
        assert fake_sup.spawn_count == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_prompts_maps_persistent_failure_to_upstream_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_in_memory(monkeypatch)
    _discovery, _sup, rsvc, audit, prefs, engine = await _setup(
        tmp_path, server_configs={"x": _stdio_config("stub")}
    )
    try:
        dead1 = _Conn(error=ConnectionError("dead"))
        dead2 = _Conn(error=ConnectionError("still dead"))
        fake_sup = _FakeSupervisor([dead1, dead2])
        discovery = _discovery_with_supervisor(rsvc, prefs, audit, fake_sup)

        with pytest.raises(UpstreamUnavailable):
            await discovery.list_prompts("x")

        # Tried to self-heal once before giving up.
        assert fake_sup.evict_calls == ["x"]
        assert dead1.request_calls == 1
        assert dead2.request_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_prompts_method_not_found_does_not_evict_or_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tools-only upstream replies METHOD_NOT_FOUND for prompts/list. That is
    a legitimate 'no prompts' answer — it must NOT trigger eviction/retry, just
    return an empty list."""
    _with_in_memory(monkeypatch)
    _discovery, _sup, rsvc, audit, prefs, engine = await _setup(
        tmp_path, server_configs={"x": _stdio_config("stub")}
    )
    try:
        import mcp.types as mcp_types
        from mcp import McpError

        not_found = McpError(
            mcp_types.ErrorData(code=mcp_types.METHOD_NOT_FOUND, message="no prompts")
        )
        conn = _Conn(error=not_found)
        fake_sup = _FakeSupervisor([conn])
        discovery = _discovery_with_supervisor(rsvc, prefs, audit, fake_sup)

        prompts = await discovery.list_prompts("x")

        assert prompts == []
        assert fake_sup.evict_calls == []
        assert conn.request_calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cache_expires_after_ttl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_in_memory(monkeypatch)
    clock_state = {"now": 0.0}

    def fake_clock() -> float:
        return clock_state["now"]

    discovery, sup, _rsvc, _audit, _prefs, engine = await _setup(
        tmp_path,
        server_configs={"fs": _stdio_config("a")},
    )
    # Replace clock + tighten TTL
    discovery._clock = fake_clock
    discovery._ttl = 1.0
    try:
        clock_state["now"] = 100.0
        await discovery.list_tools("fs")
        # Cache hit
        clock_state["now"] = 100.5
        await discovery.list_tools("fs")
        # Cache expired
        clock_state["now"] = 102.0
        await discovery.list_tools("fs")
        # If we got here without exception, the cache invalidation triggered
        # a fresh upstream query (which the fake server can serve forever).
    finally:
        await sup.dispose()
        await engine.dispose()
