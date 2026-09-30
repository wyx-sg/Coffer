"""The plugin inventory a descriptor carries, and the worker's schedule."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from coffer.application.sync.inventory import AgentPluginInventory
from coffer.application.sync.worker import SyncWorker
from coffer.domain.sync.remote import SyncRemote


class _Agents:
    def __init__(self, *rows: Any) -> None:
        self.rows = rows

    async def list(self, *, kind: str) -> list[Any]:
        assert kind == "agent"
        return list(self.rows)


class _Plugins:
    async def list_plugins(self, uid: str) -> Any:
        if uid == "broken":
            raise RuntimeError("config does not parse")
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    id="zeta", name="Zeta", marketplace="m", enabled=False, version=None
                ),
                SimpleNamespace(
                    id="alpha", name="Alpha", marketplace=None, enabled=True, version="2"
                ),
            ]
        )


async def test_each_agent_is_listed_with_its_plugins_and_a_failure_lists_none() -> None:
    agents = _Agents(
        SimpleNamespace(uid="u1", name="codex", config={"type": "codex"}),
        SimpleNamespace(uid="broken", name="claude-code", config={"type": "claude_code"}),
    )
    got = await AgentPluginInventory(agents, lambda: _Plugins()).inventory()  # type: ignore[arg-type]
    assert [(a.type, [p.id for p in a.plugins]) for a in got] == [
        ("codex", ["alpha", "zeta"]),
        ("claude_code", []),
    ]
    without = await AgentPluginInventory(agents, lambda: None).inventory()  # type: ignore[arg-type]
    assert all(a.plugins == () for a in without)


@dataclass
class _Service:
    remote_: SyncRemote | None
    runs: list[str] = field(default_factory=list)
    next_at: datetime | None = None

    def remote(self) -> SyncRemote | None:
        return self.remote_

    def set_next_round(self, when: datetime | None) -> None:
        self.next_at = when

    async def run(self, *, trigger: str = "manual") -> Any:
        self.runs.append(trigger)
        return None


NOW = datetime(2026, 9, 30, 8, 0, tzinfo=UTC)


async def test_a_round_runs_on_the_remote_interval_and_says_when_the_next_is() -> None:
    svc = _Service(SyncRemote(url="https://example.com/v.git", interval_seconds=600))
    worker = SyncWorker(svc, clock=lambda: NOW)  # type: ignore[arg-type]
    assert await worker.tick() == 600
    assert svc.runs == ["timer"]
    assert svc.next_at == NOW + timedelta(seconds=600)


async def test_nothing_runs_without_a_remote_or_while_it_is_paused() -> None:
    for remote in (None, SyncRemote(url="https://example.com/v.git", enabled=False)):
        svc = _Service(remote)
        worker = SyncWorker(svc, idle_poll_s=5, clock=lambda: NOW)  # type: ignore[arg-type]
        assert await worker.tick() == 5
        assert svc.runs == [] and svc.next_at is None
