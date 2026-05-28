"""Drive the fake_mcp_server via the official mcp Python SDK client.

If this test passes, every Phase 3 stdio-upstream test inherits a
known-good fake to wire against.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_FAKE = Path(__file__).resolve().parents[2] / "fixtures" / "fake_mcp_server.py"


def _params(*extra: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(_FAKE), *extra],
    )


@pytest.mark.asyncio
async def test_basic_initialize_and_list_tools() -> None:
    params = _params("--scenario", "basic", "--tools", "read_file", "write_file")
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.list_tools()
    names = [t.name for t in result.tools]
    assert names == ["read_file", "write_file"]


@pytest.mark.asyncio
async def test_call_tool_echoes_arguments() -> None:
    params = _params("--tools", "foo")
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("foo", arguments={"x": 1})
    # The result content is a list of TextContent; first item is our echo.
    payload = result.content[0]
    assert payload.type == "text"
    assert "echo:foo:" in payload.text


@pytest.mark.asyncio
async def test_resources_and_prompts() -> None:
    params = _params(
        "--tools",
        "--resources",
        "file:///tmp/a.txt",
        "--prompts",
        "hello",
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        r = await session.list_resources()
        p = await session.list_prompts()
    assert [str(x.uri) for x in r.resources] == ["file:///tmp/a.txt"]
    assert [x.name for x in p.prompts] == ["hello"]


@pytest.mark.asyncio
async def test_mutating_server_actually_sends_list_changed() -> None:
    """The mutating scenario fires a real notifications/tools/list_changed.

    Drives the fake server in mutating mode through a real MCP ClientSession,
    triggers the notification via a tool call, and asserts the client receives
    the notification.  This test pins that the fixture's send_tool_list_changed()
    path is genuinely wired — a silent no-op (the old try/except pass) would
    leave `received` empty and fail the assertion.
    """
    params = _params(
        "--scenario",
        "mutating",
        "--tools",
        "alpha",
        "beta",
        "--notify-list-changed-after",
        "1",
    )
    received: list[object] = []

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        # We capture notifications via a private SDK hook (_received_notification)
        # because the mcp library (pinned in pyproject.toml) does not yet expose a
        # public notification callback.  The assert below ensures an SDK rename fails
        # loudly rather than silently passing with an empty `received` list.
        assert hasattr(session, "_received_notification"), (
            "MCP SDK changed: notification-capture hook renamed — update this test"
        )
        original_recv = session._received_notification  # type: ignore[attr-defined]

        async def _capture(n: object) -> None:
            received.append(n)
            await original_recv(n)

        session._received_notification = _capture  # type: ignore[method-assign]

        await session.initialize()
        # First call triggers send_tool_list_changed() inside the handler.
        await session.call_tool("alpha", arguments={})
        # Give the server a moment to emit the notification.
        await asyncio.sleep(0.3)

    methods = [
        str(getattr(getattr(n, "root", None), "method", None) or getattr(n, "method", ""))
        for n in received
    ]
    assert any("tools/list_changed" in m for m in methods), (
        f"Expected notifications/tools/list_changed but got: {methods}"
    )


@pytest.mark.asyncio
async def test_crash_scenario_exits_after_n_calls() -> None:
    """`--scenario crash --crash-after-calls 1` makes the server os._exit
    after the first tool call. The client sees the stdio pipe close and
    McpError("Connection closed") propagates out of the context stack."""
    params = _params(
        "--scenario",
        "crash",
        "--tools",
        "boom",
        "--crash-after-calls",
        "1",
    )
    # Let call_tool's McpError propagate naturally — catching it inside the
    # ClientSession context leaves background tasks alive and the TaskGroup hangs.
    # pytest.raises at this level catches after the context managers fully unwind.
    # The combined async-with form wraps McpError in ExceptionGroup, so we keep
    # the nested form here and match on the base Exception class.
    with pytest.raises(Exception, match="unhandled errors in a TaskGroup"):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Server calls os._exit(1) during this call; client surfaces McpError.
                await session.call_tool("boom")
