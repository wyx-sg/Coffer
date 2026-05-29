"""Integration tests for StdioUpstreamConnection.

Each test spawns a real fake_mcp_server subprocess and exercises the
lifecycle: spawn_and_initialize → request(s) → close.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import StdioTransport
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _transport(*extra: str, scenario: str = "basic") -> StdioTransport:
    return StdioTransport(
        type="stdio",
        command=sys.executable,
        args=[str(_FAKE), "--scenario", scenario, *extra],
    )


@pytest.mark.asyncio
async def test_spawn_and_initialize_returns_capabilities() -> None:
    conn = StdioUpstreamConnection(
        transport=_transport("--tools", "read_file"),
        env_overlay={},
    )
    try:
        caps = await conn.spawn_and_initialize()
        assert isinstance(caps, dict)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_request_list_tools() -> None:
    conn = StdioUpstreamConnection(
        transport=_transport("--tools", "read_file", "write_file"),
        env_overlay={},
    )
    try:
        await conn.spawn_and_initialize()
        result = await conn.request("tools/list", {})
        names = [t.name for t in result.tools]
        assert names == ["read_file", "write_file"]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_request_tools_call() -> None:
    conn = StdioUpstreamConnection(
        transport=_transport("--tools", "echo"),
        env_overlay={},
    )
    try:
        await conn.spawn_and_initialize()
        result = await conn.request("tools/call", {"name": "echo", "arguments": {"x": 1}})
        # fake server's echo returns "echo:NAME:ARGS"
        assert result.content[0].type == "text"
        assert "echo:echo:" in result.content[0].text
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_spawn_timeout() -> None:
    """fake_mcp_server --scenario slow --init-delay-ms 2000 vs spawn_timeout=1."""
    conn = StdioUpstreamConnection(
        transport=_transport("--init-delay-ms", "2000", scenario="slow"),
        env_overlay={},
        spawn_timeout_seconds=1,
    )
    with pytest.raises((UpstreamTimeout, UpstreamUnavailable)):
        await conn.spawn_and_initialize()
    await conn.close()


@pytest.mark.asyncio
async def test_env_overlay_passed_through(tmp_path: Path) -> None:
    """Verify the env_overlay reaches the subprocess.

    Write a tiny script that captures the env and exits — we don't need
    it to speak MCP. Verify the env file was written with the overlay value.
    """
    import asyncio

    script = tmp_path / "envprobe.py"
    out_file = tmp_path / "env.out"
    script.write_text(
        f"""
import os, sys
with open({str(out_file)!r}, "w") as f:
    f.write(os.environ.get("MARKER", "MISSING"))
sys.exit(0)
"""
    )
    conn = StdioUpstreamConnection(
        transport=StdioTransport(
            type="stdio",
            command=sys.executable,
            args=[str(script)],
        ),
        env_overlay={"MARKER": "I_AM_HERE"},
        spawn_timeout_seconds=3,
    )
    # spawn_and_initialize will fail because the script doesn't speak MCP,
    # but the env file should have been written before the SDK gives up.
    with pytest.raises((UpstreamTimeout, UpstreamUnavailable)):
        await conn.spawn_and_initialize()
    await conn.close()
    # Give the OS a beat for the file to flush
    await asyncio.sleep(0.1)
    assert out_file.exists(), "subprocess didn't run"
    assert out_file.read_text() == "I_AM_HERE"


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    conn = StdioUpstreamConnection(
        transport=_transport("--tools", "read_file"),
        env_overlay={},
    )
    await conn.spawn_and_initialize()
    await conn.close()
    await conn.close()  # second close must not raise
