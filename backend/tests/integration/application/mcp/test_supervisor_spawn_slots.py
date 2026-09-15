"""SubprocessSupervisor cold-start bounding and cancellation propagation.

* ``max_concurrent_spawns`` caps how many DIFFERENT upstreams one supervisor
  cold-starts at once (the per-server ``spawn_lock`` only coalesces racers on
  the same name).
* ``COFFER_MCP_MAX_CONCURRENT_SPAWNS`` is the env knob behind the default.
* A CancelledError from ``spawn_and_initialize`` leaves the retry ladder on
  the spot — no retry, no cooldown.

Fake upstreams stand in for real subprocesses: the properties under test are
the supervisor's own, and a real fake_mcp_server child would only add noise.
"""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.supervisor import (
    SubprocessSupervisor,
    UpstreamHealth,
)
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from tests.integration.application.mcp.test_supervisor import (
    _basic_stdio_config,
    _make_services,
    _with_in_memory,
)


class _FakeUpstream:
    async def request(self, method, params):  # type: ignore[no-untyped-def]
        return None

    def on_notification(self, cb):  # type: ignore[no-untyped-def]
        pass

    def on_sampling_request(self, cb):  # type: ignore[no-untyped-def]
        pass

    def on_roots_request(self, cb):  # type: ignore[no-untyped-def]
        pass

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_concurrent_cold_starts_are_capped_at_max_concurrent_spawns(
    tmp_path, monkeypatch
) -> None:
    """Five different servers spawned at once through a supervisor with
    ``max_concurrent_spawns=2`` never have more than two spawns in flight —
    and all five still come up."""
    _with_in_memory(monkeypatch)
    names = [f"srv{i}" for i in range(5)]
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[(n, _basic_stdio_config("x")) for n in names]
    )

    in_flight = {"now": 0, "max": 0, "spawns": 0}

    class _SlowUpstream(_FakeUpstream):
        async def spawn_and_initialize(self) -> dict:
            in_flight["now"] += 1
            in_flight["spawns"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["now"])
            try:
                await asyncio.sleep(0.2)
            finally:
                in_flight["now"] -= 1
            return {}

    def _factory(transport, overlay, spawn_to, req_to, name):  # type: ignore[no-untyped-def]
        return _SlowUpstream()

    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        upstream_factory=_factory,  # type: ignore[arg-type]
        max_concurrent_spawns=2,
    )
    try:
        conns = await asyncio.gather(*[sup.get_or_spawn(n) for n in names])
        assert len(conns) == 5 and all(isinstance(c, _SlowUpstream) for c in conns)
        assert all(sup.health(n) == UpstreamHealth.HEALTHY for n in names)
        assert in_flight["spawns"] == 5
        assert in_flight["max"] == 2, (
            f"expected at most 2 spawns in flight under max_concurrent_spawns=2, "
            f"saw {in_flight['max']}"
        )
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_max_concurrent_spawns_env_knob(tmp_path, monkeypatch) -> None:
    """Unparseable / non-positive env falls back to the default of 4; a valid
    value is honoured; an explicit constructor value wins over env."""
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(tmp_path, register_servers=[])
    resolver = CredentialResolver(KeyringAdapter())

    def _factory(transport, overlay, spawn_to, req_to, name):  # type: ignore[no-untyped-def]
        return _FakeUpstream()

    def _build(**kwargs: int) -> SubprocessSupervisor:
        return SubprocessSupervisor(
            resource_service=resource_svc,
            credential_resolver=resolver,
            upstream_factory=_factory,  # type: ignore[arg-type]
            **kwargs,
        )

    try:
        monkeypatch.setenv("COFFER_MCP_MAX_CONCURRENT_SPAWNS", "junk")
        assert _build().max_concurrent_spawns == 4
        monkeypatch.setenv("COFFER_MCP_MAX_CONCURRENT_SPAWNS", "0")
        assert _build().max_concurrent_spawns == 4
        monkeypatch.setenv("COFFER_MCP_MAX_CONCURRENT_SPAWNS", "7")
        sup = _build()
        assert sup.max_concurrent_spawns == 7
        assert sup._spawn_slots._value == 7  # the semaphore really is sized by it
        assert _build(max_concurrent_spawns=3).max_concurrent_spawns == 3
        monkeypatch.delenv("COFFER_MCP_MAX_CONCURRENT_SPAWNS")
        assert _build().max_concurrent_spawns == 4
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_error_leaves_retry_ladder_immediately(tmp_path, monkeypatch) -> None:
    """A CancelledError out of spawn_and_initialize (the caller's task is
    being cancelled — e.g. daemon shutdown) propagates on the first attempt:
    the factory is called once, no retry sleep runs, and the server is not
    pushed into cooldown as if it had failed."""
    _with_in_memory(monkeypatch)
    resource_svc, engine = await _make_services(
        tmp_path, register_servers=[("fs", _basic_stdio_config("x"))]
    )
    calls = {"factory": 0}

    class _CancellingUpstream(_FakeUpstream):
        async def spawn_and_initialize(self) -> dict:
            raise asyncio.CancelledError()

    def _factory(transport, overlay, spawn_to, req_to, name):  # type: ignore[no-untyped-def]
        calls["factory"] += 1
        return _CancellingUpstream()

    sup = SubprocessSupervisor(
        resource_service=resource_svc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
        upstream_factory=_factory,  # type: ignore[arg-type]
        retry_delays=(30.0, 30.0),  # a retry would be unmistakable in wall-clock
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await sup.get_or_spawn("fs")
        assert calls["factory"] == 1
        assert sup.health("fs") != UpstreamHealth.COOLDOWN
        # The slot was released on the way out: a later spawn is not starved.
        assert sup._spawn_slots._value == sup.max_concurrent_spawns
    finally:
        await sup.dispose()
        await engine.dispose()
