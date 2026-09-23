"""spec workflow "Give the gateway the run's identity at dispatch", end to end.

The identity travels four hops, each owned by a different layer, and each has a
unit test of its own. What none of them proves is that the hops meet: that the
string the attempt row yields is the one the shim stamps, that the key the shim
stamps is the one the gateway reads, and that what the gateway hands the gate
is enough to attribute the call to the run and the attempt that made it. So
this test walks all four with the production code at every hop:

1. a task starts and opens its conversation (the real node service and driver,
   over real SQLite rows);
2. ``conversation_env_lookup`` — what the chat providers call when they spawn
   the agent process for that conversation — yields the environment;
3. the MCP shim's ``_inject_meta`` stamps that environment into the
   ``initialize`` handshake;
4. an ``MCPGatewaySession`` takes the handshake, and a ``tools/call`` on it is
   put to the real ``WorkflowToolGate``, whose approval row records what the
   call was attributed to.

The gateway's upstream side is the recording fake its own unit tests use.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.tiering_config import TieringConfig
from coffer.surfaces.http.workflow_adapters import RUN_CONTEXT_ENV, conversation_env_lookup
from coffer.surfaces.shim import bootstrap
from tests.unit.application.mcp.test_gateway_workflow_gate import (
    FakeInvocations,
    FakePrefs,
    FakeResources,
    FakeSupervisor,
    FakeUpstream,
)

from .requirement_harness import TEMPLATE, Daemon, build_daemon

CALL: dict[str, Any] = {
    "name": "jira__create_issue",
    "arguments": {"project": "COF", "summary": "ship it"},
}


@pytest.fixture
async def daemon(tmp_path: pathlib.Path) -> AsyncIterator[Daemon]:
    built, engine = await build_daemon(tmp_path)
    yield built
    await engine.dispose()


def _session(daemon: Daemon, upstream: FakeUpstream) -> MCPGatewaySession:
    return MCPGatewaySession(
        session_id="s1",
        resource_service=FakeResources(),  # type: ignore[arg-type]
        supervisor=FakeSupervisor(upstream),  # type: ignore[arg-type]
        discovery=None,  # type: ignore[arg-type]
        preferences=FakePrefs(),  # type: ignore[arg-type]
        invocations=FakeInvocations(),  # type: ignore[arg-type]
        clock=lambda: datetime.now(tz=UTC),
        builtin_tools=BuiltinToolRegistry(),
        tiering=TieringConfig(enabled=False, budget=100, window_days=30),
        tool_gate=daemon.gate,
    )


def _handshake() -> dict[str, Any]:
    """What a shim launched in the current environment sends as ``initialize``."""
    envelope: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
    }
    bootstrap._inject_meta(envelope, agent_uid="uid-claude-code")
    params: dict[str, Any] = envelope["params"]
    return params


@pytest.mark.acceptance(
    spec="workflow", scenario="a tool call is attributed to the run and task that made it"
)
async def test_the_gateway_attributes_a_call_to_the_run_and_attempt_whose_shim_made_it(
    daemon: Daemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    await daemon.start(run.id, "draft_td")
    attempt = await daemon.attempts.latest_attempt(run.id, "draft_td")
    assert attempt is not None and attempt.conversation_id is not None

    # The agent process for the task's conversation is spawned with this.
    env = await conversation_env_lookup(daemon.attempts)(attempt.conversation_id)
    assert env is not None
    monkeypatch.delenv(RUN_CONTEXT_ENV, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    upstream = FakeUpstream()
    session = _session(daemon, upstream)
    await session.handle_initialize(_handshake())
    result = await session.handle_request("tools/call", CALL)

    # As it dispatched, the gateway knew the run and the attempt: the call was
    # held against exactly that pair, and never reached the upstream.
    assert session.run_context == f"{run.id}/{attempt.id}"
    [held] = await daemon.approvals.list_for_run(run.id)
    assert (held.run_id, held.attempt_id) == (run.id, attempt.id)
    assert held.tool_name == "jira__create_issue"
    assert held.payload == CALL["arguments"]
    assert result["isError"] is True
    assert upstream.requests == []


@pytest.mark.acceptance(
    spec="workflow", scenario="a tool call is attributed to the run and task that made it"
)
async def test_a_shim_launched_outside_any_run_carries_no_run_identity(
    daemon: Daemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await daemon.started_run(await daemon.template(TEMPLATE))
    # An ordinary conversation is not a task's, so its agent gets nothing.
    assert await conversation_env_lookup(daemon.attempts)("an-ordinary-chat") is None
    monkeypatch.delenv(RUN_CONTEXT_ENV, raising=False)

    params = _handshake()
    assert "coffer/run" not in params["_meta"]
    upstream = FakeUpstream()
    session = _session(daemon, upstream)
    await session.handle_initialize(params)
    result = await session.handle_request("tools/call", CALL)

    assert session.run_context is None
    assert await daemon.approvals.list_for_run(run.id) == []
    assert upstream.requests == [
        ("tools/call", {"name": "create_issue", "arguments": CALL["arguments"]})
    ]
    assert result["isError"] is False
