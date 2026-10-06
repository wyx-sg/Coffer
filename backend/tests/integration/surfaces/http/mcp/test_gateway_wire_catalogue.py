"""The gateway's catalogue, exposure and permissions, on the wire.

Spec mcp-gateway: namespacing and routing, resource and prompt forwarding,
search, tool exposure, switched-off tools and servers, and per-agent scope. A
real daemon app, real ledger upstreams (stdio and stateless HTTP,
``tests/fixtures/ledger_mcp_server.py``) and raw JSON-RPC, so each assertion
names the exact result and the exact count of what an upstream really ran.
"""

from __future__ import annotations

import pathlib
import time
from collections.abc import Iterator
from typing import Any

import pytest

from tests.fixtures.ledger_mcp_server import BUSINESS_ERROR_TEXT, IMAGE_DATA
from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.ledger_wire import (
    call,
    code,
    events,
    http_ledger,
    ledger_transport,
    open_session,
    register,
    result,
    rpc,
    search,
    tool_names,
    wait_for,
)

pytestmark = pytest.mark.timeout(180)

AGENT_A, AGENT_B = "a" * 32, "b" * 32


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


def _stdio(d: BoundaryDaemon, tmp: pathlib.Path, name: str, *args: str) -> tuple[str, pathlib.Path]:
    ledger = tmp / f"{name}.jsonl"
    ledger.touch()
    return register(d, name, ledger_transport(ledger, "--tag", name, *args)), ledger


def _structured(response: Any) -> dict[str, Any]:
    return dict(result(response)["structuredContent"])


def _starts(ledger: pathlib.Path, tool: str) -> int:
    return len(events(ledger, "start", tool))


def _expose(d: BoundaryDaemon, uid: str, tools: list[str], mode: str) -> None:
    """The route knows a server's tools only once discovery saved them: retry a 404."""
    path = f"/api/v1/resources/mcp_server/{uid}/tools/exposure"
    for _ in range(40):
        r = d.client.patch(path, json={"tools": tools, "mode": mode})
        if r.status_code != 404:
            break
        time.sleep(0.25)
    assert r.status_code in (200, 204), r.text


def _toggle(d: BoundaryDaemon, uid: str, tool: str, enabled: bool) -> None:
    verb = "enable" if enabled else "disable"
    r = d.client.post(
        f"/api/v1/resources/mcp_server/{uid}/capabilities/tool/{verb}",
        json={"capability_key": tool},
    )
    assert r.status_code in (200, 204), r.text


def _capability_enabled(d: BoundaryDaemon, uid: str, tool: str) -> bool | None:
    r = d.client.get(f"/api/v1/resources/mcp_server/{uid}/capabilities")
    assert r.status_code == 200, r.text
    rows = r.json().get("tools", [])
    return next((t.get("enabled") for t in rows if t.get("original_name") == tool), None)


def _found(d: BoundaryDaemon, session: str, query: str, top_k: int = 20) -> dict[str, Any]:
    return dict(search(d, session, query, top_k)["structuredContent"])


def _discovered(d: BoundaryDaemon, session: str, name: str) -> None:
    """Make the gateway know ``name``'s tools (found by search whatever their exposure)."""
    wait_for(
        lambda: any(
            t["name"] == f"{name}__image" for t in _found(d, session, f"{name} image")["tools"]
        ),
        f"{name} discovery",
    )


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="tool-name collision across servers is prevented"
)
def test_same_tool_name_on_three_servers_is_namespaced_per_server(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    _stdio(daemon, tmp_path, "a")
    _stdio(daemon, tmp_path, "b")
    h_ledger = tmp_path / "h.jsonl"
    h_ledger.touch()
    with http_ledger(tmp_path, h_ledger, "h") as url:
        register(daemon, "h", {"type": "http", "url": url})
        session = open_session(daemon, AGENT_A)
        wait_for(lambda: "h__echo" in tool_names(daemon, session), "the HTTP server's tools")
        names = tool_names(daemon, session)
        assert {"a__echo", "b__echo", "h__echo"} <= set(names)
        assert "echo" not in names
        assert len(names) == len(set(names))


@pytest.mark.acceptance(spec="mcp-gateway", scenario="route a tool call to the correct upstream")
def test_a_prefixed_call_reaches_only_its_own_upstream_once(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    _, a_ledger = _stdio(daemon, tmp_path, "a")
    _, b_ledger = _stdio(daemon, tmp_path, "b")
    h_ledger = tmp_path / "h.jsonl"
    h_ledger.touch()
    ledgers = {"a": a_ledger, "b": b_ledger, "h": h_ledger}
    with http_ledger(tmp_path, h_ledger, "h") as url:
        register(daemon, "h", {"type": "http", "url": url})
        session = open_session(daemon, AGENT_A)
        wait_for(lambda: "h__echo" in tool_names(daemon, session), "the HTTP server's tools")
        for tag in ("a", "b", "h"):
            before = {t: _starts(p, "echo") for t, p in ledgers.items()}
            reply = call(daemon, session, f"{tag}__echo", {"text": "route"})
            assert _structured(reply)["tag"] == tag
            delta = {t: _starts(p, "echo") - before[t] for t, p in ledgers.items()}
            assert delta == {t: int(t == tag) for t in ledgers}, (tag, delta)


@pytest.mark.acceptance(spec="mcp-gateway", scenario="resources forward through the gateway")
def test_resources_are_listed_and_read_from_their_own_upstream(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    _stdio(daemon, tmp_path, "a")
    _stdio(daemon, tmp_path, "b")
    session = open_session(daemon, AGENT_A)
    uris: list[str] = []

    def both() -> bool:
        uris[:] = [
            r["uri"] for r in result(rpc(daemon, session, "resources/list", {}))["resources"]
        ]
        return {"coffer://a/ledger://same", "coffer://b/ledger://same"} <= set(uris)

    wait_for(both, "both servers' resources")
    for tag in ("a", "b"):
        read = result(
            rpc(daemon, session, "resources/read", {"uri": f"coffer://{tag}/ledger://same"})
        )
        assert read["contents"][0]["text"] == tag


@pytest.mark.acceptance(spec="mcp-gateway", scenario="prompts forward through the gateway")
def test_prompts_are_listed_and_fetched_from_their_own_upstream(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    _stdio(daemon, tmp_path, "a")
    _stdio(daemon, tmp_path, "b")
    session = open_session(daemon, AGENT_A)
    names: list[str] = []

    def both() -> bool:
        names[:] = [p["name"] for p in result(rpc(daemon, session, "prompts/list", {}))["prompts"]]
        return {"a__same", "b__same"} <= set(names)

    wait_for(both, "both servers' prompts")
    for tag in ("a", "b"):
        got = result(
            rpc(
                daemon,
                session,
                "prompts/get",
                {"name": f"{tag}__same", "arguments": {"text": "hi"}},
            )
        )
        assert got["messages"][0]["content"]["text"] == f"{tag}:hi"


def test_an_upstream_business_error_is_passed_through_as_an_in_band_error(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    _, ledger = _stdio(daemon, tmp_path, "a")
    session = open_session(daemon, AGENT_A)
    wait_for(lambda: "a__business_error" in tool_names(daemon, session), "a's tools")
    reply = result(call(daemon, session, "a__business_error"))
    assert reply["isError"] is True
    assert reply["content"][0]["text"] == BUSINESS_ERROR_TEXT
    assert [e["event"] for e in events(ledger, tool="business_error")] == ["start", "done"]


def test_image_content_is_relayed_intact(daemon: BoundaryDaemon, tmp_path: pathlib.Path) -> None:
    _stdio(daemon, tmp_path, "a")
    session = open_session(daemon, AGENT_A)
    wait_for(lambda: "a__image" in tool_names(daemon, session), "a's tools")
    content = result(call(daemon, session, "a__image"))["content"]
    assert content[0] == {"type": "image", "data": IMAGE_DATA, "mimeType": "image/png"}
    assert content[1]["text"] == "a"


def test_a_second_page_of_an_upstreams_tools_is_read_and_callable(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    _, ledger = _stdio(daemon, tmp_path, "pg", "--paged")
    session = open_session(daemon, AGENT_A)
    # ``image`` is only on page two of the upstream's own tools/list.
    wait_for(lambda: "pg__image" in tool_names(daemon, session), "page two of pg's tools")
    found = [t["name"] for t in _found(daemon, session, "pg image")["tools"]]
    assert "pg__image" in found
    assert result(call(daemon, session, "pg__image"))["content"][0]["type"] == "image"
    assert _starts(ledger, "image") == 1


@pytest.fixture
def many(daemon: BoundaryDaemon, tmp_path: pathlib.Path) -> str:
    _stdio(daemon, tmp_path, "many", "--extra-tools", "25")
    session = open_session(daemon, AGENT_A)
    _discovered(daemon, session, "many")
    return session


def test_search_returns_at_most_top_k_real_upstream_schemas(
    daemon: BoundaryDaemon, many: str
) -> None:
    out = search(daemon, many, "ledger tool", 5)["structuredContent"]
    found = out["tools"]
    assert 0 < len(found) <= 5
    assert all("__" in t["name"] and not t["name"].startswith("coffer__") for t in found)
    assert all(isinstance(t["inputSchema"], dict) for t in found)
    assert isinstance(out["total_searched"], int)


@pytest.mark.parametrize(
    "arguments", [{}, {"query": 12}, {"query": "", "top_k": -1}], ids=["none", "number", "negative"]
)
def test_a_malformed_search_is_refused_not_crashed(
    daemon: BoundaryDaemon, many: str, arguments: dict[str, Any]
) -> None:
    r = call(daemon, many, "coffer__search_tools", arguments)
    assert r.status_code == 200, r.text
    body = r.json()
    if "error" in body:
        assert body["error"]["code"] == -32602
    else:
        assert body["result"]["isError"] is True


def test_top_k_above_the_maximum_is_bounded_to_twenty(daemon: BoundaryDaemon, many: str) -> None:
    assert len(_found(daemon, many, "tool_0", 500)["tools"]) == 20


@pytest.mark.parametrize("mode", ["search", "listed", "auto"])
def test_exposure_changes_only_how_a_tool_is_listed_never_whether_it_is_callable(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path, mode: str
) -> None:
    uid, ledger = _stdio(daemon, tmp_path, "b")
    session = open_session(daemon, AGENT_A)
    _discovered(daemon, session, "b")
    _expose(daemon, uid, ["image"], mode)
    listed = "b__image" in tool_names(daemon, session)
    found = any(t["name"] == "b__image" for t in _found(daemon, session, "b image")["tools"])
    if mode == "search":
        assert not listed and found
    elif mode == "listed":
        assert listed
    assert result(call(daemon, session, "b__image"))["content"][0]["type"] == "image"
    assert _starts(ledger, "image") == 1


def test_setting_a_pinned_tool_back_to_auto_clears_the_pin(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    uid, _ = _stdio(daemon, tmp_path, "pin")
    session = open_session(daemon, AGENT_A)
    _discovered(daemon, session, "pin")
    _toggle(daemon, uid, "slow", False)
    _expose(daemon, uid, ["image"], "listed")
    _expose(daemon, uid, ["image"], "auto")
    r = daemon.client.get(f"/api/v1/resources/mcp_server/{uid}/tiering")
    assert r.status_code == 200, r.text
    row = next(t for t in r.json()["tools"] if t["tool"] == "image")
    assert row["mode"] == "auto"


def test_a_tool_switched_off_and_back_on_is_callable_again(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    uid, ledger = _stdio(daemon, tmp_path, "t")
    session = open_session(daemon, AGENT_A)
    _discovered(daemon, session, "t")
    _toggle(daemon, uid, "image", False)
    assert _capability_enabled(daemon, uid, "image") is False
    _toggle(daemon, uid, "image", True)
    assert _capability_enabled(daemon, uid, "image") is True
    fresh = open_session(daemon, AGENT_A)
    assert result(call(daemon, fresh, "t__image"))["content"][0]["type"] == "image"
    assert _starts(ledger, "image") == 1


def test_a_call_to_a_switched_off_server_is_refused_before_the_upstream(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    uid, ledger = _stdio(daemon, tmp_path, "t")
    session = open_session(daemon, AGENT_A)
    _discovered(daemon, session, "t")
    assert daemon.client.post(f"/api/v1/resources/{uid}/disable").status_code == 200
    assert code(call(daemon, session, "t__echo", {"text": "refused"})) == -32000
    assert events(ledger) == []
    assert daemon.client.post(f"/api/v1/resources/{uid}/enable").status_code == 200
    assert (
        result(call(daemon, session, "t__echo", {"text": "again"}))["structuredContent"]["tag"]
        == "t"
    )
    assert _starts(ledger, "echo") == 1


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an out-of-scope server is invisible to a session"
)
def test_a_server_scoped_to_one_agent_is_hidden_from_and_refused_to_others(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    uid, ledger = _stdio(daemon, tmp_path, "s")
    session_a = open_session(daemon, AGENT_A)
    _discovered(daemon, session_a, "s")
    r = daemon.client.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": [AGENT_A]}})
    assert r.status_code == 200, r.text
    invocations = f"/api/v1/resources/mcp_server/{uid}/invocations?limit=50&status=denied"
    before = daemon.client.get(invocations).json()["total"]
    for session in (open_session(daemon, AGENT_B), open_session(daemon)):
        assert not [n for n in tool_names(daemon, session) if n.startswith("s__")]
        assert code(call(daemon, session, "s__echo", {"text": "refused"})) == -32000
    assert events(ledger) == []
    assert daemon.client.get(invocations).json()["total"] - before >= 2
    named = open_session(daemon, AGENT_A)
    assert "s__echo" in tool_names(daemon, named)
    assert (
        result(call(daemon, named, "s__echo", {"text": "in scope"}))["structuredContent"]["tag"]
        == "s"
    )
    assert _starts(ledger, "echo") == 1
