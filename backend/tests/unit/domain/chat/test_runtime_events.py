"""Runtime event value objects + their SSE payload mapping."""

from __future__ import annotations

from coffer.domain.chat.runtime import (
    ChatTurnRequest,
    ConfirmationRequest,
    DoneEvent,
    ErrorEvent,
    TextDelta,
    ToolCallStarted,
    ToolResultEvent,
    TurnMessage,
    event_payload,
)


def test_text_delta_payload():
    assert event_payload(TextDelta(text="hi")) == {"type": "text_delta", "text": "hi"}


def test_tool_call_payload_carries_name_and_args():
    ev = ToolCallStarted(id="t1", tool="coffer__add_memory", args={"text": "x"})
    assert event_payload(ev) == {
        "type": "tool_call",
        "id": "t1",
        "tool": "coffer__add_memory",
        "args": {"text": "x"},
    }


def test_tool_result_payload():
    ev = ToolResultEvent(id="t1", tool="coffer__add_memory", ok=True, summary="created")
    assert event_payload(ev) == {
        "type": "tool_result",
        "id": "t1",
        "tool": "coffer__add_memory",
        "ok": True,
        "summary": "created",
    }


def test_confirmation_request_payload():
    ev = ConfirmationRequest(id="t9", tool="coffer__delete_memory", args={"id": 3})
    assert event_payload(ev) == {
        "type": "confirmation",
        "id": "t9",
        "tool": "coffer__delete_memory",
        "args": {"id": 3},
    }


def test_error_payload_carries_code_and_message():
    ev = ErrorEvent(code="UPSTREAM_UNAVAILABLE", message="boom")
    assert event_payload(ev) == {
        "type": "error",
        "code": "UPSTREAM_UNAVAILABLE",
        "message": "boom",
    }


def test_done_payload():
    assert event_payload(DoneEvent()) == {"type": "done"}


def test_chat_turn_request_holds_history_and_policy():
    req = ChatTurnRequest(
        history=[TurnMessage(role="user", content="prior")],
        user_message="now",
        confirm_tools=["*delete*"],
    )
    assert req.history[0].content == "prior"
    assert req.user_message == "now"
    assert req.confirm_tools == ["*delete*"]
