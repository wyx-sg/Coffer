"""AgentConnectionService over fake parts (spec agent-registry "Connect an agent
to Coffer in one action", "Report an agent's Coffer connection part by part",
"Disconnect an agent from Coffer").

Pure: the parts are in-memory fakes and the agent lookup is a dict, so what is
pinned here is the composition — which parts apply, the order they install in,
what disconnect removes, and how the state is derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from coffer.application.agent.connection_service import (
    MCP_PART,
    AgentConnectionService,
    ConnectionState,
    PartStatus,
)
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource

_NOW = datetime(2026, 9, 28, tzinfo=UTC)


def _agent(uid: str, agent_type: AgentType = AgentType.CLAUDE_CODE) -> Resource:
    return Resource(
        uid=uid,
        kind="agent",
        name=uid,
        description=None,
        config={"type": agent_type.value, "config_dir": f"/tmp/{uid}"},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


class _Agents:
    def __init__(self, *agents: Resource) -> None:
        self._by_uid = {a.uid: a for a in agents}

    async def get(self, uid: str, /) -> Resource:
        try:
            return self._by_uid[uid]
        except KeyError:
            raise ResourceNotFound(uid) from None

    async def list(self) -> list[Resource]:
        return list(self._by_uid.values())


@dataclass
class _Part:
    key: str
    types: frozenset[AgentType] = frozenset(AgentType)
    installed: set[str] = field(default_factory=set)
    log: list[tuple[str, str, str]] = field(default_factory=list)
    broken: set[str] = field(default_factory=set)

    def supports(self, agent_type: AgentType) -> bool:
        return agent_type in self.types

    async def status(self, agent_uid: str) -> PartStatus:
        if agent_uid in self.broken:
            raise ValueError("unreadable config")
        on = agent_uid in self.installed
        return PartStatus(key=self.key, installed=on, detail=f"{self.key}-cmd" if on else None)

    async def install(self, agent_uid: str, *, actor: str) -> None:
        self.log.append(("install", agent_uid, actor))
        self.installed.add(agent_uid)

    async def remove(self, agent_uid: str, *, actor: str) -> None:
        self.log.append(("remove", agent_uid, actor))
        self.installed.discard(agent_uid)


def _svc(
    *agents: Resource, hook: _Part | None = None
) -> tuple[AgentConnectionService, _Part, _Part]:
    mcp = _Part(MCP_PART)
    hook = hook or _Part("memory_hook")
    return AgentConnectionService(agent_service=_Agents(*agents), parts=(mcp, hook)), mcp, hook


def test_the_gateway_entry_must_be_the_first_part() -> None:
    with pytest.raises(ValueError, match="gateway entry"):
        AgentConnectionService(agent_service=_Agents(), parts=(_Part("memory_hook"),))


async def test_status_of_a_fresh_agent_is_disconnected_with_every_applicable_part() -> None:
    svc, _mcp, _hook = _svc(_agent("a1"))
    status = await svc.status("a1")
    assert status.state is ConnectionState.DISCONNECTED
    assert [(p.key, p.installed) for p in status.parts] == [("mcp", False), ("memory_hook", False)]


async def test_connect_installs_every_applicable_part_gateway_first() -> None:
    svc, mcp, hook = _svc(_agent("a1"))
    status = await svc.connect("a1", actor="alice")
    assert status.state is ConnectionState.CONNECTED
    assert mcp.log == [("install", "a1", "alice")]
    assert hook.log == [("install", "a1", "alice")]
    assert [p.detail for p in status.parts] == ["mcp-cmd", "memory_hook-cmd"]


async def test_connect_stops_at_the_first_refusal_before_later_parts() -> None:
    class _Refusing(_Part):
        async def install(self, agent_uid: str, *, actor: str) -> None:
            raise RuntimeError("no shim")

    hook = _Part("memory_hook")
    svc = AgentConnectionService(
        agent_service=_Agents(_agent("a1")), parts=(_Refusing(MCP_PART), hook)
    )
    with pytest.raises(RuntimeError, match="no shim"):
        await svc.connect("a1", actor="alice")
    assert hook.log == []


async def test_a_part_the_type_lacks_is_neither_listed_nor_removed() -> None:
    hook = _Part("memory_hook", types=frozenset({AgentType.CODEX}))
    svc, _mcp, _ = _svc(_agent("a1"), hook=hook)
    await svc.connect("a1", actor="alice")
    await svc.disconnect("a1", actor="alice")
    assert hook.log == []


async def test_some_parts_installed_reads_partial() -> None:
    svc, mcp, _hook = _svc(_agent("a1"))
    mcp.installed.add("a1")
    assert (await svc.status("a1")).state is ConnectionState.PARTIAL


async def test_an_unknown_agent_is_not_found() -> None:
    svc, _mcp, _hook = _svc()
    with pytest.raises(ResourceNotFound):
        await svc.status("ghost")


async def test_connected_agents_are_the_ones_carrying_the_gateway_entry() -> None:
    svc, mcp, hook = _svc(_agent("a1"), _agent("a2"), _agent("a3"), _agent("a4"))
    mcp.installed |= {"a1", "a3", "a4"}
    hook.installed.add("a2")  # a hook alone is not a connection
    mcp.broken.add("a4")  # an unreadable file leaves that agent out, not the rest
    assert await svc.connected_agents() == ["a1", "a3"]
