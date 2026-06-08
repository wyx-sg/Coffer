"""Unit tests for the MCP gateway's session-cwd propagation (spec 007 FR-004).

The shim reports its launch cwd at the ``initialize`` handshake
(``params._meta["coffer/cwd"]``); the gateway captures it and threads it into
built-in tool calls whose input schema declares a ``cwd`` property (the memory
tools). KB tools (no ``cwd`` property) are left untouched. The gateway never
special-cases the memory kind — it dispatches generically off the schema.
"""

from __future__ import annotations

import pytest

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.mcp.gateway import MCPGatewaySession


def _session_with(registry: BuiltinToolRegistry) -> MCPGatewaySession:
    return MCPGatewaySession(
        session_id="s1",
        resource_service=None,  # type: ignore[arg-type]
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


def test_inject_session_cwd_adds_cwd_for_memory_tool():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = "/work/repo"
    params = session._inject_session_cwd(
        "coffer__recall", {"name": "coffer__recall", "arguments": {"query": "x"}}
    )
    assert params["arguments"]["cwd"] == "/work/repo"


def test_inject_session_cwd_respects_caller_supplied_cwd():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = "/daemon"
    params = session._inject_session_cwd(
        "coffer__recall",
        {"name": "coffer__recall", "arguments": {"query": "x", "cwd": "/explicit"}},
    )
    assert params["arguments"]["cwd"] == "/explicit"


def test_inject_session_cwd_skips_tool_without_cwd_property():
    reg, _ = _registry_with_cwd_tool()
    session = _session_with(reg)
    session._session_cwd = "/work/repo"
    params = session._inject_session_cwd(
        "coffer__search_knowledge",
        {"name": "coffer__search_knowledge", "arguments": {"kb": "k", "query": "x"}},
    )
    assert "cwd" not in params["arguments"]
