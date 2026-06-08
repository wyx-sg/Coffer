"""Contract test: drive coffer's /mcp endpoint with the official mcp SDK
as a black-box client. If the SDK accepts the responses without raising,
the wire format is spec-compliant.

The test boots an in-process daemon on a random loopback port via a
background thread running uvicorn (same runtime as production), then uses
the mcp SDK's streamablehttp_client + ClientSession to exercise:

    initialize → tools/list → tools/call

If any step raises (Pydantic ValidationError, protocol violation, etc.),
the test fails — so the SDK's own validation is the oracle.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tests.fixtures.keyring import install_in_memory_keyring
from tests.fixtures.net import free_port

_FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"

_TOKEN = "test-oracle-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


@pytest.fixture
async def running_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Boot an in-process daemon on a random port; yield (port, token).

    We use an async fixture so we can await httpx health-checks and the
    REST registration call from within the fixture body.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    # Port range must not clash with other parallel test processes
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59600")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59649")
    install_in_memory_keyring(monkeypatch)

    port = free_port()

    from coffer.surfaces.http.app import create_app
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.daemon_routes import set_port

    app = create_app()
    set_active_token(_TOKEN)
    set_port(port)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: server.run(), daemon=True)
    thread.start()

    # Wait for the server to be ready (up to 15 s to allow Alembic migrations)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail(f"daemon did not bind on port {port} within 15 s")

    # Wait for /api/v1/daemon/status to return 200 (Alembic + lifespan done)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as c:
        for _ in range(60):
            try:
                r = await c.get("/api/v1/daemon/status")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            server.should_exit = True
            thread.join(timeout=5)
            pytest.fail("daemon /status did not return 200 in time")

        # Re-apply the token (lifespan may have set a different one if daemon.json existed)
        set_active_token(_TOKEN)

        # Register a fake MCP server via the REST API so tools/list has something
        r = await c.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": "fs",
                "config": {
                    "transport": {
                        "type": "stdio",
                        "command": sys.executable,
                        "args": [
                            str(_FAKE),
                            "--scenario",
                            "basic",
                            "--tools",
                            "read_file",
                            "write_file",
                        ],
                    },
                },
            },
            headers=_HEADERS,
        )
        assert r.status_code == 201, f"resource registration failed: {r.status_code} {r.text}"

    yield port, _TOKEN

    server.should_exit = True
    thread.join(timeout=10)


@pytest.mark.acceptance(spec="001-mcp-gateway", scenario="register a stdio MCP server")
@pytest.mark.acceptance(
    spec="006-knowledge-base",
    scenario="built-in KB tools appear in client tool list",
)
@pytest.mark.acceptance(
    spec="007-memory",
    scenario="built-in memory tools appear in client tool list",
)
async def test_sdk_round_trip(running_daemon: tuple[int, str]) -> None:
    """Drive the /mcp endpoint via the mcp SDK; SDK validation is the oracle.

    If ClientSession.initialize(), list_tools(), or call_tool() succeed without
    raising, the wire format is spec-compliant (the SDK validates every field
    through its Pydantic models on parse).
    """
    port, token = running_daemon
    mcp_url = f"http://127.0.0.1:{port}/mcp"
    headers = {"X-Coffer-Token": token}

    async with (
        streamablehttp_client(mcp_url, headers=headers) as (
            read,
            write,
            _session_id_getter,
        ),
        ClientSession(read, write) as session,
    ):
        # 1. Initialize — SDK validates InitializeResult shape
        init = await session.initialize()
        assert init.serverInfo.name == "coffer", (
            f"expected serverInfo.name='coffer', got {init.serverInfo.name!r}"
        )

        # 2. tools/list — SDK validates ListToolsResult.
        # Upstream tools must appear; Coffer's own built-in tools (coffer__*)
        # also appear in the list — accept any superset that contains the
        # fake upstream's two tools.
        tools_result = await session.list_tools()
        tool_names = {t.name for t in tools_result.tools}
        assert {"fs__read_file", "fs__write_file"}.issubset(tool_names), (
            f"upstream tools missing from list: {tool_names}"
        )
        # TEST22-002: positively assert that Coffer's own built-in tools
        # (coffer__*) appear in the same listing — this is the acceptance
        # scenario "built-in tools appear in client tool list". Without
        # this check the test passed even when the KB tools were missing.
        assert any(n.startswith("coffer__") for n in tool_names), (
            f"no coffer__ built-in tools found in tools/list: {tool_names}"
        )
        # And the KB tools specifically must be there (spec 006).
        expected_kb_tools = {
            "coffer__list_knowledge_bases",
            "coffer__search_knowledge",
            "coffer__grep_knowledge",
            "coffer__read_document",
        }
        assert expected_kb_tools.issubset(tool_names), (
            f"KB built-in tools missing from tools/list; "
            f"missing={expected_kb_tools - tool_names}; got={sorted(tool_names)}"
        )
        # And the memory tools (spec 007).
        expected_memory_tools = {
            "coffer__recall",
            "coffer__remember",
            "coffer__update_memory",
            "coffer__forget",
            "coffer__list_memory",
        }
        assert expected_memory_tools.issubset(tool_names), (
            f"memory built-in tools missing from tools/list; "
            f"missing={expected_memory_tools - tool_names}; got={sorted(tool_names)}"
        )

        # 3. tools/call — SDK validates CallToolResult
        call_result = await session.call_tool(
            "fs__read_file",
            arguments={"path": "/tmp/oracle-test"},
        )
        # Reaching here means the SDK parsed the response without errors.
        assert call_result.content is not None, "expected non-empty content"
