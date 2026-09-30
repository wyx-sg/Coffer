"""AgentAttentionSource: at most one item per enabled agent, the most basic
problem first."""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.agent.attention import AgentAttentionSource
from coffer.application.agent.auto_detect import AgentDetection
from coffer.application.agent.connection_service import (
    ConnectionState,
    ConnectionStatus,
    PartStatus,
)
from coffer.application.attention import AttentionAction, Severity
from coffer.domain.agent.detection import DetectionState
from coffer.domain.agent.types import AgentType
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
