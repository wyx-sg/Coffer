"""Unit tests for the MCP gateway's session-cwd propagation.

The shim reports its launch cwd at the ``initialize`` handshake
(``params._meta["coffer/cwd"]``); the gateway captures it and threads it into
built-in tool calls whose input schema declares a ``cwd`` property (the memory
tools). KB tools (no ``cwd`` property) are left untouched. The gateway never
special-cases the memory kind — it dispatches generically off the schema.

The ``agent`` argument is the exception to "opt in by schema": it says who is
calling (spec mcp-gateway "Take the agent identity from the handshake"), so
every built-in call carries the SESSION's answer and never the client's —
whatever the client put under ``agent`` is dropped before the tool sees the
arguments.

Its value is the agent's NAME, resolved from the uid the shim reported. The uid
gates what the session may see; the name labels what it did. These tests pin
both ends of that resolution: a live agent's name goes in, and a uid that
resolves to no agent puts nothing in at all.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource

# Opaque uuid4 hex, as the shim reports it.
_CC_UID = "9f2c41a0b7d94e6a8c1f35b2d07ae914"
_CODEX_UID = "3b7e08d1c4f2456ab90d61ea5c2f7d38"
#: A uid that resolves to a row of some OTHER kind — the shim should never send
#: one, but resolving it would label a write with a channel's name.
_NOT_AN_AGENT_UID = "5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c5c"


def _row(uid: str, kind: str, name: str) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        uid=uid,
        kind=kind,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


class _Resources:
    """Just enough ResourceService to resolve a uid to a row."""

    def __init__(self) -> None:
        self._rows = {
            _CC_UID: _row(_CC_UID, "agent", "claude-code"),
            _CODEX_UID: _row(_CODEX_UID, "agent", "codex"),
            _NOT_AN_AGENT_UID: _row(_NOT_AN_AGENT_UID, "channel", "seatalk"),
        }

    async def get(self, uid: str) -> Resource:
        if uid not in self._rows:
            raise ResourceNotFound(f"no resource with uid {uid!r}")
        return self._rows[uid]


def _session_with(registry: BuiltinToolRegistry) -> MCPGatewaySession:
    return MCPGatewaySession(
        session_id="s1",
        resource_service=_Resources(),  # type: ignore[arg-type]
        supervisor=None,  # type: ignore[arg-type]
        discovery=None,  # type: ignore[arg-type]
        preferences=None,  # type: ignore[arg-type]
        invocations=None,  # type: ignore[arg-type]
        builtin_tools=registry,
    )


@pytest.mark.asyncio
async def test_initialize_captures_cwd_from_meta():
    session = _session_with(BuiltinToolRegistry())
    await session.handle_initialize({"protocolVersion": "x", "_meta": {"coffer/cwd": "/work/repo"}})
    assert session._session_cwd == "/work/repo"


@pytest.mark.asyncio
async def test_initialize_without_meta_leaves_cwd_none():
    session = _session_with(BuiltinToolRegistry())
    await session.handle_initialize({"protocolVersion": "x"})
    assert session._session_cwd is None


@pytest.mark.asyncio
async def test_initialize_captures_agent_uid_from_meta():
    """MCP Gateway "Take the agent identity from the handshake": the shim's
    self-reported agent identity rides the same ``_meta`` extension bag as the
    launch cwd, and it is the uid."""
    session = _session_with(BuiltinToolRegistry())
    await session.handle_initialize(
        {"protocolVersion": "x", "_meta": {"coffer/agent-uid": _CC_UID}}
    )
    assert session._session_agent_uid == _CC_UID


@pytest.mark.asyncio
async def test_initialize_without_agent_meta_leaves_session_agent_uid_none():
    session = _session_with(BuiltinToolRegistry())
    await session.handle_initialize({"protocolVersion": "x", "_meta": {"coffer/cwd": "/p"}})
    assert session._session_agent_uid is None


@pytest.mark.asyncio
async def test_initialize_captures_run_context_from_meta():
    """Spec workflow FR-035: a shim launched inside a node's turn reports the
    run identity on the same ``_meta`` bag, so the gateway can attribute the
    tool calls of that session to the run and attempt that caused them."""
    session = _session_with(BuiltinToolRegistry())
    await session.handle_initialize(
        {"protocolVersion": "x", "_meta": {"coffer/run": "run_01J/att_07"}}
    )
    assert session.run_context == "run_01J/att_07"


@pytest.mark.asyncio
async def test_initialize_without_run_meta_leaves_run_context_none():
    """Every conversation a person is driving: no run identity, and therefore
    nothing for a gate to attribute. None, never a default object — a session
    that reports no run must behave exactly as it did before the key existed."""
    session = _session_with(BuiltinToolRegistry())
    await session.handle_initialize(
        {"protocolVersion": "x", "_meta": {"coffer/cwd": "/p", "coffer/agent": "claude_code"}}
    )
    assert session.run_context is None


@pytest.mark.asyncio
async def test_run_context_ignores_a_blank_or_non_string_value():
    """A client that sets the key to something empty is saying nothing, not
    claiming an unnamed run."""
    for value in ("", 7, None):
        session = _session_with(BuiltinToolRegistry())
        await session.handle_initialize({"protocolVersion": "x", "_meta": {"coffer/run": value}})
        assert session.run_context is None


def _registry_with_cwd_tool() -> tuple[BuiltinToolRegistry, list[dict]]:
    seen: list[dict] = []

    async def handler(args):  # type: ignore[no-untyped-def]
        seen.append(args)
        return {"ok": True}

    reg = BuiltinToolRegistry()
    reg.register(
        BuiltinTool(
            name="recall",
            description="memory recall",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}, "cwd": {"type": "string"}},
                "required": ["query"],
            },
            handler=handler,
        )
    )
    reg.register(
        BuiltinTool(
            name="search_knowledge",
            description="kb search (no cwd)",
            input_schema={
                "type": "object",
                "properties": {"kb": {"type": "string"}, "query": {"type": "string"}},
                "required": ["kb", "query"],
            },
            handler=handler,
        )
    )
    return reg, seen


@pytest.mark.asyncio
async def test_inject_session_context_adds_cwd_for_memory_tool():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = "/work/repo"
    params = await session._inject_session_context(
        "coffer__recall", {"name": "coffer__recall", "arguments": {"query": "x"}}
    )
    assert params["arguments"]["cwd"] == "/work/repo"


@pytest.mark.asyncio
async def test_inject_session_context_respects_caller_supplied_cwd():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = "/daemon"
    params = await session._inject_session_context(
        "coffer__recall",
        {"name": "coffer__recall", "arguments": {"query": "x", "cwd": "/explicit"}},
    )
    assert params["arguments"]["cwd"] == "/explicit"


@pytest.mark.asyncio
async def test_inject_session_context_skips_tool_without_cwd_property():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = "/work/repo"
    params = await session._inject_session_context(
        "coffer__search_knowledge",
        {"name": "coffer__search_knowledge", "arguments": {"kb": "k", "query": "x"}},
    )
    assert "cwd" not in params["arguments"]


@pytest.mark.asyncio
async def test_inject_session_context_without_session_cwd_injects_nothing():
    """No reported session cwd ⇒ no cwd injection. Falling back to the daemon's
    own cwd would silently scope agent memory to the DAEMON's project when the
    daemon happens to run inside a git repo (review M5)."""
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = None
    params = await session._inject_session_context(
        "coffer__recall", {"name": "coffer__recall", "arguments": {"query": "x"}}
    )
    assert "cwd" not in params["arguments"]


@pytest.mark.asyncio
async def test_inject_session_context_injects_the_agents_name_not_its_uid():
    """The value a tool receives is the agent's NAME.

    Its one consumer writes it into an audit entry's actor column, which exists
    to be read by a person — a uid there would make the log unreadable by its
    only audience. The uid keeps its own job (the scope gate) and is not what
    travels here."""
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_agent_uid = _CC_UID
    params = await session._inject_session_context(
        "coffer__recall", {"name": "coffer__recall", "arguments": {"query": "x"}}
    )
    assert params["arguments"]["agent"] == "claude-code"


@pytest.mark.asyncio
async def test_inject_session_context_overwrites_a_client_supplied_agent():
    """A client naming another agent is asking for that agent's collections.
    The handshake identity wins, on every tool, whether or not its schema
    mentions ``agent`` — it is not a public property any more."""
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_agent_uid = _CC_UID
    for tool in ("coffer__recall", "coffer__search_knowledge"):
        params = await session._inject_session_context(
            tool, {"name": tool, "arguments": {"query": "x", "agent": "codex"}}
        )
        assert params["arguments"]["agent"] == "claude-code"


@pytest.mark.asyncio
async def test_inject_session_context_injects_nothing_for_a_uid_that_resolves_to_no_agent():
    """A reported uid whose agent has since been deleted, or which names some
    other kind, yields NO argument — so the consumer records an unattributed
    write. That is honest and readable; a bare uid would be neither, since the
    row that could have explained it is the row that is gone."""
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    for uid in ("11112222333344445555666677778888", _NOT_AN_AGENT_UID):
        session._session_agent_uid = uid
        params = await session._inject_session_context(
            "coffer__recall",
            {"name": "coffer__recall", "arguments": {"query": "x", "agent": "codex"}},
        )
        assert "agent" not in params["arguments"], uid


@pytest.mark.asyncio
async def test_inject_session_context_strips_agent_when_the_session_reported_none():
    """No handshake identity ⇒ no identity: the tool sees an unidentified
    caller, not the one the client claimed to be."""
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_agent_uid = None
    params = await session._inject_session_context(
        "coffer__recall",
        {"name": "coffer__recall", "arguments": {"query": "x", "agent": "codex"}},
    )
    assert "agent" not in params["arguments"]


@pytest.mark.asyncio
async def test_inject_session_context_leaves_other_arguments_alone():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_agent_uid = _CC_UID
    params = await session._inject_session_context(
        "coffer__search_knowledge",
        {"name": "coffer__search_knowledge", "arguments": {"kb": "k", "query": "x"}},
    )
    assert params["arguments"] == {"kb": "k", "query": "x", "agent": "claude-code"}
