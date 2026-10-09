"""Raw JSON-RPC on a real daemon's ``/mcp`` against ledger upstreams.

The helpers the wire-level gateway tests share: register a
``tests/fixtures/ledger_mcp_server.py`` upstream (stdio, or stateless HTTP in a
process the caller owns), open a session by the MCP handshake, send one
message, and read back what the upstream really ran from its ledger. The
daemon is :class:`tests.support.boundary_daemon.BoundaryDaemon` — the whole app
over a throwaway ``HOME``.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from tests.support.boundary_daemon import BoundaryDaemon
from tests.support.mcp_wire import init_params

LEDGER_SERVER = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "ledger_mcp_server.py"
_ids = itertools.count(1)


def ledger_transport(ledger: pathlib.Path, *args: str, **extra: Any) -> dict[str, Any]:
    """A stdio transport running the ledger server; ``args`` go on its command line."""
    return {
        "type": "stdio",
        "command": sys.executable,
        "args": [str(LEDGER_SERVER), "--ledger", str(ledger), *args],
        **extra,
    }


def register(d: BoundaryDaemon, name: str, transport: dict[str, Any], **config: Any) -> str:
    """Register an MCP server; returns its uid."""
    body = {"kind": "mcp_server", "name": name, "config": {"transport": transport, **config}}
    r = d.client.post("/api/v1/resources", json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


@contextmanager
def http_ledger(tmp: pathlib.Path, ledger: pathlib.Path, tag: str) -> Iterator[str]:
    """A ledger server over stateless Streamable HTTP; yields its ``/mcp`` URL."""
    ready = tmp / f"{tag}.port"
    cmd = [sys.executable, str(LEDGER_SERVER), "--ledger", str(ledger), "--tag", tag]
    proc = subprocess.Popen([*cmd, "--transport", "http", "--ready", str(ready)])
    try:
        deadline = time.monotonic() + 30
        while not (ready.exists() and ready.read_text()):
            assert proc.poll() is None, "the HTTP ledger server exited"
            assert time.monotonic() < deadline, "the HTTP ledger server never bound"
            time.sleep(0.05)
        yield f"http://127.0.0.1:{ready.read_text()}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def post(
    d: BoundaryDaemon, body: Any, session: str | None = None, headers: dict[str, str] | None = None
) -> Any:
    h = dict(headers or {})
    if session is not None:
        h["Mcp-Session-Id"] = session
    return d.client.post("/mcp", json=body, headers=h)


def open_session(
    d: BoundaryDaemon,
    agent: str | None = None,
    caps: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """``initialize`` + ``notifications/initialized``; returns the session id."""
    if meta is None and agent:
        meta = {"coffer/agent-uid": agent}
    body = {"jsonrpc": "2.0", "id": next(_ids), "method": "initialize"}
    r = post(d, {**body, "params": init_params(meta, caps)})
    assert r.status_code == 200 and "result" in r.json(), r.text
    session = str(r.headers["Mcp-Session-Id"])
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert post(d, note, session).status_code == 202
    return session


def rpc(d: BoundaryDaemon, session: str, method: str, params: Any = None, rid: Any = None) -> Any:
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": next(_ids) if rid is None else rid,
        "method": method,
    }
    if params is not None:
        body["params"] = params
    return post(d, body, session)


def call(
    d: BoundaryDaemon, session: str, name: str, arguments: dict[str, Any] | None = None
) -> Any:
    return rpc(d, session, "tools/call", {"name": name, "arguments": arguments or {}})


def code(response: Any) -> int:
    """The JSON-RPC error code of an HTTP 200 answer."""
    assert response.status_code == 200, response.text
    return int(response.json()["error"]["code"])


def result(response: Any) -> dict[str, Any]:
    assert response.status_code == 200 and "result" in response.json(), response.text
    return dict(response.json()["result"])


def tool_names(d: BoundaryDaemon, session: str) -> list[str]:
    return [t["name"] for t in result(rpc(d, session, "tools/list", {}))["tools"]]


def search(d: BoundaryDaemon, session: str, query: str, top_k: int = 20) -> dict[str, Any]:
    return result(call(d, session, "coffer__search_tools", {"query": query, "top_k": top_k}))


def events(ledger: pathlib.Path, event: str | None = None, tool: str | None = None) -> list[dict]:
    """The ledger's rows, optionally only one event and/or one tool."""
    if not ledger.exists():
        return []
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    return [
        r
        for r in rows
        if (event is None or r["event"] == event) and (tool is None or r["tool"] == tool)
    ]


def wait_for(predicate: Any, what: str, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.02)
