"""End-to-end shim tests.

Boot an in-process FastAPI app on a random loopback port + write daemon.json.
Spawn coffer-mcp-shim as a subprocess, send JSON-RPC over its stdin,
read responses on its stdout.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.mcp.credential_resolver import CredentialResolver
from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.mcp.supervisor import SubprocessSupervisor
from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.daemon.pid_lock import write as write_daemon_json
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.mcp.persistence import (
    MCPCapabilityPreferenceRepo,
    MCPInvocationRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router
from coffer.surfaces.http.daemon_routes import set_port
from coffer.surfaces.http.dependencies import set_mcp_session_factory
from coffer.surfaces.http.mcp.protocol_routes import router as mcp_router
from coffer.surfaces.http.mcp.protocol_routes import shutdown_all_sessions
from tests.fixtures.keyring import install_in_memory_keyring
from tests.fixtures.net import free_port

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _stdio_cfg(*tools: str) -> dict:  # type: ignore[type-arg]
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", *tools],
        },
    }


def _build_app_sync(tmp_path: Path, token: str, port: int) -> FastAPI:
    """Build and wire a FastAPI app synchronously (for uvicorn-in-thread use)."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"

    # Create schema + seed data in a fresh event loop
    async def _setup() -> None:
        engine = create_async_engine_with_pragmas(db_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = session_maker(engine)
        audit = AuditService(SqlAlchemyAuditRepo(sm))
        rsvc = ResourceService(
            kinds={
                "mcp_server": Kind(
                    name="mcp_server",
                    display_name="MCP Server",
                    config_schema=MCPServerConfig,
                ),
            },
            repo=SqlAlchemyResourceRepo(sm),
            audit=audit,
        )
        await rsvc.register(
            kind="mcp_server",
            name="fs",
            config=_stdio_cfg("read_file"),
            actor="test",
        )
        await engine.dispose()

    asyncio.new_event_loop().run_until_complete(_setup())

    # Factory: create a new MCPGatewaySession per session_id
    def _mcp_factory(session_id: str) -> MCPGatewaySession:
        engine = create_async_engine_with_pragmas(db_url)
        sm2 = session_maker(engine)
        audit2 = AuditService(SqlAlchemyAuditRepo(sm2))
        rsvc2 = ResourceService(
            kinds={
                "mcp_server": Kind(
                    name="mcp_server",
                    display_name="MCP Server",
                    config_schema=MCPServerConfig,
                ),
            },
            repo=SqlAlchemyResourceRepo(sm2),
            audit=audit2,
        )
        supervisor = SubprocessSupervisor(
            upstream_factory=build_upstream,
            resource_service=rsvc2,
            credential_resolver=CredentialResolver(KeyringAdapter()),
        )
        prefs = MCPCapabilityPreferenceRepo(sm2)
        invs = MCPInvocationRepo(sm2)
        discovery = CapabilityDiscovery(
            resource_service=rsvc2,
            supervisor=supervisor,
            preferences=prefs,
            audit=audit2,
        )
        return MCPGatewaySession(
            session_id=session_id,
            resource_service=rsvc2,
            supervisor=supervisor,
            discovery=discovery,
            preferences=prefs,
            invocations=invs,
        )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_router)
    app.include_router(mcp_router)
    set_mcp_session_factory(_mcp_factory)
    set_active_token(token)
    set_port(port)

    return app


@pytest.fixture
def running_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Start a real uvicorn daemon on a random port + write daemon.json."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    install_in_memory_keyring(monkeypatch)

    port = free_port()
    token = "test-shim-token"

    app = _build_app_sync(tmp_path, token, port)

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for uvicorn to bind
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("uvicorn did not bind within 10s")

    # Also wait for /api/v1/daemon/status to respond
    import httpx

    deadline2 = time.monotonic() + 10
    while time.monotonic() < deadline2:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/v1/daemon/status", timeout=1.0)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.05)

    write_daemon_json(
        home / ".coffer" / "daemon.json",
        DaemonInfo(
            version=1,
            pid=os.getpid(),
            port=port,
            token=token,
            started_at=datetime.now(tz=UTC),
            binary_path=sys.executable,
        ),
    )

    yield home, port, token

    server.should_exit = True
    server_thread.join(timeout=5)
    asyncio.new_event_loop().run_until_complete(shutdown_all_sessions())
    set_active_token(None)


def _spawn_shim(env: dict[str, str]) -> subprocess.Popen[str]:
    cmd = [sys.executable, "-m", "coffer.surfaces.shim.main"]
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **env},
    )


def _send_envelope(proc: subprocess.Popen[str], envelope: dict) -> None:  # type: ignore[type-arg]
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(envelope) + "\n")
    proc.stdin.flush()


def _read_reply(proc: subprocess.Popen[str], timeout: float = 15.0) -> dict:  # type: ignore[type-arg]
    """Read one line of JSON from the shim's stdout."""
    assert proc.stdout is not None
    # Use a thread to implement the timeout on readline
    result: list[str] = []
    exc: list[Exception] = []

    def _read() -> None:
        try:
            line = proc.stdout.readline()  # type: ignore[union-attr]
            result.append(line)
        except Exception as e:
            exc.append(e)

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        raise TimeoutError(f"no reply from shim within {timeout}s")
    if exc:
        raise exc[0]
    line = result[0] if result else ""
    if not line:
        raise RuntimeError("shim closed stdout before replying")
    return json.loads(line)


def test_initialize_round_trip(running_daemon: tuple) -> None:
    home, _port, _token = running_daemon
    proc = _spawn_shim({"HOME": str(home)})
    try:
        _send_envelope(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            },
        )
        reply = _read_reply(proc)
        assert reply["id"] == 1
        assert reply["result"]["serverInfo"]["name"] == "coffer"
    finally:
        proc.stdin.close()  # type: ignore[union-attr]
        proc.wait(timeout=10)


def test_tools_list_round_trip(running_daemon: tuple) -> None:
    home, _port, _token = running_daemon
    proc = _spawn_shim({"HOME": str(home)})
    try:
        _send_envelope(
            proc,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        _read_reply(proc)  # discard init reply
        _send_envelope(
            proc,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        reply = _read_reply(proc)
        assert reply["id"] == 2
        names = {t["name"] for t in reply["result"]["tools"]}
        assert names == {"fs__read_file"}
    finally:
        proc.stdin.close()  # type: ignore[union-attr]
        proc.wait(timeout=10)


def test_stdin_eof_causes_graceful_exit(running_daemon: tuple) -> None:
    home, _port, _token = running_daemon
    proc = _spawn_shim({"HOME": str(home)})
    try:
        _send_envelope(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        _read_reply(proc)
    finally:
        proc.stdin.close()  # type: ignore[union-attr]
        try:
            code = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise
        assert code == 0


# ---------------------------------------------------------------------------
# T16 — unit-cover _wait_for_daemon and _ensure_daemon in-process
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_daemon_returns_none_when_no_daemon_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_wait_for_daemon must return None when ~/.coffer/daemon.json is absent."""
    from coffer.surfaces.cli import _client as _cli_client
    from coffer.surfaces.shim.main import _wait_for_daemon

    empty_home = tmp_path / "empty"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    # Ensure discover() returns None — no daemon.json present
    monkeypatch.setattr(_cli_client, "discover", lambda: None)

    result = await _wait_for_daemon(timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_daemon_returns_info_when_daemon_answers(
    running_daemon: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_wait_for_daemon must return DaemonInfo when the daemon answers /status."""
    home, _port, _token = running_daemon
    from coffer.infrastructure.daemon.pid_lock import read as read_daemon_json
    from coffer.surfaces.cli import _client as _cli_client
    from coffer.surfaces.shim.main import _wait_for_daemon

    monkeypatch.setenv("HOME", str(home))
    # Patch discover() so it reads the daemon.json written by the fixture
    daemon_json = home / ".coffer" / "daemon.json"
    info = read_daemon_json(daemon_json)
    monkeypatch.setattr(_cli_client, "discover", lambda: info)

    result = await _wait_for_daemon(timeout=5.0)
    assert result is not None
    assert result.port == info.port


@pytest.mark.asyncio
async def test_ensure_daemon_exits_3_when_spawn_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_ensure_daemon must call sys.exit(3) when the daemon never comes up."""
    from coffer.surfaces.cli import _client as _cli_client
    from coffer.surfaces.shim import main as shim_main

    empty_home = tmp_path / "empty"
    empty_home.mkdir()
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setattr(_cli_client, "discover", lambda: None)

    # Patch _spawn_daemon so it does nothing (avoids actually launching a process).
    monkeypatch.setattr(shim_main, "_spawn_daemon", lambda: None)
    # Use a very short timeout so the test is fast.
    monkeypatch.setattr(shim_main, "_DAEMON_BOOT_TIMEOUT", 0.1)

    with pytest.raises(SystemExit) as exc_info:
        await shim_main._ensure_daemon()

    assert exc_info.value.code == 3


@pytest.mark.asyncio
async def test_ensure_daemon_returns_info_when_daemon_present(
    running_daemon: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_ensure_daemon must return DaemonInfo without spawning when daemon is live."""
    home, _port, _token = running_daemon
    from coffer.infrastructure.daemon.pid_lock import read as read_daemon_json
    from coffer.surfaces.cli import _client as _cli_client
    from coffer.surfaces.shim import main as shim_main

    monkeypatch.setenv("HOME", str(home))
    daemon_json = home / ".coffer" / "daemon.json"
    info = read_daemon_json(daemon_json)
    monkeypatch.setattr(_cli_client, "discover", lambda: info)

    spawned: list[bool] = []
    monkeypatch.setattr(shim_main, "_spawn_daemon", lambda: spawned.append(True))

    result = await shim_main._ensure_daemon()
    assert result is not None
    assert result.port == info.port
    # Daemon was already up — no spawn should have been attempted
    assert spawned == [], "_spawn_daemon must not be called when daemon is already reachable"
