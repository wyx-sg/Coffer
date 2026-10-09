"""The official MCP SDK as a client of the real ``coffer-mcp-shim`` over stdio.

A real daemon (uvicorn in a thread over a throwaway ``HOME``, with its
``daemon.json``), the shim as a subprocess, real stdio ledger upstreams
(``tests/fixtures/ledger_mcp_server.py``), and ``mcp.client.stdio`` +
``ClientSession`` on the other end of the shim's pipes.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.daemon.pid_lock import write as write_daemon_json
from tests.fixtures.keyring import install_in_memory_keyring
from tests.fixtures.net import free_port
from tests.support.ledger_wire import events, ledger_transport

pytestmark = pytest.mark.timeout(120)

_TOKEN = "test-shim-sdk-token"


@pytest.fixture
def daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, int]]:
    """A real daemon on a loopback port; yields (home, port). ``daemon.json`` is written."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59650")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59699")
    install_in_memory_keyring(monkeypatch)

    from coffer.surfaces.http.app import create_app
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.daemon_port import set_port

    port = free_port()
    app = create_app()
    set_active_token(_TOKEN)
    set_port(port)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            if (
                httpx.get(f"http://127.0.0.1:{port}/api/v1/daemon/status", timeout=1).status_code
                == 200
            ):
                break
        except (OSError, httpx.HTTPError):
            pass
        time.sleep(0.1)
    else:
        server.should_exit = True
        pytest.fail("the daemon did not come up")
    set_active_token(_TOKEN)
    write_daemon_json(
        home / ".coffer" / "daemon.json",
        DaemonInfo(
            version=1,
            pid=os.getpid(),
            port=port,
            token=_TOKEN,
            started_at=datetime.now(tz=UTC),
        ),
    )
    yield home, port
    server.should_exit = True
    thread.join(timeout=10)
    set_active_token(None)


def _register(port: int, name: str, transport: dict) -> None:  # type: ignore[type-arg]
    r = httpx.post(
        f"http://127.0.0.1:{port}/api/v1/resources",
        json={"kind": "mcp_server", "name": name, "config": {"transport": transport}},
        headers={"X-Coffer-Token": _TOKEN},
        timeout=30,
    )
    assert r.status_code == 201, r.text


@asynccontextmanager
async def _client(home: Path, tmp_path: Path) -> AsyncIterator[ClientSession]:
    """The official SDK talking to a shim subprocess."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "coffer.surfaces.shim.main"],
        env={**os.environ, "HOME": str(home)},
        cwd=str(tmp_path),
    )
    with (tmp_path / "shim-stderr.log").open("w") as errlog:
        async with stdio_client(params, errlog=errlog) as (r, w):
            async with ClientSession(r, w, read_timeout_seconds=30) as client:
                await client.initialize()
                yield client


async def test_sdk_over_shim_reaches_stdio_server_with_its_env_and_cwd(
    daemon: tuple[Path, int], tmp_path: Path
) -> None:
    home, port = daemon
    work = tmp_path / "upstream-cwd"
    work.mkdir()
    ledger = tmp_path / "ledger.jsonl"
    transport = ledger_transport(
        ledger, "--tag", "env", env={"LEDGER_ENV": "shim-env"}, cwd=str(work)
    )
    _register(port, "envsrv", transport)

    async with _client(home, tmp_path) as client:
        names = [t.name for t in (await client.list_tools()).tools]
        reply = await client.call_tool("envsrv__environment", {})

    assert names
    assert not reply.is_error
    sc = reply.structured_content or {}
    assert sc["env"] == "shim-env"
    assert Path(sc["cwd"]).resolve() == work.resolve()
    assert sc["tag"] == "env"
    assert len(events(ledger, "done", "environment")) == 1


async def test_shim_lists_two_servers_tools_with_unique_names(
    daemon: tuple[Path, int], tmp_path: Path
) -> None:
    home, port = daemon
    for name in ("srv-a", "srv-b"):
        _register(port, name, ledger_transport(tmp_path / f"{name}.jsonl", "--tag", name))

    async with _client(home, tmp_path) as client:
        names = [t.name for t in (await client.list_tools()).tools]
        a = await client.call_tool("srv-a__echo", {"text": "x"})
        b = await client.call_tool("srv-b__echo", {"text": "x"})

    assert {"srv-a__echo", "srv-b__echo"} <= set(names)
    assert len(names) == len(set(names))
    assert (a.structured_content or {}).get("tag") == "srv-a"
    assert (b.structured_content or {}).get("tag") == "srv-b"


async def test_shim_answers_a_ping_while_a_slow_call_is_in_flight(
    daemon: tuple[Path, int], tmp_path: Path
) -> None:
    home, port = daemon
    ledger = tmp_path / "ledger.jsonl"
    _register(port, "slowsrv", ledger_transport(ledger, "--tag", "slowsrv"))

    async with _client(home, tmp_path) as client:
        await client.list_tools()
        task = asyncio.create_task(client.call_tool("slowsrv__slow", {"delay": 1.0}))
        deadline = time.monotonic() + 15
        while not events(ledger, "start", "slow"):
            assert time.monotonic() < deadline, "the slow call never reached the upstream"
            await asyncio.sleep(0.02)
        await client.send_ping()
        still_running = not task.done()
        done_before_ping_returned = bool(events(ledger, "done", "slow"))
        result = await task

    assert still_running, "the ping was answered only after the slow call finished"
    assert not done_before_ping_returned
    assert not result.is_error
    assert len(events(ledger, "done", "slow")) == 1
