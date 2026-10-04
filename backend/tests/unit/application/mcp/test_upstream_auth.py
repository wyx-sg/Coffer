"""UpstreamAuthMonitor: when a forwarded call changes a server's recorded health."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.mcp.upstream_auth import UpstreamAuthMonitor

NOW = datetime(2026, 10, 3, tzinfo=UTC)


class FakeHealth:
    def __init__(self, row: tuple[str, str | None] | None = None) -> None:
        self.row = row
        self.reads = 0
        self.writes: list[tuple[str, str, str | None]] = []

    async def get(self, resource_uid: str) -> tuple[str, datetime] | None:
        self.reads += 1
        return (self.row[0], NOW) if self.row else None

    async def get_reason(self, resource_uid: str) -> str | None:
        return self.row[1] if self.row else None

    async def upsert(
        self, resource_uid: str, status: Any, checked_at: datetime, reason: Any = None
    ) -> None:
        self.writes.append((resource_uid, status, reason))
        self.row = (status, reason)


def _monitor(health: FakeHealth) -> tuple[UpstreamAuthMonitor, list[int]]:
    changes: list[int] = []
    monitor = UpstreamAuthMonitor(health, clock=lambda: NOW, on_change=lambda: changes.append(1))
    return monitor, changes


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a rejected key from a real call reaches the Overview"
)
async def test_a_rejection_records_the_server_failing_with_auth_rejected() -> None:
    health = FakeHealth()
    monitor, changes = _monitor(health)
    await monitor.rejected("u1")
    assert health.writes == [("u1", "failing", "auth_rejected")]
    assert changes == [1]


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an answered call clears a recorded rejection")
async def test_an_answered_call_after_a_rejection_records_healthy() -> None:
    health = FakeHealth()
    monitor, changes = _monitor(health)
    await monitor.rejected("u1")
    await monitor.answered("u1")
    assert health.writes[-1] == ("u1", "healthy", None)
    assert changes == [1, 1]


@pytest.mark.acceptance(spec="mcp-gateway", scenario="an answered call clears a recorded rejection")
async def test_a_rejection_recorded_before_a_restart_is_cleared_by_the_first_answer() -> None:
    health = FakeHealth(("failing", "auth_rejected"))
    monitor, _ = _monitor(health)
    await monitor.answered("u1")
    assert health.writes == [("u1", "healthy", None)]


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="answered calls to a healthy server write nothing"
)
async def test_answered_calls_to_a_healthy_server_read_once_and_never_write() -> None:
    health = FakeHealth(("healthy", None))
    monitor, changes = _monitor(health)
    for _ in range(5):
        await monitor.answered("u1")
    assert health.reads == 1
    assert health.writes == []
    assert changes == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a tool error result does not mark a server failing"
)
async def test_a_failing_state_from_another_cause_is_left_alone_by_an_answer() -> None:
    # Only a recorded auth rejection is the gateway's to clear: an unreachable
    # server a test found stays as it is until the next test.
    health = FakeHealth(("failing", "unreachable"))
    monitor, _ = _monitor(health)
    await monitor.answered("u1")
    assert health.writes == []
