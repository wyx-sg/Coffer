"""The one-off MCP server test (``infrastructure/mcp/probe.py``) against real processes.

Real subprocesses and a real HTTP fake: a stdio server is started for the test
and gone afterwards — its whole process group, a forked grandchild included —
whether the test passed, failed, ran out of time, or was cancelled.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from coffer.domain.mcp.probe import REDACTED
from coffer.domain.mcp.server_config import HttpTransport, StdioTransport
from coffer.infrastructure.mcp.probe import probe_server
from coffer.infrastructure.net.ssrf_guard import check_url
from tests.fixtures.fake_mcp_server import start_http_fake

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
_FAKE = str(_FIXTURES / "fake_mcp_server.py")
_FORKING = str(_FIXTURES / "forking_mcp_server.py")


def _gone(pid: int, within: float = 3.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


async def _probe(transport: StdioTransport | HttpTransport, **kw: object):
    kw.setdefault("spawn_timeout_seconds", 20)
    kw.setdefault("request_timeout_seconds", 20)
    return await probe_server(transport, kw.pop("overlay", {}), **kw)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_stdio_probe_lists_tools_and_counts_resources_and_prompts() -> None:
    result = await _probe(
        StdioTransport(
            command=sys.executable,
            args=[_FAKE, "--tools", "read", "write", "--resources", "file:///a", "--prompts", "p"],
        )
    )
    assert result.ok, result
    assert [t.name for t in result.tools] == ["read", "write"]
    assert result.tool_count == 2
    assert result.resource_count == 1
    assert result.prompt_count == 1
    assert result.error_code is None
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_stdio_probe_reports_exit_code_and_redacted_stderr() -> None:
    script = (
        "import os, sys; sys.stderr.write('auth failed for ' + os.environ['API_TOKEN'] + '\\n');"
        " sys.exit(3)"
    )
    result = await _probe(
        StdioTransport(command=sys.executable, args=["-c", script]),
        overlay={"API_TOKEN": "tok-typed-value-123"},
    )
    assert not result.ok
    assert result.error_code == "exited"
    assert result.exit_code == 3
    assert result.error_message == "The process exited with code 3."
    assert result.stderr_tail == (f"auth failed for {REDACTED}",)
    assert "tok-typed-value-123" not in repr(result)


@pytest.mark.asyncio
async def test_stdio_probe_command_not_found_is_spawn_failed() -> None:
    result = await _probe(StdioTransport(command="coffer-no-such-launcher-xyz"))
    assert not result.ok
    assert result.error_code == "spawn_failed"
    assert "coffer-no-such-launcher-xyz" in (result.error_message or "")


@pytest.mark.asyncio
async def test_stdio_probe_missing_cwd_is_spawn_failed(tmp_path: Path) -> None:
    result = await _probe(
        StdioTransport(command=sys.executable, args=[_FAKE], cwd=str(tmp_path / "nope"))
    )
    assert result.error_code == "spawn_failed"
    assert "does not exist" in (result.error_message or "")


@pytest.mark.asyncio
async def test_stdio_probe_hard_time_limit(tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    # Serves nothing on stdout: initialize never completes.
    started = time.monotonic()
    result = await _probe(
        StdioTransport(
            command=sys.executable,
            args=[
                _FORKING,
                str(pidfile),
                "serve",
                "--scenario",
                "slow",
                "--init-delay-ms",
                "60000",
            ],
        ),
        total_seconds=5.0,
    )
    assert time.monotonic() - started < 15
    assert result.error_code == "timeout"
    assert _gone(int(pidfile.read_text()))


@pytest.mark.asyncio
async def test_stdio_probe_stops_the_whole_process_group_on_success(tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    result = await _probe(
        StdioTransport(
            command=sys.executable, args=[_FORKING, str(pidfile), "serve", "--tools", "t"]
        )
    )
    assert result.ok, result
    assert _gone(int(pidfile.read_text()))


@pytest.mark.asyncio
async def test_stdio_probe_stops_a_grandchild_the_exited_leader_left(tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    result = await _probe(
        StdioTransport(command=sys.executable, args=[_FORKING, str(pidfile), "exit"])
    )
    assert result.error_code == "exited"
    assert result.exit_code == 1
    assert result.stderr_tail == ("fatal: cannot start",)
    assert _gone(int(pidfile.read_text()))


@pytest.mark.asyncio
async def test_stdio_probe_cancelled_by_the_caller_stops_the_group(tmp_path: Path) -> None:
    pidfile = tmp_path / "grandchild.pid"
    task = asyncio.create_task(
        _probe(
            StdioTransport(
                command=sys.executable,
                args=[
                    _FORKING,
                    str(pidfile),
                    "serve",
                    "--scenario",
                    "slow",
                    "--init-delay-ms",
                    "60000",
                ],
            )
        )
    )
    deadline = time.monotonic() + 10
    while not pidfile.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _gone(int(pidfile.read_text()))


@pytest.mark.asyncio
async def test_http_probe_refuses_a_loopback_url_before_any_request() -> None:
    result = await _probe(HttpTransport(url="http://127.0.0.1:1/mcp"), url_guard=check_url)
    assert result.error_code == "url_refused"
    assert "127.0.0.1" in (result.error_message or "")
    assert result.latency_ms < 1000


@pytest.mark.asyncio
async def test_http_probe_connect_failed() -> None:
    result = await _probe(HttpTransport(url="http://127.0.0.1:9/mcp"), spawn_timeout_seconds=5)
    assert result.error_code in {"connect_failed", "timeout"}
    assert not result.ok


@pytest.mark.asyncio
async def test_http_probe_lists_tools() -> None:
    loop = asyncio.get_running_loop()
    proc, port = await loop.run_in_executor(None, start_http_fake, ["ping", "pong"])
    try:
        result = await _probe(HttpTransport(url=f"http://127.0.0.1:{port}/mcp"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert result.ok, result
    assert {t.name for t in result.tools} == {"ping", "pong"}


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a rejected key is recorded as auth_rejected")
@pytest.mark.asyncio
async def test_http_probe_a_401_is_auth_rejected() -> None:
    async def refuse(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 401 Unauthorized\r\ncontent-length: 0\r\nconnection: close\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(refuse, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result = await _probe(HttpTransport(url=f"http://127.0.0.1:{port}/mcp"))
    finally:
        server.close()
    assert not result.ok
    assert result.error_code == "auth_rejected"
    assert "401" in (result.error_message or "")
