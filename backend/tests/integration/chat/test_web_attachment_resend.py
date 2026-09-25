"""Retrying a message that carried files, over HTTP (spec chat "Show a failed
turn as one inline banner with Retry").

The same real app as ``test_web_attachments``: the real file-backed media store
under ``tmp_path`` and a scripted agent adapter, so a resend is rebuilt from the
persisted row on disk and a swept file is really gone.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from coffer.application.chat.turn_orchestrator import clear_active_turns
from coffer.domain.chat.attachment import Attachment
from coffer.surfaces.http.auth import set_active_token
from tests.integration.chat.test_web_attachments import (
    _PNG,
    _TOKEN,
    _client,
    _conversation,
    _Env,
    _upload,
)


@pytest.fixture(autouse=True)
def _reset_turns() -> Generator[None, None, None]:
    clear_active_turns()
    set_active_token(_TOKEN)
    yield
    set_active_token(None)
    clear_active_turns()


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    return _Env(tmp_path)


def _settled_rows(client: TestClient, conv_id: str, replies: int) -> list[dict[str, Any]]:
    """Poll until ``replies`` assistant replies are committed; return every row."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = client.get(f"/api/v1/chat/conversations/{conv_id}/messages").json()["messages"]
        done = [r for r in rows if r["role"] == "assistant" and r["status"] == "complete"]
        if len(done) >= replies:
            return list(rows)
        time.sleep(0.02)
    raise AssertionError("the turns never settled")


def _send_with_file(client: TestClient, conv_id: str) -> tuple[dict[str, Any], str]:
    png = _upload(client, "shot.png", _PNG, "image/png").json()
    resp = client.post(
        f"/api/v1/chat/conversations/{conv_id}/messages",
        json={"text": "what is this?", "attachment_ids": [png["id"]]},
    )
    assert resp.status_code == 202, resp.text
    user = next(r for r in _settled_rows(client, conv_id, 1) if r["role"] == "user")
    return png, str(user["id"])


@pytest.mark.acceptance(spec="chat", scenario="a retry re-sends the failed message's attachments")
def test_resend_carries_the_original_attachments(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        png, message_id = _send_with_file(client, conv_id)
        resp = client.post(f"/api/v1/chat/conversations/{conv_id}/messages/{message_id}/resend")
        assert resp.status_code == 202, resp.text
        rows = _settled_rows(client, conv_id, 2)

    users = [r for r in rows if r["role"] == "user"]
    assert len(users) == 2
    assert users[1]["id"] != message_id
    assert users[1]["content"] == users[0]["content"]
    assert [(b["type"], b.get("filename")) for b in users[1]["content"]] == [
        ("text", None),
        ("attachment", "shot.png"),
    ]
    stored = Attachment(
        path=str(env.media / f"{png['id']}.png"), mime="image/png", filename="shot.png"
    )
    # Both the original turn and the retry hand the agent the same file.
    assert env.adapter.recorded_attachments == [[stored], [stored]]


@pytest.mark.acceptance(
    spec="chat", scenario="a retry whose attachment was pruned is refused, never sent without it"
)
def test_resend_of_a_swept_attachment_is_410_and_nothing_is_sent(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        png, message_id = _send_with_file(client, conv_id)
        (env.media / f"{png['id']}.png").unlink()  # what the 30-day sweep does
        resp = client.post(f"/api/v1/chat/conversations/{conv_id}/messages/{message_id}/resend")
        rows = client.get(f"/api/v1/chat/conversations/{conv_id}/messages").json()["messages"]

    assert resp.status_code == 410
    error = resp.json()["error"]
    assert error["code"] == "ATTACHMENT_EXPIRED"
    assert "shot.png" in error["message"]
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert env.orchestrator.pending(conv_id) == []
    assert len(env.adapter.recorded_attachments) == 1


def test_resend_of_an_unknown_or_assistant_message_is_404(env: _Env) -> None:
    with _client(env) as client:
        conv_id = _conversation(client)
        _png, _message_id = _send_with_file(client, conv_id)
        rows = client.get(f"/api/v1/chat/conversations/{conv_id}/messages").json()["messages"]
        reply_id = next(r["id"] for r in rows if r["role"] == "assistant")
        unknown = client.post(f"/api/v1/chat/conversations/{conv_id}/messages/nope/resend")
        reply = client.post(f"/api/v1/chat/conversations/{conv_id}/messages/{reply_id}/resend")
        no_conv = client.post("/api/v1/chat/conversations/nope/messages/x/resend")

    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "MESSAGE_NOT_FOUND")
    assert (reply.status_code, reply.json()["error"]["code"]) == (404, "MESSAGE_NOT_FOUND")
    assert (no_conv.status_code, no_conv.json()["error"]["code"]) == (
        404,
        "CONVERSATION_NOT_FOUND",
    )
