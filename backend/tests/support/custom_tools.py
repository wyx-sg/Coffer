"""Helpers for custom-tool tests against a real in-process daemon.

Builds on ``boundary_daemon``: groups are created through the REST routes, the
secret binding is approved the way the desktop app approves it, and agents are
driven through the real ``/mcp`` JSON-RPC endpoint with a self-reported agent
uid, so every test exercises the gateway exactly as a shim would.
"""

from __future__ import annotations

import itertools
import time
from typing import Any

from tests.support.boundary_daemon import BoundaryDaemon

SECRET_NAME = "billing-token"
SECRET_VALUE = "tok_live_9f8e7d6c5b4a"
_ids = itertools.count(1)


def tool(name: str, method: str, path: str, **extra: Any) -> dict[str, Any]:
    props = {h: {"type": "string"} for h in _holes(path)}
    body: dict[str, Any] = {
        "name": name,
        "method": method,
        "path": path,
        "input_schema": {"type": "object", "properties": props},
    }
    body.update(extra)
    return body


def _holes(path: str) -> list[str]:
    import re

    return re.findall(r"\{([A-Za-z_][A-Za-z0-9_.\-]*)\}", path)


def create_group(
    d: BoundaryDaemon,
    name: str,
    base_url: str,
    tools: list[dict[str, Any]],
    *,
    secret: bool = True,
    approve: bool = True,
    agents: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "base_url": base_url, "tools": tools}
    if secret:
        if d.value(f"secret/{SECRET_NAME}") is None:
            d.store(f"secret/{SECRET_NAME}", SECRET_VALUE)
        body["auth"] = {"header": "Authorization", "prefix": "Bearer ", "secret": SECRET_NAME}
    if agents is not None:
        body["agents"] = agents
    r = d.client.post("/api/v1/custom-tools", json=body)
    assert r.status_code == 201, r.text
    group = dict(r.json())
    if secret and approve:
        for approval_id in group["pending_approvals"]:
            d.approve(approval_id)
        group = get_group(d, name)
    return group


def get_group(d: BoundaryDaemon, name: str) -> dict[str, Any]:
    r = d.client.get(f"/api/v1/custom-tools/{name}")
    assert r.status_code == 200, r.text
    return dict(r.json())


class Agent:
    """One MCP session through ``/mcp``, as a shim with ``--agent-uid`` opens it."""

    def __init__(self, d: BoundaryDaemon, agent_uid: str | None = None) -> None:
        self._d = d
        self.session = f"custom-tools-{next(_ids)}"
        meta = {"coffer/agent-uid": agent_uid} if agent_uid else {}
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "_meta": meta})

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        r = self._d.client.post(
            "/mcp",
            headers={"Mcp-Session-Id": self.session},
            json={"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}},
        )
        assert r.status_code == 200, r.text
        return dict(r.json())

    def tools(self) -> dict[str, dict[str, Any]]:
        return {t["name"]: t for t in self.rpc("tools/list")["result"]["tools"]}

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.rpc("tools/call", {"name": name, "arguments": arguments or {}})


def invocations(
    d: BoundaryDaemon, uid: str, *, expect: int, timeout: float = 5.0
) -> list[dict[str, Any]]:
    """The group's invocation rows once ``expect`` of them are written (the log is buffered)."""
    deadline = time.monotonic() + timeout
    rows: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        r = d.client.get(f"/api/v1/resources/mcp_server/{uid}/invocations")
        assert r.status_code == 200, r.text
        rows = list(r.json()["invocations"])
        if len(rows) >= expect:
            return rows
        time.sleep(0.05)
    return rows


def text_of(result: dict[str, Any]) -> str:
    return "".join(c.get("text", "") for c in result["result"]["content"])
