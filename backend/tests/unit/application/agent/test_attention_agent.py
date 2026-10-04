"""AgentAttentionSource: at most one item per enabled agent, the most basic
problem first."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.agent.attention import AgentAttentionSource
from coffer.application.agent.auto_detect import AgentDetection
from coffer.application.agent.connection_service import (
    ConnectionState,
    ConnectionStatus,
    PartStatus,
)
from coffer.application.agent.hooks_service import CofferHook
from coffer.application.attention import AttentionAction, Severity
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.hooks import HookHealth
from coffer.domain.agent.types import AgentType
from coffer.domain.hook_trust import HookTrust
from coffer.domain.workspace_errors import AgentConfigParseError
from tests.unit.application._attention_fakes import FakeResources, resource

MCP_ON = PartStatus(key="mcp", installed=True, detail="shim")
MCP_OFF = PartStatus(key="mcp", installed=False, detail=None)
HOOK_OFF = PartStatus(key="memory_hook", installed=False, detail=None)


def _agent(uid: str, *, enabled: bool = True):  # type: ignore[no-untyped-def]
    return resource(
        uid,
        "agent",
        {"type": "claude_code", "config_dir": f"/agents/{uid}"},
        name=f"claude-{uid}",
        enabled=enabled,
    )


class FakeDetect:
    def __init__(self, states: dict[str, DetectionState]) -> None:
        self.states = states
        self.asked: list[tuple[AgentType, pathlib.Path]] = []

    async def detect(self, agent_type: AgentType, config_dir: pathlib.Path) -> AgentDetection:
        self.asked.append((agent_type, config_dir))
        return AgentDetection(
            self.states.get(config_dir.name, DetectionState.INSTALLED_ACTIVE), None
        )

    async def program_handoff(
        self, agent_type: AgentType, config_dir: str, state: DetectionState, *, registered: bool
    ) -> str | None:
        return f"reinstall {agent_type.value} at {config_dir} ({state.value}, {registered})"


class FakeConnection:
    def __init__(self, statuses: dict[str, ConnectionStatus | Exception]) -> None:
        self.statuses = statuses

    async def status(self, agent_uid: str) -> ConnectionStatus:
        answer = self.statuses[agent_uid]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _status(state: ConnectionState, *parts: PartStatus) -> ConnectionStatus:
    return ConnectionStatus(state=state, parts=parts)


def _source(rows, detect: FakeDetect, conn: FakeConnection) -> AgentAttentionSource:  # type: ignore[no-untyped-def]
    return AgentAttentionSource(agents=FakeResources(rows), detect=detect, connection=conn)


async def test_partial_connection_is_a_warning_naming_the_missing_part() -> None:
    conn = FakeConnection({"a": _status(ConnectionState.PARTIAL, MCP_ON, HOOK_OFF)})
    items = await _source([_agent("a")], FakeDetect({}), conn).items()
    assert len(items) == 1
    item = items[0]
    # Labelled by the product, not the stored name or a title.
    assert (item.kind, item.uid, item.title) == ("agent", "a", "Claude Code")
    assert item.reason_code == "agent_partial"
    assert item.severity is Severity.WARNING
    assert "memory_hook" in item.reason
    assert item.since is None
    assert item.action == AttentionAction(
        verb="connect", method="POST", path="/api/v1/agents/a/coffer-connection"
    )


async def test_disconnected_is_info_with_the_connect_action() -> None:
    conn = FakeConnection({"a": _status(ConnectionState.DISCONNECTED, MCP_OFF)})
    [item] = await _source([_agent("a")], FakeDetect({}), conn).items()
    assert item.reason_code == "agent_not_connected"
    assert item.severity is Severity.INFO
    assert item.title == "Claude Code"
    assert item.action.path == "/api/v1/agents/a/coffer-connection"
    assert item.action.method == "POST"


async def test_connected_agent_reports_nothing() -> None:
    conn = FakeConnection({"a": _status(ConnectionState.CONNECTED, MCP_ON)})
    assert await _source([_agent("a")], FakeDetect({}), conn).items() == []


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an attention item for a missing program carries the reinstall prompt",
)
@pytest.mark.parametrize("state", [DetectionState.CONFIG_ONLY, DetectionState.MISSING])
async def test_missing_program_wins_over_the_connection_state(state: DetectionState) -> None:
    detect = FakeDetect({"a": state})
    # Not even asked: a status here would raise KeyError.
    conn = FakeConnection({})
    [item] = await _source([_agent("a")], detect, conn).items()
    assert item.reason_code == "agent_program_missing"
    assert item.severity is Severity.ERROR
    assert item.action == AttentionAction(verb="check", method="GET", path="/api/v1/agents/a")
    # The fix is a chore for an agent: the item carries the reinstall prompt,
    # and its reason names no command.
    assert item.handoff == f"reinstall claude_code at /agents/a ({state.value}, True)"
    assert "`" not in item.reason and "install -g" not in item.reason
    # Detection is asked about the agent's own type and config dir.
    assert detect.asked == [(AgentType.CLAUDE_CODE, pathlib.Path("/agents/a"))]


async def test_an_unreadable_config_is_a_warning_with_the_check_action() -> None:
    conn = FakeConnection({"a": AgentConfigParseError("/agents/a/settings.json", "bad json")})
    [item] = await _source([_agent("a")], FakeDetect({}), conn).items()
    assert item.reason_code == "agent_config_unreadable"
    assert "cannot parse /agents/a/settings.json" in item.reason
    assert item.severity is Severity.WARNING
    assert item.action == AttentionAction(verb="check", method="GET", path="/api/v1/agents/a")


async def test_disabled_agents_are_not_asked() -> None:
    detect = FakeDetect({"off": DetectionState.MISSING})
    items = await _source([_agent("off", enabled=False)], detect, FakeConnection({})).items()
    assert items == []
    assert detect.asked == []


async def test_a_raising_detection_propagates() -> None:
    class Broken(FakeDetect):
        async def detect(self, agent_type: AgentType, config_dir: pathlib.Path) -> AgentDetection:
            raise RuntimeError("probe died")

    with pytest.raises(RuntimeError, match="probe died"):
        await _source([_agent("a")], Broken({}), FakeConnection({})).items()


def test_source_identity() -> None:
    source = _source([], FakeDetect({}), FakeConnection({}))
    assert (source.name, source.feature) == ("agent", None)


class FakeHooks:
    def __init__(self, hook) -> None:  # type: ignore[no-untyped-def]
        self.hook = hook

    async def coffer_hook(self, uid: str):  # type: ignore[no-untyped-def]
        return self.hook


def _hook(trust: HookTrust, fired: bool = True) -> CofferHook:
    return CofferHook(
        event="SessionStart",
        path="/agents/a/hooks.json",
        health=HookHealth.CURRENT,
        trust=trust,
        installed_command="coffer memory index",
        expected_command="coffer memory index",
        last_fired_at=datetime(2026, 9, 1, tzinfo=UTC) if fired else None,
    )


async def _hook_item(hook):  # type: ignore[no-untyped-def]
    conn = FakeConnection({"a": _status(ConnectionState.CONNECTED, MCP_ON)})
    source = AgentAttentionSource(
        agents=FakeResources([_agent("a")]),
        detect=FakeDetect({}),
        connection=conn,
        hooks=FakeHooks(hook),
    )
    [item] = await source.items()
    assert item.reason_code == "agent_hook_attention"
    assert item.severity is Severity.WARNING
    return item


@pytest.mark.acceptance(
    spec="agent-registry", scenario="a hook the agent has not approved is a warning"
)
@pytest.mark.parametrize("trust", [HookTrust.UNTRUSTED, HookTrust.MODIFIED])
async def test_an_unapproved_hook_is_a_warning(trust) -> None:  # type: ignore[no-untyped-def]
    assert "approved" in (await _hook_item(_hook(trust))).reason


@pytest.mark.acceptance(spec="agent-registry", scenario="a hook that never fired is a warning")
async def test_a_hook_that_never_fired_is_a_warning() -> None:
    item = await _hook_item(_hook(HookTrust.NOT_REQUIRED, fired=False))
    assert "never fired" in item.reason


@pytest.mark.acceptance(spec="agent-registry", scenario="a healthy hook reports nothing")
@pytest.mark.parametrize(
    "hook", [_hook(HookTrust.TRUSTED), _hook(HookTrust.DISABLED, fired=False), None]
)
async def test_a_healthy_or_absent_hook_reports_nothing(hook) -> None:  # type: ignore[no-untyped-def]
    conn = FakeConnection({"a": _status(ConnectionState.CONNECTED, MCP_ON)})
    source = AgentAttentionSource(
        agents=FakeResources([_agent("a")]),
        detect=FakeDetect({}),
        connection=conn,
        hooks=FakeHooks(hook),
    )
    assert await source.items() == []


@pytest.mark.parametrize(
    "hook",
    [_hook(HookTrust.UNTRUSTED), _hook(HookTrust.NOT_REQUIRED, fired=False)],
)
async def test_with_memory_off_a_missing_or_unfired_hook_reports_nothing(hook) -> None:  # type: ignore[no-untyped-def]
    conn = FakeConnection({"a": _status(ConnectionState.CONNECTED, MCP_ON)})

    def source(memory_on: bool) -> AgentAttentionSource:
        return AgentAttentionSource(
            agents=FakeResources([_agent("a")]),
            detect=FakeDetect({}),
            connection=conn,
            hooks=FakeHooks(hook),
            memory_on=lambda: memory_on,
        )

    assert await source(False).items() == []
    [item] = await source(True).items()
    assert item.reason_code == "agent_hook_attention"
