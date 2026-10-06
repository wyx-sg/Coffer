"""A value Coffer injected into a stdio upstream never lands in its log file.

Spec secret "Hold plaintext only in memory at the moment of use". The child is
handed its materialised secrets in its environment; whatever it then prints on
stderr is written to ``logs/upstream/<name>.log``, which the server page's log
read, the diagnosis hand-off and ``coffer log`` all quote. Each test starts a
real synthetic upstream that prints the injected canary on stderr — in one
write, split across two writes with a pause, or right before exiting non-zero —
and reads the raw bytes of that file afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.domain.mcp.server_config import StdioTransport
from coffer.domain.resource import Resource
from coffer.infrastructure.logging.files import upstream_log_path
from coffer.infrastructure.logging.upstream_tail import read_upstream_tail
from coffer.infrastructure.mcp.probe import probe_server
from coffer.infrastructure.mcp.stderr_mask import DRAIN_SECONDS, MASK
from coffer.infrastructure.mcp.subprocess import StdioUpstreamConnection
from coffer.surfaces.http.mcp.handoff_views import diagnose_prompt

_FAKE = Path(__file__).resolve().parents[2] / "fixtures" / "fake_mcp_server.py"
_PLAIN_LINE = "plain progress line ünïcödé 42"
_PLAIN_SETTING = "visible-static-setting-value"

# Prints the canary on stderr the way ``argv[1]`` says, then either exits or
# becomes a working MCP server (the shared fake), so both the "child died" and
# the "session ended normally" paths are exercised.
_UPSTREAM = f"""
import os, runpy, sys, time
value = os.environ["QA_CANARY_SECRET"]
mode = sys.argv[1]
if mode == "split":
    half = len(value) // 2
    os.write(2, ("leak=" + value[:half]).encode())
    time.sleep(0.3)
    os.write(2, (value[half:] + "\\n").encode())
else:
    os.write(2, ("leak=" + value + "\\n").encode())
os.write(2, ({_PLAIN_LINE!r} + "\\n").encode())
os.write(2, ("setting=" + os.environ["PLAIN_SETTING"] + "\\n").encode())
if mode == "exit":
    os.write(2, ("dying with " + value).encode())
    os._exit(3)
if mode == "hang":
    os.write(2, ("hanging with " + value).encode())
    time.sleep(60)
if mode == "orphan":
    # A grandchild that inherits stderr and outlives the server: the pipe
    # never reaches end of file while it lives.
    import subprocess
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
sys.argv = [{str(_FAKE)!r}, "--scenario", "basic", "--tools", "echo"]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


@pytest.fixture
def canary() -> str:
    return f"sk-qa-canary-{secrets.token_hex(12)}"


def _conn(tmp_path: Path, name: str, canary: str, mode: str, **kw) -> StdioUpstreamConnection:
    script = tmp_path / "upstream.py"
    script.write_text(_UPSTREAM)
    return StdioUpstreamConnection(
        transport=StdioTransport(
            type="stdio",
            command=sys.executable,
            args=[str(script), mode],
            env={"PLAIN_SETTING": _PLAIN_SETTING},
        ),
        env_overlay={"QA_CANARY_SECRET": canary},
        server_name=name,
        **kw,
    )


def _resource(name: str) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        uid="r1",
        kind="mcp_server",
        name=name,
        description=None,
        config={"transport": {"type": "stdio", "command": "x"}},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


def _assert_masked_log(name: str, canary: str) -> bytes:
    raw = upstream_log_path(name).read_bytes()
    assert canary.encode() not in raw
    assert f"leak={MASK}\n".encode() in raw
    assert f"{_PLAIN_LINE}\n".encode() in raw
    assert f"setting={_PLAIN_SETTING}\n".encode() in raw
    # What the server page's log read and the diagnosis hand-off quote.
    tail = read_upstream_tail(name, 200)
    assert tail.lines
    assert all(canary not in line.text for line in tail.lines)
    assert canary not in diagnose_prompt(_resource(name), error="boom")
    return raw


@pytest.mark.acceptance(
    spec="secret",
    scenario="an injected secret a stdio server prints on stderr is masked before it is written",
)
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one", "split"])
async def test_a_running_server_s_stderr_is_masked_on_disk(
    tmp_path: Path, canary: str, mode: str
) -> None:
    name = f"leak-{mode}"
    conn = _conn(tmp_path, name, canary, mode)
    try:
        await conn.spawn_and_initialize()
        result = await conn.request("tools/call", {"name": "echo", "arguments": {}})
        assert result.content
    finally:
        await conn.close()
    raw = _assert_masked_log(name, canary)
    # Coffer's own lines bracket the child's output, in order.
    text = raw.decode()
    assert text.index(" coffer start ") < text.index("leak=") < text.index(" coffer stop ")


@pytest.mark.asyncio
async def test_a_child_that_exits_right_after_printing_is_still_masked(
    tmp_path: Path, canary: str
) -> None:
    name = "leak-exit"
    conn = _conn(tmp_path, name, canary, "exit", spawn_timeout_seconds=5)
    with pytest.raises((UpstreamUnavailable, UpstreamTimeout)):
        await conn.spawn_and_initialize()
    await conn.close()
    raw = _assert_masked_log(name, canary)
    # The unterminated last write was flushed, masked, not dropped.
    assert f"dying with {MASK}".encode() in raw


@pytest.mark.asyncio
async def test_coffer_s_own_launch_error_line_never_carries_the_value(
    tmp_path: Path, canary: str
) -> None:
    name = "leak-launch"
    conn = StdioUpstreamConnection(
        transport=StdioTransport(type="stdio", command="coffer-no-such-launcher-qa", args=[]),
        env_overlay={"PATH": f"/opt/{canary}/bin:/usr/bin"},
        server_name=name,
        spawn_timeout_seconds=5,
    )
    with pytest.raises((UpstreamUnavailable, UpstreamTimeout)):
        await conn.spawn_and_initialize()
    await conn.close()
    raw = upstream_log_path(name).read_bytes()
    assert canary.encode() not in raw
    # The whole injected value (here, all of PATH) is what is masked.
    assert f"not found on PATH {MASK}\n".encode() in raw


@pytest.mark.asyncio
async def test_masking_leaks_no_descriptor_and_no_thread(tmp_path: Path, canary: str) -> None:
    me = psutil.Process()
    fds, threads = me.num_fds(), threading.active_count()
    for i, mode in enumerate(["one", "exit", "split"]):
        conn = _conn(tmp_path, f"leak-fd-{i}", canary, mode, spawn_timeout_seconds=5)
        try:
            await conn.spawn_and_initialize()
        except (UpstreamUnavailable, UpstreamTimeout):
            pass
        finally:
            await conn.close()
    # A leak is growth; other tests' threads may finish meanwhile (xdist worker),
    # so the counts may drop but must not rise.
    assert me.num_fds() <= fds
    assert threading.active_count() <= threads


@pytest.mark.asyncio
async def test_a_start_that_times_out_is_masked_and_leaks_nothing(
    tmp_path: Path, canary: str
) -> None:
    me = psutil.Process()
    fds = me.num_fds()
    name = "leak-hang"
    conn = _conn(tmp_path, name, canary, "hang", spawn_timeout_seconds=1)
    with pytest.raises(UpstreamTimeout):
        await conn.spawn_and_initialize()
    await conn.close()
    raw = _assert_masked_log(name, canary)
    assert f"hanging with {MASK}".encode() in raw
    assert b" coffer error did not start within 1s" in raw
    assert me.num_fds() == fds


@pytest.mark.asyncio
async def test_a_cancelled_start_flushes_the_masked_tail_and_leaks_nothing(
    tmp_path: Path, canary: str
) -> None:
    me = psutil.Process()
    fds = me.num_fds()
    name = "leak-cancel"
    conn = _conn(tmp_path, name, canary, "hang", spawn_timeout_seconds=30)
    task = asyncio.create_task(conn.spawn_and_initialize())
    await asyncio.sleep(1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await conn.close()
    raw = upstream_log_path(name).read_bytes()
    assert canary.encode() not in raw
    assert f"hanging with {MASK}".encode() in raw
    assert me.num_fds() == fds


@pytest.mark.asyncio
async def test_a_grandchild_holding_stderr_open_does_not_hold_up_close(
    tmp_path: Path, canary: str
) -> None:
    me = psutil.Process()
    fds = me.num_fds()
    name = "leak-orphan"
    conn = _conn(tmp_path, name, canary, "orphan")
    await conn.spawn_and_initialize()
    await asyncio.sleep(0.3)  # let the server start its grandchild
    family = [p for pid in conn._child_pids for p in psutil.Process(pid).children(recursive=True)]
    started = time.monotonic()
    try:
        await conn.close()
        assert time.monotonic() - started < DRAIN_SECONDS + 8
    finally:
        for proc in family:
            with contextlib.suppress(psutil.NoSuchProcess):
                proc.kill()
    _assert_masked_log(name, canary)
    assert me.num_fds() == fds


@pytest.mark.asyncio
async def test_a_one_off_test_of_the_server_reports_no_injected_value(
    tmp_path: Path, canary: str
) -> None:
    script = tmp_path / "upstream.py"
    script.write_text(_UPSTREAM)
    result = await probe_server(
        StdioTransport(
            type="stdio",
            command=sys.executable,
            args=[str(script), "exit"],
            env={"PLAIN_SETTING": _PLAIN_SETTING},
        ),
        {"QA_CANARY_SECRET": canary},
        spawn_timeout_seconds=5,
        request_timeout_seconds=5,
    )
    assert not result.ok
    joined = "\n".join(result.stderr_tail) + (result.error_message or "")
    assert canary not in joined
    assert _PLAIN_LINE in joined
    assert not list((Path(os.environ["HOME"]) / ".coffer").rglob("upstream/test.log"))
