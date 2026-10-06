"""The gateway over a real 127.0.0.1 socket: streams, dropped connections, list changes.

Spec mcp-gateway. The daemon app is served by uvicorn on a real loopback port
in a background thread, with a real ledger stdio upstream
(``tests/fixtures/ledger_mcp_server.py``), driven with httpx. What an
in-process test client cannot show — a client abandoning a connection, a
server-sent-event stream held open — is the subject here.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import socket
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import uvicorn

from tests.fixtures.keyring import install_in_memory_keyring
from tests.fixtures.net import free_port
from tests.support.ledger_wire import LEDGER_SERVER, events, wait_for
from tests.support.mcp_wire import init_params

pytestmark = pytest.mark.timeout(120)

_TOKEN = "test-real-socket-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_ids = itertools.count(1)


@dataclass
class Live:
    base: str
    ledger: pathlib.Path

    def post(self, body: Any, session: str | None = None, timeout: float = 30) -> httpx.Response:
        headers = dict(_HEADERS)
        if session:
            headers["Mcp-Session-Id"] = session
        return httpx.post(f"{self.base}/mcp", json=body, headers=headers, timeout=timeout)

    def open_session(self) -> str:
        body = {"jsonrpc": "2.0", "id": next(_ids), "method": "initialize", "params": init_params()}
        r = self.post(body)
        assert r.status_code == 200 and "result" in r.json(), r.text
        session = r.headers["Mcp-Session-Id"]
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        assert self.post(note, session).status_code == 202
        return session

    def rpc(
        self, session: str, method: str, params: Any = None, timeout: float = 30
    ) -> httpx.Response:
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": next(_ids), "method": method}
        if params is not None:
            body["params"] = params
        return self.post(body, session, timeout)

    def call(
        self, session: str, name: str, args: dict[str, Any] | None = None, timeout: float = 30
    ) -> httpx.Response:
        return self.rpc(session, "tools/call", {"name": name, "arguments": args or {}}, timeout)

    def stream(self, session: str) -> Any:
        headers = {**_HEADERS, "Mcp-Session-Id": session, "Accept": "text/event-stream"}
        return httpx.stream("GET", f"{self.base}/mcp", headers=headers, timeout=30)


@pytest.fixture
def live(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59970")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59979")
    install_in_memory_keyring(monkeypatch)
    port = free_port()

    from coffer.surfaces.http.app import create_app
    from coffer.surfaces.http.auth import set_active_token
    from coffer.surfaces.http.daemon_port import set_port

    app = create_app()
    set_active_token(_TOKEN)
    set_port(port)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                if httpx.get(f"{base}/api/v1/daemon/status", timeout=2).status_code == 200:
                    break
            except (OSError, httpx.HTTPError):
                pass
            assert time.monotonic() < deadline, f"daemon did not come up on port {port}"
            time.sleep(0.1)
        set_active_token(_TOKEN)  # the lifespan may have replaced it

        ledger = tmp_path / "ledger.jsonl"
        ledger.touch()
        transport = {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(LEDGER_SERVER), "--ledger", str(ledger)],
        }
        r = httpx.post(
            f"{base}/api/v1/resources",
            json={"kind": "mcp_server", "name": "up", "config": {"transport": transport}},
            headers=_HEADERS,
        )
        assert r.status_code == 201, r.text
        yield Live(base, ledger)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        set_active_token(None)


def test_session_stays_usable_across_opening_and_closing_its_notification_stream(
    live: Live,
) -> None:
    session = live.open_session()
    assert live.rpc(session, "ping", {}).json()["result"] == {}

    with live.stream(session) as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")

    assert live.rpc(session, "ping", {}).json()["result"] == {}


def test_dropped_http_connection_is_not_a_cancellation(live: Live) -> None:
    session = live.open_session()
    assert "result" in live.call(session, "up__echo", {"text": "warm"}).json()
    marker = {"delay": 1.5}
    with pytest.raises(httpx.TimeoutException):
        live.call(session, "up__slow", marker, timeout=0.5)

    wait_for(lambda: events(live.ledger, "done", "slow"), "the abandoned call to finish", 10)
    time.sleep(1.0)
    assert len(events(live.ledger, "start", "slow")) == 1
    assert len(events(live.ledger, "done", "slow")) == 1
    assert events(live.ledger, "cancelled", "slow") == []


def test_upstream_list_changes_reach_the_sessions_stream_and_the_catalogue_refreshes(
    live: Live,
) -> None:
    session = live.open_session()
    assert "result" in live.call(session, "up__echo", {"text": "warm"}).json()
    seen: list[dict[str, Any]] = []
    ready = threading.Event()
    stop = threading.Event()

    def read() -> None:
        with live.stream(session) as stream:
            ready.set()
            for line in stream.iter_lines():
                if line.startswith("data:") and line[5:].strip():
                    seen.append(json.loads(line[5:]))
                if stop.is_set():
                    return

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    assert ready.wait(10)
    time.sleep(0.5)
    try:
        assert "result" in live.call(session, "up__mutate").json()
        wanted = {f"notifications/{k}/list_changed" for k in ("tools", "resources", "prompts")}
        wait_for(lambda: wanted <= {m.get("method") for m in seen}, "the three list_changed", 20)
    finally:
        stop.set()

    found = live.call(session, "coffer__search_tools", {"query": "added", "top_k": 20}).json()
    names = [t["name"] for t in found["result"]["structuredContent"]["tools"]]
    assert "up__added" in names, found
