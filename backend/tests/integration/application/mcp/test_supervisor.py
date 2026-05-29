"""SubprocessSupervisor tests using the fake_mcp_server fixture for stdio
and an in-process FakeKeyring + ResourceService for kind-agnostic plumbing.
"""

from __future__ import annotations

import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import keyring
import keyring.core
import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.supervisor import (
    SubprocessSupervisor,
    UpstreamHealth,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind, ResourceRef
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


class _InMemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._data.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._data[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._data.pop((service, username), None)


def _with_in_memory(monkeypatch) -> _InMemoryKeyring:
    backend = _InMemoryKeyring()
    monkeypatch.setattr(keyring.core, "_keyring_backend", backend)
    return backend


async def _make_services(tmp_path, *, register_servers: list[tuple[str, dict]]):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    kinds = {
        "mcp_server": Kind(
            name="mcp_server",
            display_name="MCP Server",
            config_schema=MCPServerConfig,
        ),
    }
    resource_svc = ResourceService(kinds=kinds, repo=repo, audit=audit)
    for name, config in register_servers:
        await resource_svc.register(kind="mcp_server", name=name, config=config, actor="test")
    return resource_svc, engine


def _basic_stdio_config(*tools: str) -> dict:
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", *tools],
        },
    }


def _slow_stdio_config(delay_ms: int) -> dict:
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [
                str(_FAKE),
                "--scenario",
                "slow",
                "--init-delay-ms",
                str(delay_ms),
                "--tools",
                "x",
            ],
        },
        "spawn_timeout_seconds": 5,  # explicit lower bound for the test
    }


@pytest.mark.asyncio
async def test_lazy_spawn_returns_initialized_connection(tmp_path, monkeypatch):
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path,
        register_servers=[("fs", _basic_stdio_config("read_file", "write_file"))],
    )
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    try:
        assert sup.health("fs") == UpstreamHealth.UNHEALTHY
        conn = await sup.get_or_spawn("fs")
        assert sup.health("fs") == UpstreamHealth.HEALTHY
        # The connection works end-to-end
        result = await conn.request("tools/list", {})
        assert {t.name for t in result.tools} == {"read_file", "write_file"}
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_spawn_is_idempotent(tmp_path, monkeypatch):
    """Calling get_or_spawn twice returns the same live connection."""
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[("fs", _basic_stdio_config("x"))]
    )
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    try:
        a = await sup.get_or_spawn("fs")
        b = await sup.get_or_spawn("fs")
        assert a is b
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_resource_rejected(tmp_path, monkeypatch):
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[("fs", _basic_stdio_config("x"))]
    )
    await resource_svc.set_enabled(ResourceRef("mcp_server", "fs"), False, actor="test")
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    try:
        with pytest.raises(UpstreamUnavailable, match="disabled"):
            await sup.get_or_spawn("fs")
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_spawn_failure_retries_then_enters_cooldown(tmp_path, monkeypatch):
    """With no retry delay and a server that always fails, supervisor cooldowns."""
    _with_in_memory(monkeypatch)
    # Register a server whose command doesn't exist — every spawn fails
    bad_config = {
        "transport": {
            "type": "stdio",
            "command": "/nonexistent/binary/that/does/not/exist",
            "args": [],
        },
        "spawn_timeout_seconds": 5,
    }
    resource_svc, engine = await _make_services(tmp_path, register_servers=[("bad", bad_config)])
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        retry_delays=(0.01, 0.01, 0.01),  # snappy for tests
        cooldown_seconds=1,
    )
    try:
        with pytest.raises(UpstreamUnavailable):
            await sup.get_or_spawn("bad")
        assert sup.health("bad") == UpstreamHealth.COOLDOWN

        # While in cooldown, no new spawn is attempted
        with pytest.raises(UpstreamUnavailable, match="cooldown"):
            await sup.get_or_spawn("bad")
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_cooldown_expires_and_allows_new_attempt(tmp_path, monkeypatch):
    """After cooldown elapses, a fresh spawn attempt can succeed."""
    _with_in_memory(monkeypatch)
    # Use a fixed clock we can advance
    clock_state = {"now": datetime(2026, 5, 21, 0, 0, 0, tzinfo=UTC)}

    def clock():
        return clock_state["now"]

    # Start with the bad command so we trip cooldown
    bad_config = {
        "transport": {
            "type": "stdio",
            "command": "/nonexistent",
            "args": [],
        },
        "spawn_timeout_seconds": 5,
    }
    resource_svc, engine = await _make_services(tmp_path, register_servers=[("flaky", bad_config)])
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        retry_delays=(0.01,),
        cooldown_seconds=60,
        clock=clock,
    )
    try:
        with pytest.raises(UpstreamUnavailable):
            await sup.get_or_spawn("flaky")
        assert sup.health("flaky") == UpstreamHealth.COOLDOWN

        # Replace the resource's config with a good one
        await resource_svc.update_config(
            ResourceRef("mcp_server", "flaky"),
            new_config=_basic_stdio_config("x"),
            actor="test",
        )

        # Advance the clock past cooldown
        clock_state["now"] = clock_state["now"] + timedelta(seconds=61)

        # Now get_or_spawn should succeed
        conn = await sup.get_or_spawn("flaky")
        assert sup.health("flaky") == UpstreamHealth.HEALTHY
        assert conn is not None
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_evict_closes_connection_and_marks_unhealthy(tmp_path, monkeypatch):
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[("fs", _basic_stdio_config("x"))]
    )
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    try:
        await sup.get_or_spawn("fs")
        await sup.evict("fs")
        assert sup.health("fs") == UpstreamHealth.UNHEALTHY
        # Next call respawns
        conn = await sup.get_or_spawn("fs")
        assert sup.health("fs") == UpstreamHealth.HEALTHY
        assert conn is not None
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_dispose_closes_all_connections(tmp_path, monkeypatch):
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path,
        register_servers=[
            ("fs", _basic_stdio_config("x")),
            ("gh", _basic_stdio_config("y")),
        ],
    )
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    try:
        await sup.get_or_spawn("fs")
        await sup.get_or_spawn("gh")
        await sup.dispose()
        assert sup.health("fs") == UpstreamHealth.UNHEALTHY
        assert sup.health("gh") == UpstreamHealth.UNHEALTHY
    finally:
        # engine.dispose() can raise CancelledError on Python 3.14 when
        # anyio cancel scopes from the closed subprocess connections are still
        # active on the event loop; SQLite GC handles cleanup in that case.
        with suppress(BaseException):
            await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_get_or_spawn_yields_one_subprocess(tmp_path, monkeypatch):
    """TEST-006: 20 concurrent get_or_spawn calls for the same server share
    one spawned upstream — proves the spawn_lock + cached-HEALTHY fast path
    coalesces racers and avoids the classic "thundering herd of subprocesses"
    failure mode.

    Bypasses the real subprocess by injecting a counting factory directly —
    no fake_mcp_server child process is required to prove the dedup property.
    """
    import asyncio as _asyncio
    from unittest.mock import AsyncMock

    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[("fs", _basic_stdio_config("read_file"))]
    )

    spawn_count = {"n": 0}
    one_conn = AsyncMock()
    one_conn.spawn_and_initialize = AsyncMock(return_value={})
    one_conn.close = AsyncMock(return_value=None)

    def _counting_factory(transport, overlay, spawn_to, req_to, name):  # type: ignore[no-untyped-def]
        spawn_count["n"] += 1
        return one_conn

    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        upstream_factory=_counting_factory,  # type: ignore[arg-type]
    )

    try:
        results = await _asyncio.gather(*[sup.get_or_spawn("fs") for _ in range(20)])
        # All 20 callers got the same connection object (cached HEALTHY).
        assert all(r is results[0] for r in results), "callers received different connections"
        assert spawn_count["n"] == 1, (
            f"expected exactly one upstream spawn for 20 concurrent get_or_spawn "
            f"calls, got {spawn_count['n']}"
        )
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_credential_overlay_passed_through(tmp_path, monkeypatch):
    """Verify the supervisor materialises credentials through the resolver."""
    backend = _with_in_memory(monkeypatch)
    backend.set_password("coffer", "github_pat_main", "ghp_abc123")
    resource_svc, engine = await _make_services(
        tmp_path,
        register_servers=[
            (
                "gh",
                {
                    "transport": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": [str(_FAKE), "--tools", "x"],
                        "credential_refs": {"GITHUB_TOKEN": "github_pat_main"},
                    },
                },
            )
        ],
    )
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    try:
        conn = await sup.get_or_spawn("gh")
        # If we got here, materialize succeeded — the env was set on the
        # subprocess. We don't probe the actual env value (the fake server
        # doesn't echo it) but a CredentialMissing would have been raised
        # by the resolver if the keychain entry was absent.
        assert conn is not None
    finally:
        await sup.dispose()
        await engine.dispose()
