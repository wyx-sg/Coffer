"""``coffer__channel_read_thread`` over the real composition root's ``/mcp``
endpoint: the channel kind registers it, and the gateway offers and serves it
only to a session inside a live Coffer turn (spec channels "Read a thread's
earlier messages on demand")."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.chat import questions
from coffer.application.turn_ask import TURN_HEADER
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.mcp_wire import INIT_PARAMS

_TOOL = "coffer__channel_read_thread"


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    questions.clear_all()
    yield
    questions.clear_all()


def _mcp(client: TestClient, headers: dict[str, str], method: str, params: Any = None) -> Any:
    init = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": INIT_PARAMS},
        headers=headers,
    )
    sid = init.headers["mcp-session-id"]
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}},
        headers={**headers, "Mcp-Session-Id": sid},
    ).json()


@pytest.mark.acceptance(spec="channels", scenario="the tool is offered only inside a Coffer turn")
def test_the_tool_is_listed_and_served_only_inside_a_turn(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59980")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59989")
    args = {"channel": "nope", "chat_id": "g", "chat_kind": "group", "thread_id": "t"}

    with TestClient(create_app()) as client:
        set_active_token("test-token")
        base = {"X-Coffer-Token": "test-token"}
        turn = questions.register_turn("conv-1")
        in_turn = {**base, TURN_HEADER: turn.token}

        def names(headers: dict[str, str]) -> set[str]:
            return {t["name"] for t in _mcp(client, headers, "tools/list")["result"]["tools"]}

        listed_in_turn = names(in_turn)
        listed_in_terminal = names(base)
        served = _mcp(client, in_turn, "tools/call", {"name": _TOOL, "arguments": args})
        refused = _mcp(client, base, "tools/call", {"name": _TOOL, "arguments": args})
        questions.release_turn(turn)

    assert _TOOL in listed_in_turn
    assert _TOOL not in listed_in_terminal
    # Inside the turn the tool runs, and says which channel it could not find.
    assert served["result"]["isError"] is True
    assert "No running channel named 'nope'" in served["result"]["content"][0]["text"]
    # Outside a turn it is not there at all.
    assert "error" in refused
