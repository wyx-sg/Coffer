"""Integration tests for StdioUpstreamConnection.

Each test spawns a real fake_mcp_server subprocess and exercises the
lifecycle: spawn_and_initialize → request(s) → close.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import StdioTransport
from coffer.infrastructure.daemon.orphan_sweep import record_spawn
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
async def test_close_kills_leaked_recorded_process(tmp_path, monkeypatch) -> None:
    """If aclose() fails to tear down the upstream subprocess (observed when a
    long upstream write hangs the SDK teardown), close() must still kill every
    PID it recorded. Otherwise the child leaks and accumulates across reconnects.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    conn = StdioUpstreamConnection(
        transport=_transport("--tools", "read_file"),
        env_overlay={},
    )
    await conn.spawn_and_initialize()

    # Simulate a child that aclose() left behind: a live, recorded sleeper.
    # Record the actual psutil cmdline (as production does) so the reap
    # recycle-guard matches — the venv python3 wrapper execs the framework
    # interpreter, so a constructed argv would not match.
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        # Let the venv python3 wrapper exec into the real interpreter before
        # snapshotting its cmdline (argv[0] flips from the venv shim to the
        # framework interpreter), so the recorded argv matches what psutil
        # reports later. Poll until the cmdline is stable across two reads.
        deadline = time.time() + 5
        prev = psutil.Process(sleeper.pid).cmdline()
        while time.time() < deadline:
            await asyncio.sleep(0.05)
            cur = psutil.Process(sleeper.pid).cmdline()
            if cur and cur == prev:
                break
            prev = cur
        leaked = record_spawn(conn._server_name, sleeper.pid, prev)
        conn._pid_files.append(leaked)

        await conn.close()

        # Poll instead of a fixed sleep — reap escalates SIGTERM→SIGKILL.
        deadline = time.time() + 5
        while time.time() < deadline and sleeper.poll() is None:
            await asyncio.sleep(0.05)
        assert sleeper.poll() is not None, "close() did not kill the leaked upstream process"
        assert not leaked.exists()
    finally:
        if sleeper.poll() is None:
            sleeper.terminate()
            sleeper.wait(timeout=5)


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    conn = StdioUpstreamConnection(
        transport=_transport("--tools", "read_file"),
        env_overlay={},
    )
    await conn.spawn_and_initialize()
    await conn.close()
    await conn.close()  # second close must not raise
