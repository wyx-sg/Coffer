"""The gateway's side of the gate (spec workflow "Refuse an unapproved write-class
tool call made for a run", "Give the gateway the run's identity at dispatch").

The gate's own decision is tested in
``tests/unit/application/workflow/test_gate.py``. What is tested here is the
seam: that the gateway consults the port only for a session that reported a run
identity, that a refusal reaches the agent instead of the upstream, and — the
claim this whole feature rests on — that the upstream is **provably** untouched
when a call is refused. So the upstream here is a fake connection that records
every request it is asked to make, and the assertion is on that recording, not
on a mock's call count somewhere further up.

The port is faked, not the workflow gate: ``application.mcp`` may not import
``application.workflow``, and a test that reached across would be asserting the
opposite of the fence it is meant to protect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.tiering_config import TieringConfig
from coffer.domain.resource import Resource

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)

REFUSAL: dict[str, Any] = {
    "content": [{"type": "text", "text": "Coffer workflow gate: rejected"}],
    "isError": True,
}


class FakeUpstream:
    """The outside world. Every request it is asked to make is recorded."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append((method, params))
        return {"content": [{"type": "text", "text": "COF-1 created"}], "isError": False}

    def on_notification(self, cb: Any) -> None: ...
    def on_sampling_request(self, cb: Any) -> None: ...
    def on_roots_request(self, cb: Any) -> None: ...


@dataclass
class FakeSupervisor:
    conn: FakeUpstream

    async def get_or_spawn(self, server_name: str) -> FakeUpstream:
        return self.conn

    async def evict(self, server_name: str) -> None: ...


class FakeResources:
    async def get(self, uid: str) -> Resource:
        """The identity path — here, only to label a built-in call's actor."""
        return await self.get_by_name("agent", uid.removeprefix("uid-"))

    async def get_by_name(self, kind: str, name: str) -> Resource:
        return Resource(
            id=1,
            uid=f"uid-{name}",
            kind=kind,
            name=name,
            description=None,
            config={},
            enabled=True,
            created_at=NOW,
            updated_at=NOW,
        )


class FakePrefs:
    async def find(self, *args: Any, **kwargs: Any) -> None:
        return None


@dataclass
class FakeInvocations:
    rows: list[Any] = field(default_factory=list)

    async def insert(self, inv: Any) -> None:
        self.rows.append(inv)


@dataclass
class RecordingGate:
    """A ``ToolCallGatePort`` that records every consultation."""

    answer: dict[str, Any] | None = None
    asked: list[dict[str, Any]] = field(default_factory=list)

    async def check_tool_call(
        self, *, run_context: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        self.asked.append(
            {"run_context": run_context, "tool_name": tool_name, "arguments": arguments}
        )
        return self.answer


@dataclass
class Harness:
    session: MCPGatewaySession
    upstream: FakeUpstream
    gate: RecordingGate


def build(*, gate: RecordingGate | None = None) -> Harness:
    upstream = FakeUpstream()
    registry = BuiltinToolRegistry()
    registry.register(
        BuiltinTool(
            name="write",
            description="write to the vault",
            input_schema={"type": "object", "properties": {}},
            handler=_vault_write,
        )
    )
    session = MCPGatewaySession(
        session_id="s1",
        resource_service=FakeResources(),  # type: ignore[arg-type]
        supervisor=FakeSupervisor(upstream),  # type: ignore[arg-type]
        discovery=None,  # type: ignore[arg-type]
        preferences=FakePrefs(),  # type: ignore[arg-type]
        invocations=FakeInvocations(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        builtin_tools=registry,
        tiering=TieringConfig(enabled=False, budget=100, window_days=30),
        tool_gate=gate,
    )
    return Harness(session, upstream, gate or RecordingGate())


async def _vault_write(args: dict[str, Any]) -> dict[str, Any]:
    return {"written": True}


CALL: dict[str, Any] = {
    "name": "jira__create_issue",
    "arguments": {"project": "COF", "summary": "ship it"},
}


async def _initialize(session: MCPGatewaySession, *, run: str | None) -> None:
    meta: dict[str, Any] = {"coffer/cwd": "/work/repo", "coffer/agent-uid": "uid-claude-code"}
    if run is not None:
        meta["coffer/run"] = run
    await session.handle_initialize({"protocolVersion": "x", "_meta": meta})


# --- an ordinary conversation is untouched -----------------------------------


async def test_a_session_with_no_run_identity_never_consults_the_gate() -> None:
    """The removal ADR's guarantee, asserted rather than assumed: a chat, a
    channel conversation, an agent the owner is driving — the port is not even
    awaited, and the call reaches the upstream exactly as before."""
    h = build(gate=RecordingGate(answer=REFUSAL))
    await _initialize(h.session, run=None)

    result = await h.session.handle_request("tools/call", CALL)

    assert h.gate.asked == []
    assert h.upstream.requests == [
        ("tools/call", {"name": "create_issue", "arguments": CALL["arguments"]})
    ]
    assert result["isError"] is False


async def test_with_no_gate_wired_a_run_s_call_still_dispatches() -> None:
    """``None`` gate is the pre-feature gateway, byte for byte."""
    h = build(gate=None)
    await _initialize(h.session, run="run1/att1")

    await h.session.handle_request("tools/call", CALL)

    assert len(h.upstream.requests) == 1


# --- a run's call is gated ---------------------------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="a write-class tool call without an approval is refused"
)
async def test_a_refused_call_never_reaches_the_upstream() -> None:
    """The upstream recorded nothing — that is the whole claim."""
    h = build(gate=RecordingGate(answer=REFUSAL))
    await _initialize(h.session, run="run1/att1")

    result = await h.session.handle_request("tools/call", CALL)

    assert h.upstream.requests == []
    assert result == REFUSAL


@pytest.mark.acceptance(spec="workflow", scenario="an approved call goes through exactly once")
async def test_an_allowed_call_reaches_the_upstream_exactly_once() -> None:
    """A held call that is approved resumes, and resumes once."""
    h = build(gate=RecordingGate(answer=None))
    await _initialize(h.session, run="run1/att1")

    result = await h.session.handle_request("tools/call", CALL)

    assert h.upstream.requests == [
        ("tools/call", {"name": "create_issue", "arguments": CALL["arguments"]})
    ]
    assert result["isError"] is False


async def test_the_gate_is_asked_about_the_prefixed_name_and_the_real_arguments() -> None:
    """What the developer decides on is what will execute."""
    h = build(gate=RecordingGate(answer=REFUSAL))
    await _initialize(h.session, run="run1/att1")

    await h.session.handle_request("tools/call", CALL)

    assert h.gate.asked == [
        {
            "run_context": "run1/att1",
            "tool_name": "jira__create_issue",
            "arguments": {"project": "COF", "summary": "ship it"},
        }
    ]


async def test_a_call_with_no_arguments_asks_about_an_empty_mapping() -> None:
    h = build(gate=RecordingGate(answer=REFUSAL))
    await _initialize(h.session, run="run1/att1")

    await h.session.handle_request("tools/call", {"name": "jira__ping"})

    assert h.gate.asked[0]["arguments"] == {}


# --- built-ins are never gated -----------------------------------------------


async def test_a_builtin_tool_is_dispatched_without_asking_the_gate() -> None:
    """``coffer__*`` reaches the developer's own vault; there is nothing
    between it and them for a gate to stand in."""
    h = build(gate=RecordingGate(answer=REFUSAL))
    await _initialize(h.session, run="run1/att1")

    result = await h.session.handle_request(
        "tools/call", {"name": "coffer__write", "arguments": {}}
    )

    assert h.gate.asked == []
    assert h.upstream.requests == []
    assert result["isError"] is False
