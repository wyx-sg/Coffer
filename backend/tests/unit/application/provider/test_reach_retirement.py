"""Retiring a connection's off switch and scope at startup (ADR
provider-reach-is-what-its-addresses-serve; spec provider-switching "Retire the
off switch and scope of existing connections"). Unit tier, over a fake service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.provider.reach_retirement import retire_off_switch
from coffer.domain.agent.types import AgentType
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope

_NOW = datetime(2026, 10, 9, tzinfo=UTC)


def _row(uid: str, kind: str, config: dict[str, Any], **over: Any) -> Resource:
    return Resource(
        uid=uid,
        kind=kind,
        name=uid,
        description=None,
        config=config,
        enabled=over.pop("enabled", True),
        created_at=_NOW,
        updated_at=_NOW,
        scope=over.pop("scope", None),
    )


def _agent(uid: str, agent_type: AgentType, connection: str | None) -> Resource:
    return _row(
        uid,
        "agent",
        {"type": agent_type.value, "config_dir": f"/tmp/{uid}", "connection_uid": connection},
    )


@dataclass
class _Resources:
    calls: list[tuple[str, str, object]] = field(default_factory=list)

    async def set_enabled(self, uid: str, enabled: bool, actor: str) -> None:
        self.calls.append(("enable", uid, enabled))

    async def update_scope(self, uid: str, scope: object, *, actor: str) -> None:
        self.calls.append(("scope", uid, scope))


@dataclass
class _Agents:
    rows: list[Resource]

    async def list(self) -> list[Resource]:
        return self.rows


@dataclass
class _Service:
    rows: list[Resource]
    _agents: _Agents
    _resources: _Resources = field(default_factory=_Resources)
    deactivated: list[AgentType] = field(default_factory=list)

    async def list(self) -> list[Resource]:
        return self.rows

    async def deactivate(self, agent_type: AgentType, *, actor: str) -> None:
        self.deactivated.append(agent_type)


_CFG = {"protocol": "anthropic", "base_url": "https://x", "secret_ref": "provider/x/key"}


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an agent on a switched-off connection goes back to its own login",
)
@pytest.mark.asyncio
async def test_an_off_connection_sends_its_agent_home_then_is_switched_on() -> None:
    off = _row("off", "provider", _CFG, enabled=False)
    on = _row("on", "provider", _CFG, scope=Scope(agents=["a" * 32]))
    agents = _Agents(
        [_agent("cc", AgentType.CLAUDE_CODE, "off"), _agent("cx", AgentType.CODEX, "on")]
    )
    service = _Service([off, on], agents)

    changed = await retire_off_switch(service)  # type: ignore[arg-type]

    assert changed == ["off", "on"]
    assert service.deactivated == [AgentType.CLAUDE_CODE]
    assert service._resources.calls == [("enable", "off", True), ("scope", "on", None)]


@pytest.mark.asyncio
async def test_a_connection_that_is_on_and_unscoped_is_left_alone() -> None:
    service = _Service([_row("p", "provider", _CFG)], _Agents([]))
    assert await retire_off_switch(service) == []  # type: ignore[arg-type]
    assert service._resources.calls == []
