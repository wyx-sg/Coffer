"""No Coffer built-in tool lets the client name who is calling.

Spec mcp-gateway, "Take the agent identity from the handshake": the session's
identity is threaded into a built-in call by the gateway, so no built-in tool
advertises ``agent`` in its input schema. Read over the real composition root's
``/mcp`` endpoint, so every kind's contributed tools are in the listing.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.mcp_wire import INIT_PARAMS


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a built-in tool call carries the session's identity, not the client's",
)
def test_no_built_in_tool_declares_an_agent_property(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59310")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59319")

    with TestClient(create_app()) as c:
        set_active_token("test-token")
        headers = {"X-Coffer-Token": "test-token"}
        init = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS},
            headers=headers,
        )
        assert init.status_code == 200
        r = c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers={**headers, "Mcp-Session-Id": init.headers["mcp-session-id"]},
        )
        assert r.status_code == 200
        builtins = [t for t in r.json()["result"]["tools"] if t["name"].startswith("coffer__")]

    # The one built-in is listed; an empty list would assert nothing.
    assert {t["name"] for t in builtins} == {"coffer__search_tools"}
    offenders = [
        t["name"]
        for t in builtins
        if "agent" in (t.get("inputSchema") or {}).get("properties", {})
        or "agent" in (t.get("inputSchema") or {}).get("required", [])
    ]
    assert offenders == []
