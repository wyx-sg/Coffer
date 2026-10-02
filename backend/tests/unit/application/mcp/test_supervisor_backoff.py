"""A dead upstream is backed off once for the daemon, not once per session.

Fake clock, fake spawner, fake resources: nothing starts and nothing sleeps.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from coffer.application.mcp.supervisor import SubprocessSupervisor, UpstreamHealth
from coffer.application.mcp.supervisor_failures import FAILING_AFTER, UpstreamFailureLedger
from coffer.domain.errors import UpstreamUnavailable
from coffer.domain.secret_errors import SecretBindingPending

_CONFIG = {"transport": {"type": "http", "url": "https://x.example/mcp"}}


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 2, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Resources:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    async def get_by_name(self, kind: str, name: str) -> Any:
        return SimpleNamespace(uid="u1", name=name, enabled=self.enabled, config=_CONFIG)


class _Secrets:
    def __init__(self, pending: bool = False) -> None:
        self.pending = pending

    def materialize(self, refs: Any, destination: Any = None) -> dict[str, str]:
        if self.pending:
            raise SecretBindingPending(["a1"], ["smart: awaiting approval"])
        return {}


class _Spawner:
    """Counts spawns; every connection it hands out fails (or works) on demand."""

    def __init__(self) -> None:
        self.spawns = 0
        self.works = False

    def __call__(self, *_a: Any) -> Any:
        outer = self

        class _Conn:
            async def spawn_and_initialize(self) -> None:
                outer.spawns += 1
                if not outer.works:
                    raise UpstreamUnavailable("upstream init failed: ConnectError")

            async def close(self) -> None:
                return None

        return _Conn()


def _supervisor(
    clock: _Clock,
    spawner: _Spawner,
    ledger: UpstreamFailureLedger,
    *,
    resources: _Resources | None = None,
    secrets: _Secrets | None = None,
) -> SubprocessSupervisor:
    return SubprocessSupervisor(
        resource_service=resources or _Resources(),  # type: ignore[arg-type]
        secret_resolver=secrets or _Secrets(),  # type: ignore[arg-type]
        upstream_factory=spawner,  # type: ignore[arg-type]
        retry_delays=(),  # one attempt per ladder keeps the count readable
        clock=clock,
        failures=ledger,
    )


@pytest.mark.asyncio
async def test_backoff_doubles_up_to_the_cap() -> None:
    clock, spawner = _Clock(), _Spawner()
    ledger = UpstreamFailureLedger(base_seconds=10, cap_seconds=35, clock=clock)
    sup = _supervisor(clock, spawner, ledger)
    waits = []
    for _ in range(4):
        with pytest.raises(UpstreamUnavailable):
            await sup.get_or_spawn("smart")
        rec = ledger.get("smart")
        assert rec and rec.retry_at
        waits.append((rec.retry_at - clock.now).total_seconds())
        clock.advance(waits[-1])
    assert waits == [10, 20, 35, 35]


@pytest.mark.asyncio
async def test_a_second_session_does_not_retry_a_server_the_first_found_dead() -> None:
    clock, spawner = _Clock(), _Spawner()
    ledger = UpstreamFailureLedger(clock=clock)
    first = _supervisor(clock, spawner, ledger)
    second = _supervisor(clock, spawner, ledger)
    with pytest.raises(UpstreamUnavailable):
        await first.get_or_spawn("smart")
    assert spawner.spawns == 1
    with pytest.raises(UpstreamUnavailable, match="Next attempt after"):
        await second.get_or_spawn("smart")
    assert spawner.spawns == 1  # not spawned again
    assert second.health("smart") == UpstreamHealth.COOLDOWN


@pytest.mark.asyncio
async def test_circuit_breaker_flags_failing_and_logs_once(caplog: Any) -> None:
    clock, spawner = _Clock(), _Spawner()
    ledger = UpstreamFailureLedger(base_seconds=1, cap_seconds=1, clock=clock)
    sup = _supervisor(clock, spawner, ledger)
    with caplog.at_level("DEBUG"):
        for _ in range(FAILING_AFTER + 3):
            with pytest.raises(UpstreamUnavailable):
                await sup.get_or_spawn("smart")
            clock.advance(2)
    rec = ledger.get("smart")
    assert rec and rec.failing and rec.consecutive_failures == FAILING_AFTER + 3
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert [r.getMessage() for r in warnings].count("mcp.upstream.failing") == 1
    # Once failing, further failed attempts are not warnings.
    assert sum(r.getMessage() == "mcp.upstream.spawn_failed" for r in warnings) == FAILING_AFTER
    with pytest.raises(UpstreamUnavailable, match=r"\(failing\)"):
        clock.advance(-1.5)
        await sup.get_or_spawn("smart")


@pytest.mark.asyncio
async def test_success_and_evict_clear_the_streak() -> None:
    clock, spawner = _Clock(), _Spawner()
    ledger = UpstreamFailureLedger(clock=clock)
    sup = _supervisor(clock, spawner, ledger)
    with pytest.raises(UpstreamUnavailable):
        await sup.get_or_spawn("smart")
    await sup.evict("smart")  # the person edited the server
    spawner.works = True
    await sup.get_or_spawn("smart")  # tried at once, no waiting out the backoff
    assert ledger.get("smart") is None
    assert sup.health("smart") == UpstreamHealth.HEALTHY


@pytest.mark.asyncio
async def test_disabled_server_is_never_spawned() -> None:
    clock, spawner = _Clock(), _Spawner()
    sup = _supervisor(
        clock, spawner, UpstreamFailureLedger(clock=clock), resources=_Resources(enabled=False)
    )
    with pytest.raises(UpstreamUnavailable, match="disabled"):
        await sup.get_or_spawn("smart")
    assert spawner.spawns == 0


@pytest.mark.asyncio
async def test_secret_awaiting_approval_never_spawns_and_is_not_a_failure() -> None:
    clock, spawner = _Clock(), _Spawner()
    ledger = UpstreamFailureLedger(clock=clock)
    sup = _supervisor(clock, spawner, ledger, secrets=_Secrets(pending=True))
    for _ in range(3):
        with pytest.raises(SecretBindingPending):
            await sup.get_or_spawn("smart")
    assert spawner.spawns == 0
    assert ledger.get("smart") is None  # approving it must take effect at once
    assert sup.health("smart") == UpstreamHealth.UNHEALTHY  # not stuck "starting"
