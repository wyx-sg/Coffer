"""The ``/mcp`` endpoint answers by the JSON-RPC and MCP lifecycle rules.

Spec mcp-gateway "Answer every MCP message by the JSON-RPC rules", "Take the
agent identity from the handshake" and "Cancel a request only when the client
says so". A real daemon app, a real stdio upstream that writes every call's
fate to a ledger (``tests/fixtures/ledger_mcp_server.py``), and raw JSON-RPC,
so each assertion names the exact code, status and upstream count.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from tests.fixtures.ledger_mcp_server import RPC_ERROR_TEXT
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon

pytestmark = pytest.mark.timeout(120)

_FIXTURE = pathlib.Path(__file__).resolve().parents[4] / "fixtures" / "ledger_mcp_server.py"
_ids = itertools.count(1)
AGENT_A, AGENT_B = "a" * 32, "b" * 32


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def ledger(daemon: BoundaryDaemon, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "ledger.jsonl"
    path.touch()
    transport = {
        "type": "stdio",
        "command": sys.executable,
        "args": [str(_FIXTURE), "--ledger", str(path)],
    }
    r = daemon.client.post(
        "/api/v1/resources",
        json={"kind": "mcp_server", "name": "up", "config": {"transport": transport}},
    )
    assert r.status_code == 201, r.text
    return path


def _events(path: pathlib.Path) -> list[tuple[str, str]]:
    return [(e["event"], e["tool"]) for e in map(json.loads, path.read_text().splitlines())]


def _post(
    d: BoundaryDaemon, body: Any, session: str | None = None, headers: dict[str, str] | None = None
) -> Any:
    h = dict(headers or {})
    if session is not None:
        h["Mcp-Session-Id"] = session
    return d.client.post("/mcp", json=body, headers=h)


def _init_params(agent: str | None = None, caps: dict[str, Any] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "protocolVersion": "2025-06-18",
        "capabilities": caps or {},
        "clientInfo": {"name": "test-client", "version": "1"},
    }
    if agent:
        params["_meta"] = {"coffer/agent-uid": agent}
    return params


def _open(d: BoundaryDaemon, agent: str | None = None) -> str:
    r = _post(
        d,
        {"jsonrpc": "2.0", "id": next(_ids), "method": "initialize", "params": _init_params(agent)},
    )
    assert r.status_code == 200 and "result" in r.json(), r.text
    session = str(r.headers["Mcp-Session-Id"])
    assert (
        _post(d, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session).status_code
        == 202
    )
    return session


def _rpc(d: BoundaryDaemon, session: str, method: str, params: Any = None, rid: Any = None) -> Any:
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": next(_ids) if rid is None else rid,
        "method": method,
    }
    if params is not None:
        body["params"] = params
    return _post(d, body, session)


def _code(response: Any) -> int:
    assert response.status_code == 200, response.text
    return int(response.json()["error"]["code"])


# --- envelopes ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "code", "answer_id"),
    [
        ({"jsonrpc": "2.0", "id": "no-method"}, -32600, "no-method"),
        ({"jsonrpc": "1.0", "id": 3, "method": "ping"}, -32600, 3),
        ({"id": 3, "method": "ping"}, -32600, 3),
        ({"jsonrpc": "2.0", "id": [], "method": "ping"}, -32600, None),
        ({"jsonrpc": "2.0", "id": None, "method": "ping"}, -32600, None),
        ({"jsonrpc": "2.0", "id": True, "method": "ping"}, -32600, None),
        ({"jsonrpc": "2.0", "id": 3, "method": 7}, -32600, 3),
        ({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": ["qa"]}, -32602, 3),
        ({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}}, -32602, 3),
        (
            {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": 1}},
            -32602,
            3,
        ),
        ([], -32600, None),
        ("qa", -32600, None),
    ],
)
@pytest.mark.acceptance(spec="mcp-gateway", scenario="a malformed message gets its JSON-RPC error")
def test_a_malformed_message_gets_its_jsonrpc_error(
    daemon: BoundaryDaemon, body: Any, code: int, answer_id: Any
) -> None:
    r = _post(daemon, body)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "jsonrpc": "2.0",
        "id": answer_id,
        "error": {"code": code, "message": r.json()["error"]["message"]},
    }
    assert "Mcp-Session-Id" not in r.headers


def test_unparseable_json_is_a_parse_error(daemon: BoundaryDaemon) -> None:
    r = daemon.client.post(
        "/mcp", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32700 and r.json()["id"] is None


@pytest.mark.acceptance(spec="mcp-gateway", scenario="only initialize opens a session")
def test_only_initialize_opens_a_session(daemon: BoundaryDaemon) -> None:
    r = _post(daemon, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600
    assert "Mcp-Session-Id" not in r.headers
    r = _post(daemon, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 400
    assert "Mcp-Session-Id" not in r.headers


def test_params_of_the_wrong_shape_are_invalid_params(daemon: BoundaryDaemon) -> None:
    s = _open(daemon)
    assert _code(_rpc(daemon, s, "tools/call", {})) == -32602
    assert _code(_rpc(daemon, s, "tools/call", {"name": ""})) == -32602
    assert _code(_rpc(daemon, s, "tools/call", {"name": "up__echo", "arguments": []})) == -32602
    assert _code(_rpc(daemon, s, "resources/read", {"uri": 5})) == -32602
    assert _code(_rpc(daemon, s, "prompts/get", {})) == -32602
    assert _code(_rpc(daemon, s, "tools/list", {"cursor": 1})) == -32602
    assert _code(_rpc(daemon, s, "tools/call", {"name": "x", "_meta": "no"})) == -32602


def test_a_ping_with_a_string_id_is_answered_with_that_id(daemon: BoundaryDaemon) -> None:
    s = _open(daemon)
    r = _rpc(daemon, s, "ping", rid="qa-string-id")
    assert r.status_code == 200
    assert r.json() == {"jsonrpc": "2.0", "id": "qa-string-id", "result": {}}


def test_delete_is_refused_and_the_session_survives(daemon: BoundaryDaemon) -> None:
    s = _open(daemon)
    r = daemon.client.delete("/mcp", headers={"Mcp-Session-Id": s})
    assert r.status_code == 405
    assert _rpc(daemon, s, "ping").json()["result"] == {}


def test_an_unknown_tool_of_a_known_server_is_invalid_params(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    s = _open(daemon)
    r = _rpc(daemon, s, "tools/call", {"name": "up__qa-unknown", "arguments": {}})
    assert _code(r) == -32602
    assert _events(ledger) == []


@pytest.mark.parametrize(
    ("headers", "statuses"),
    [
        ({"X-Coffer-Token": ""}, (401,)),
        ({"X-Coffer-Token": "qa-wrong-token"}, (401,)),
        ({"Origin": "https://qa-attacker.invalid"}, (403,)),
        ({"Host": "qa-attacker.invalid"}, (403,)),
    ],
)
def test_an_established_session_refuses_a_bad_credential_or_origin(
    daemon: BoundaryDaemon,
    ledger: pathlib.Path,
    headers: dict[str, str],
    statuses: tuple[int, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The suite-wide ``COFFER_ALLOWED_HOSTS=*`` switches the Host check off; allow
    # only the in-process client's own authority so a foreign Host is really judged.
    monkeypatch.setenv("COFFER_ALLOWED_HOSTS", "testserver")
    s = _open(daemon)
    ping = _rpc_with(daemon, s, {"jsonrpc": "2.0", "id": 90, "method": "ping"}, headers)
    assert ping.status_code in statuses, (ping.status_code, ping.text)
    assert "result" not in ping.text
    call = {
        "jsonrpc": "2.0",
        "id": 91,
        "method": "tools/call",
        "params": {"name": "up__echo", "arguments": {"text": "x"}},
    }
    refused = _rpc_with(daemon, s, call, headers)
    assert refused.status_code in statuses, (refused.status_code, refused.text)
    assert _events(ledger) == []
    # The session itself is untouched by the refused requests.
    assert _rpc(daemon, s, "ping").json()["result"] == {}


def _rpc_with(d: BoundaryDaemon, session: str, body: Any, headers: dict[str, str]) -> Any:
    return _post(d, body, session, headers)


# --- error codes --------------------------------------------------------------


@pytest.mark.acceptance(spec="mcp-gateway", scenario="each failure keeps its own JSON-RPC code")
def test_each_failure_keeps_its_own_code(daemon: BoundaryDaemon, ledger: pathlib.Path) -> None:
    s = _open(daemon)
    assert _code(_rpc(daemon, s, "qa/unknown", {})) == -32601
    assert _code(_rpc(daemon, s, "resources/templates/list", {})) == -32601
    assert _code(_rpc(daemon, s, "tools/call", {"name": "no-such-server__echo"})) == -32602
    assert _code(_rpc(daemon, s, "tools/call", {"name": "noprefix"})) == -32602
    assert _code(_rpc(daemon, s, "prompts/get", {"name": "no-such-server__p"})) == -32602
    assert _code(_rpc(daemon, s, "resources/read", {"uri": "coffer://no-such-server/x"})) == -32602
    # The upstream's own JSON-RPC errors keep their code; their text is not relayed.
    wrong = _rpc(daemon, s, "tools/call", {"name": "up__echo", "arguments": {"text": 7}})
    assert _code(wrong) == -32602 and "must be a string" not in wrong.text
    rpc_error = _rpc(daemon, s, "tools/call", {"name": "up__rpc_error", "arguments": {}})
    assert _code(rpc_error) == -32602 and RPC_ERROR_TEXT not in rpc_error.text
    ok = _rpc(daemon, s, "tools/call", {"name": "up__echo", "arguments": {"text": "hi"}})
    assert ok.status_code == 200 and ok.json()["result"]["isError"] is False
    # A switched-off tool keeps Coffer's own code, and no upstream request is made.
    assert "up__echo" in {
        t["name"] for t in _rpc(daemon, s, "tools/list").json()["result"]["tools"]
    }
    uid = daemon.client.get(
        "/api/v1/resources", params={"kind": "mcp_server", "name": "up"}
    ).json()["resources"][0]["uid"]
    r = daemon.client.post(
        f"/api/v1/resources/mcp_server/{uid}/capabilities/tool/disable",
        json={"capability_key": "echo"},
    )
    assert r.status_code in (200, 204), r.text
    before = len(_events(ledger))
    assert (
        _code(_rpc(daemon, s, "tools/call", {"name": "up__echo", "arguments": {"text": "x"}}))
        == -32000
    )
    assert len(_events(ledger)) == before
    # The upstream ran exactly the one valid echo.
    assert _events(ledger) == [("start", "echo"), ("done", "echo")]


# --- protocol version header ----------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an unsupported MCP-Protocol-Version header is refused"
)
def test_the_protocol_version_header_is_checked(daemon: BoundaryDaemon) -> None:
    s = _open(daemon)
    ping = {"jsonrpc": "2.0", "id": 9, "method": "ping"}
    assert _post(daemon, ping, s, {"MCP-Protocol-Version": "2025-06-18"}).json()["result"] == {}
    assert _post(daemon, ping, s).json()["result"] == {}
    bad = _post(daemon, ping, s, {"MCP-Protocol-Version": "qa-invalid"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == -32600
    older = _post(daemon, ping, s, {"MCP-Protocol-Version": "2024-11-05"})
    assert older.status_code == 400
    get = daemon.client.get(
        "/mcp", headers={"Mcp-Session-Id": s, "MCP-Protocol-Version": "qa-invalid"}
    )
    assert get.status_code == 400


def test_a_client_asking_for_another_version_is_offered_the_supported_one(
    daemon: BoundaryDaemon,
) -> None:
    for version in ("2024-11-05", "2099-01-01", "qa-unsupported"):
        params = {**_init_params(), "protocolVersion": version}
        r = _post(daemon, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params})
        assert r.json()["result"]["protocolVersion"] == "2025-06-18"


# --- one handshake per session ----------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a second initialize on a session changes nothing"
)
def test_a_second_initialize_cannot_change_the_identity(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    uid = daemon.client.get(
        "/api/v1/resources", params={"kind": "mcp_server", "name": "up"}
    ).json()["resources"][0]["uid"]
    r = daemon.client.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": [AGENT_A]}})
    assert r.status_code == 200, r.text
    s = _open(daemon, AGENT_B)
    call = {"name": "up__echo", "arguments": {"text": "x"}}
    assert _code(_rpc(daemon, s, "tools/call", call)) == -32000

    again = _rpc(daemon, s, "initialize", _init_params(AGENT_A))
    assert _code(again) == -32600

    assert _code(_rpc(daemon, s, "tools/call", call)) == -32000
    assert _events(ledger) == []
    # A new session may report another identity, as before.
    fresh = _open(daemon, AGENT_A)
    assert _rpc(daemon, fresh, "tools/call", call).json()["result"]["isError"] is False


# --- cancellation -------------------------------------------------------------------


def _wait_for(predicate: Any, what: str, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.02)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a cancelled request stops upstream once and is not answered"
)
def test_a_cancelled_request_reaches_the_upstream_once(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    a, b = _open(daemon), _open(daemon)
    # Warm both connections so the timing below is about the calls alone.
    for s in (a, b):
        assert (
            "result"
            in _rpc(
                daemon, s, "tools/call", {"name": "up__echo", "arguments": {"text": "w"}}
            ).json()
        )
    open(ledger, "w").close()

    with ThreadPoolExecutor(2) as pool:
        slow_a = pool.submit(
            _rpc, daemon, a, "tools/call", {"name": "up__slow", "arguments": {"delay": 20}}, "same"
        )
        slow_b = pool.submit(
            _rpc, daemon, b, "tools/call", {"name": "up__slow", "arguments": {"delay": 1}}, "same"
        )
        _wait_for(lambda: _events(ledger).count(("start", "slow")) == 2, "both calls to start")
        started = time.monotonic()
        # The same id in a different session is not this request.
        cancel = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": "same"},
        }
        assert _post(daemon, cancel, a).status_code == 202
        answer_a, answer_b = slow_a.result(timeout=30), slow_b.result(timeout=30)

    assert answer_a.status_code == 202 and answer_a.content == b""
    assert time.monotonic() - started < 15
    assert answer_b.json()["result"]["isError"] is False
    _wait_for(lambda: ("cancelled", "slow") in _events(ledger), "the upstream to see the cancel")
    events = _events(ledger)
    assert events.count(("start", "slow")) == 2
    assert events.count(("cancelled", "slow")) == 1
    assert events.count(("done", "slow")) == 1


def test_cancelling_an_unknown_or_finished_request_is_harmless(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    s = _open(daemon)
    done = _rpc(daemon, s, "tools/call", {"name": "up__echo", "arguments": {"text": "x"}}, "r1")
    assert done.json()["result"]["isError"] is False
    for rid in ("r1", "never-sent", 42):
        cancel = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": rid},
        }
        assert _post(daemon, cancel, s).status_code == 202
    assert _rpc(daemon, s, "ping", {}).json()["result"] == {}
    assert _events(ledger) == [("start", "echo"), ("done", "echo")]


def test_an_id_still_in_flight_is_refused_not_run_twice(
    daemon: BoundaryDaemon, ledger: pathlib.Path
) -> None:
    s = _open(daemon)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(
            _rpc, daemon, s, "tools/call", {"name": "up__slow", "arguments": {"delay": 1}}, "dup"
        )
        _wait_for(lambda: ("start", "slow") in _events(ledger), "the first call to start")
        second = _rpc(
            daemon, s, "tools/call", {"name": "up__slow", "arguments": {"delay": 1}}, "dup"
        )
        assert _code(second) == -32600
        assert first.result(timeout=30).json()["result"]["isError"] is False
    assert _events(ledger).count(("start", "slow")) == 1
