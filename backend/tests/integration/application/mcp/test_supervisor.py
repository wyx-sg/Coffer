"""SubprocessSupervisor tests using the fake_mcp_server fixture for stdio
and an in-process FakeKeyring + ResourceService for kind-agnostic plumbing.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.supervisor import (
    SubprocessSupervisor,
    UpstreamHealth,
)
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.fixtures.keyring import InMemoryKeyring, install_in_memory_keyring

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _with_in_memory(monkeypatch) -> InMemoryKeyring:
    return install_in_memory_keyring(monkeypatch)


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


@pytest.mark.asyncio
async def test_lazy_spawn_returns_initialized_connection(tmp_path, monkeypatch):
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path,
        register_servers=[("fs", _basic_stdio_config("read_file", "write_file"))],
    )
    sup = SubprocessSupervisor(
        upstream_factory=build_upstream,
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
        upstream_factory=build_upstream,
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
    fs = await resource_svc.get_by_name("mcp_server", "fs")
    await resource_svc.set_enabled(fs.uid, False, actor="test")
    sup = SubprocessSupervisor(
        upstream_factory=build_upstream,
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
        upstream_factory=build_upstream,
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
        upstream_factory=build_upstream,
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
        flaky = await resource_svc.get_by_name("mcp_server", "flaky")
        await resource_svc.update_config(
            flaky.uid,
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
        upstream_factory=build_upstream,
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
        upstream_factory=build_upstream,
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
    """20 concurrent get_or_spawn calls for the same server share
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
async def test_concurrent_get_or_spawn_on_dead_upstream_runs_one_retry_ladder(
    tmp_path, monkeypatch
):
    """When several callers race to reach a dead upstream, the retry
    ladder must run exactly once in total, not once per caller.

    Regression: the cooldown gate was only checked before acquiring spawn_lock.
    Each waiter that then acquired the lock saw state != HEALTHY, reset to
    STARTING, and burned the whole ladder again — so N concurrent callers
    amplified the work N-fold (and held a session's tool calls hostage for
    minutes). Re-checking cooldown *under* the lock makes later waiters fail
    fast once the first caller has entered cooldown.
    """
    import asyncio as _asyncio

    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[("bad", _basic_stdio_config("x"))]
    )

    attempts = {"n": 0}

    class _AlwaysFailUpstream:
        async def spawn_and_initialize(self) -> dict:
            attempts["n"] += 1
            raise UpstreamUnavailable("boom")

        async def request(self, method, params):  # type: ignore[no-untyped-def]
            raise UpstreamUnavailable("boom")

        def on_notification(self, cb):  # type: ignore[no-untyped-def]
            pass

        def on_sampling_request(self, cb):  # type: ignore[no-untyped-def]
            pass

        def on_roots_request(self, cb):  # type: ignore[no-untyped-def]
            pass

        async def close(self) -> None:
            pass

    def _failing_factory(transport, overlay, spawn_to, req_to, name):  # type: ignore[no-untyped-def]
        return _AlwaysFailUpstream()

    retry_delays = (0.01, 0.01, 0.01)
    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        upstream_factory=_failing_factory,  # type: ignore[arg-type]
        retry_delays=retry_delays,
        cooldown_seconds=60,
    )

    try:
        results = await _asyncio.gather(
            *[sup.get_or_spawn("bad") for _ in range(5)],
            return_exceptions=True,
        )
        assert all(isinstance(r, UpstreamUnavailable) for r in results)
        assert sup.health("bad") == UpstreamHealth.COOLDOWN
        # One ladder = len(retry_delays) + 1 attempts. Without the under-lock
        # cooldown re-check this would be 5x that.
        assert attempts["n"] == len(retry_delays) + 1, (
            f"expected one retry ladder ({len(retry_delays) + 1} attempts) for "
            f"5 concurrent callers, got {attempts['n']}"
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
        upstream_factory=build_upstream,
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


@pytest.mark.asyncio
async def test_evicting_a_server_does_not_wait_for_a_spawn_that_will_never_work(
    tmp_path, monkeypatch
):
    """Eviction wins over a spawn in flight, instead of queueing behind it.

    A delete runs the ``mcp_server`` kind's ``on_delete``, which evicts the
    server from every supervisor holding a live connection — including the
    process-wide one behind the capability-management routes. That supervisor
    is exactly where a detail page's discovery is spawning, and a command that
    cannot speak MCP takes the full retry ladder to fail. Sharing one lock
    between the two made deleting such a server wait for a subprocess ladder
    nobody wanted the answer to any more, which read to the user — and to the
    browser test that found it — as a request that never came back.

    So the assertion is on TIME, which is the whole defect: the numbers are a
    generous multiple of the ladder this supervisor is configured with, so the
    test fails only if eviction is serialised behind it.
    """
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path,
        register_servers=[
            (
                "wedged",
                {
                    "transport": {
                        "type": "stdio",
                        # Exits immediately and says nothing — the upstream
                        # never initialises, so every attempt on the ladder
                        # burns its full timeout.
                        "command": sys.executable,
                        "args": ["-c", "pass"],
                    },
                },
            )
        ],
    )
    sup = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        retry_delays=(5.0, 5.0),
    )
    try:
        spawning = asyncio.create_task(_swallow(sup.get_or_spawn("wedged")))
        # Let the ladder get as far as holding the lock.
        await asyncio.sleep(0.2)

        started = asyncio.get_running_loop().time()
        await asyncio.wait_for(sup.evict("wedged"), timeout=2.0)
        waited = asyncio.get_running_loop().time() - started

        assert waited < 1.0, f"evict queued behind the spawn ladder ({waited:.1f}s)"
        spawning.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await spawning
    finally:
        await sup.dispose()
        await engine.dispose()


async def _swallow(awaitable):
    """Run something whose failure is the point, not the subject."""
    with suppress(Exception):
        return await awaitable
    return None
