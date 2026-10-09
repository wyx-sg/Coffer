"""``coffer__ask``: offered and served only inside a turn Coffer runs (spec
mcp-gateway "Let an agent ask the owner a question during a Coffer turn").

Two levels. Over the real composition root's ``/mcp`` endpoint the listing
follows the ``X-Coffer-Turn`` header; on a gateway session the call blocks until
the owner answers through the chat kind's one answering function.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.testclient import TestClient

from coffer.application.chat import questions
from coffer.application.chat.question_agents import QuestionService
from coffer.application.chat.questions import AnswerInput
from coffer.application.mcp.gateway import MCPGatewaySession
from coffer.application.turn_ask import ASK_TOOL_NAME, NOT_IN_TURN_TEXT, TURN_HEADER
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from tests.support.mcp_wire import INIT_PARAMS


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    questions.clear_all()
    yield
    questions.clear_all()


# --------------------------------------------------------------------------
# Over the real /mcp endpoint
# --------------------------------------------------------------------------


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


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an agent in a Coffer turn sees and calls coffer__ask"
)
@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="coffer__ask is not offered outside a Coffer turn"
)
def test_the_listing_offers_coffer_ask_only_to_a_session_naming_a_live_turn(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59330")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59339")

    with TestClient(create_app()) as client:
        set_active_token("test-token")
        base = {"X-Coffer-Token": "test-token"}
        turn = questions.register_turn("conv-1")

        def names(headers: dict[str, str]) -> set[str]:
            listing = _mcp(client, headers, "tools/list")
            return {t["name"] for t in listing["result"]["tools"]}

        in_turn = names({**base, TURN_HEADER: turn.token})
        terminal = names(base)
        stale = names({**base, TURN_HEADER: "not-a-live-token"})
        questions.release_turn(turn)
        ended = names({**base, TURN_HEADER: turn.token})

        # A direct call outside a turn is answered, not run.
        reply = _mcp(
            client,
            base,
            "tools/call",
            {"name": ASK_TOOL_NAME, "arguments": {"questions": []}},
        )

    assert ASK_TOOL_NAME in in_turn
    assert ASK_TOOL_NAME not in terminal | stale | ended
    assert "coffer__search_tools" in terminal, "the other built-ins are unaffected"
    assert reply["result"]["isError"] is True
    assert reply["result"]["content"][0]["text"] == NOT_IN_TURN_TEXT


# --------------------------------------------------------------------------
# On a gateway session: the call blocks until the owner answers
# --------------------------------------------------------------------------


class _NoServers:
    async def list(self, **_: Any) -> list[Any]:
        return []


class _Invocations:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    async def insert(self, row: Any) -> None:
        self.rows.append(row)


class _Supervisor:
    async def dispose(self) -> None:
        return None


class _Discovery:
    async def list_tools(self, *_: Any, **__: Any) -> list[Any]:  # pragma: no cover
        return []


def _session(invocations: _Invocations) -> MCPGatewaySession:
    return MCPGatewaySession(
        session_id="s1",
        resource_service=_NoServers(),  # type: ignore[arg-type]
        supervisor=_Supervisor(),  # type: ignore[arg-type]
        discovery=_Discovery(),  # type: ignore[arg-type]
        preferences=object(),  # type: ignore[arg-type]
        invocations=invocations,  # type: ignore[arg-type]
        clock=lambda: datetime.now(tz=UTC),
        turn_ask=QuestionService(),
    )


_ASK = {
    "name": ASK_TOOL_NAME,
    "arguments": {
        "context": "A diff",
        "questions": [
            {
                "header": "Apply",
                "question": "Apply this change to staging?",
                "options": [{"label": "Yes"}, {"label": "No"}],
            }
        ],
    },
}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an agent in a Coffer turn sees and calls coffer__ask"
)
@pytest.mark.asyncio
async def test_the_call_returns_the_answer_once_the_owner_gives_it() -> None:
    ctx = questions.register_turn("conv-1")
    invocations = _Invocations()
    session = _session(invocations)
    session.turn_token = ctx.token

    call = asyncio.create_task(session.handle_request("tools/call", _ASK))
    for _ in range(200):
        block = questions.pending_question_for("conv-1")
        if block is not None:
            break
        await asyncio.sleep(0.005)
    else:
        raise AssertionError("the call raised no question")
    assert block.context == "A diff"
    assert not call.done(), "the call must wait for the owner"

    await questions.answer_question(
        "conv-1", block.question_id, [AnswerInput(selected=["Yes"])], via="web", by="ui"
    )
    result = await asyncio.wait_for(call, 2.0)

    assert result["isError"] is False
    answers = json.loads(result["content"][0]["text"])
    assert answers["answered"] is True
    assert answers["answers"] == [
        {
            "header": "Apply",
            "question": "Apply this change to staging?",
            "selected": ["Yes"],
            "text": None,
        }
    ]
    assert [(r.capability_key, r.status) for r in invocations.rows] == [("ask", "ok")]
    questions.release_turn(ctx)


@pytest.mark.asyncio
async def test_a_stopped_turn_tells_the_waiting_call_no_answer_came() -> None:
    ctx = questions.register_turn("conv-1")
    session = _session(_Invocations())
    session.turn_token = ctx.token
    call = asyncio.create_task(session.handle_request("tools/call", _ASK))
    for _ in range(100):
        await asyncio.sleep(0.005)
        if questions.needs_you("conv-1"):
            break

    await questions.close_turn(ctx)
    result = await asyncio.wait_for(call, 2.0)

    assert json.loads(result["content"][0]["text"]) == {
        "answered": False,
        "message": "The owner stopped the task.",
    }


@pytest.mark.asyncio
async def test_a_malformed_ask_is_an_in_band_error_the_agent_can_correct() -> None:
    ctx = questions.register_turn("conv-1")
    session = _session(_Invocations())
    session.turn_token = ctx.token
    result = await session.handle_request(
        "tools/call", {"name": ASK_TOOL_NAME, "arguments": {"questions": [{"question": "q"}]}}
    )
    assert result["isError"] is True
    assert "options" in result["content"][0]["text"]
    assert not questions.needs_you("conv-1")
    questions.release_turn(ctx)


@pytest.mark.asyncio
async def test_a_session_without_a_turn_gets_the_note_not_a_question() -> None:
    session = _session(_Invocations())
    result = await session.handle_request("tools/call", _ASK)
    assert result["isError"] is True
    assert result["content"][0]["text"] == NOT_IN_TURN_TEXT
