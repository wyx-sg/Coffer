"""What each reply changed in each file, end to end (spec chat "Record what each
reply changed in each file").

Real SQLite repos (``chat_reply_files`` with its cascade), the real routes and
turn runner, and a scripted adapter that reports the files it changed — plus the
Claude adapter's snapshot hook driven through a scripted SDK session on a
temporary directory.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from fastapi import FastAPI
from sqlalchemy import text

from coffer.application.chat.attachments import ChatAttachmentService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.chat.reply_file import ReplyFile
from coffer.infrastructure.chat.claude_sdk_agent import ClaudeSdkAgentAdapter
from coffer.infrastructure.chat.media_store import FileChatMediaStore
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.persistence import models as _models  # noqa: F401  (registers tables)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry,
    get_attachment_service,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.reply_file_routes import router as reply_file_router
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import get_resource_service
from tests.unit.chat.conftest import FakeAgentAdapter, make_registry

_TOKEN = "test-token"

_EDITED = ReplyFile(
    "/w/ws_client.py",
    2,
    1,
    "--- a/w/ws_client.py\n+++ b/w/ws_client.py\n@@ -1 +1,2 @@\n-a\n+b\n+c\n",
)
_NEW = ReplyFile(
    "/w/test_ws.py", 3, 0, "--- a/w/test_ws.py\n+++ b/w/test_ws.py\n@@ -0,0 +1,3 @@\n+x\n+y\n+z\n"
)
_BIG = ReplyFile("/w/big.bin", 90000, 0, None, "too_large")


class _NoChannels:
    async def list(self, **_: object) -> list[Any]:
        return []


class _ReportingAdapter(FakeAgentAdapter):
    """A scripted adapter that, like the real ones, says what it changed."""

    def __init__(self, files: list[ReplyFile]) -> None:
        super().__init__(
            [
                TurnStarted(),
                TextDelta(text="done"),
                TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn"),
            ]
        )
        self.reply_files = files


class _Env:
    def __init__(self, tmp_path: Path, files: list[ReplyFile]) -> None:
        self.engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
        self.sm = session_maker(self.engine)
        self.messages = MessageRepo(self.sm)
        registry, _ = make_registry(_ReportingAdapter(files))
        self.chat = ChatService(
            conversations=ConversationRepo(self.sm), messages=self.messages, registry=registry
        )
        orchestrator = TurnOrchestrator(chat_service=self.chat, registry=registry)
        app = FastAPI()
        err_handlers.register(app)
        for router in (reply_file_router, conversation_router, turn_router):
            app.include_router(router)
        app.dependency_overrides[get_chat_service] = lambda: self.chat
        app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
        app.dependency_overrides[get_agent_registry] = lambda: registry
        attachments = ChatAttachmentService(FileChatMediaStore(tmp_path / "media"))
        app.dependency_overrides[get_attachment_service] = lambda: attachments
        app.dependency_overrides[get_resource_service] = lambda: _NoChannels()
        self.app = app


@pytest.fixture
async def env(tmp_path: Path):  # type: ignore[no-untyped-def]
    set_active_token(_TOKEN)
    e = _Env(tmp_path, [_EDITED, _NEW, _BIG])
    async with e.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield e
    set_active_token(None)
    await e.engine.dispose()


def _client(env: _Env) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=env.app),
        base_url="http://test",
        headers={"X-Coffer-Token": _TOKEN},
    )


async def _run_turn(client: httpx.AsyncClient) -> tuple[str, str]:
    """Send one message and return ``(conversation id, assistant message id)``."""
    conv = (await client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})).json()[
        "id"
    ]
    sent = await client.post(f"/api/v1/chat/conversations/{conv}/messages", json={"text": "go"})
    assert sent.status_code == 202
    for _ in range(250):
        rows = (await client.get(f"/api/v1/chat/conversations/{conv}/messages")).json()["messages"]
        done = [r for r in rows if r["role"] == "assistant" and r["status"] == "complete"]
        if done:
            return conv, str(done[0]["id"])
        await asyncio.sleep(0.02)
    raise AssertionError("the turn never settled")


async def test_a_replys_files_are_recorded_and_read_over_http(env: _Env) -> None:
    client = _client(env)
    conv, reply = await _run_turn(client)
    base = f"/api/v1/chat/conversations/{conv}/messages/{reply}/files"

    listed = await client.get(base)
    assert listed.status_code == 200
    assert listed.json() == {
        "files": [
            {"path": "/w/ws_client.py", "added": 2, "removed": 1, "has_diff": True},
            {"path": "/w/test_ws.py", "added": 3, "removed": 0, "has_diff": True},
            {"path": "/w/big.bin", "added": 90000, "removed": 0, "has_diff": False},
        ]
    }

    one = await client.get(f"{base}/diff", params={"path": "/w/test_ws.py"})
    assert one.status_code == 200
    assert one.json() == {
        "path": "/w/test_ws.py",
        "added": 3,
        "removed": 0,
        "diff": _NEW.diff,
        "diff_omitted": None,
    }

    big = await client.get(f"{base}/diff", params={"path": "/w/big.bin"})
    assert big.json() == {
        "path": "/w/big.bin",
        "added": 90000,
        "removed": 0,
        "diff": None,
        "diff_omitted": "too_large",
    }


@pytest.mark.acceptance(spec="chat", scenario="a binary file is listed without a diff")
async def test_a_file_without_a_diff_is_listed_as_having_none(env: _Env) -> None:
    client = _client(env)
    conv, reply = await _run_turn(client)

    listed = await client.get(f"/api/v1/chat/conversations/{conv}/messages/{reply}/files")
    big = next(f for f in listed.json()["files"] if f["path"] == "/w/big.bin")

    assert big == {"path": "/w/big.bin", "added": 90000, "removed": 0, "has_diff": False}


async def test_unknown_messages_and_paths_are_404(env: _Env) -> None:
    client = _client(env)
    conv, reply = await _run_turn(client)
    other = (await client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"})).json()[
        "id"
    ]
    user = (await client.get(f"/api/v1/chat/conversations/{conv}/messages")).json()["messages"][0][
        "id"
    ]
    prefix = "/api/v1/chat/conversations"

    async def code(url: str, **params: str) -> tuple[int, str]:
        r = await client.get(url, params=params)
        return r.status_code, r.json()["error"]["code"]

    assert await code(f"{prefix}/{conv}/messages/nope/files") == (404, "MESSAGE_NOT_FOUND")
    assert await code(f"{prefix}/{conv}/messages/{user}/files") == (404, "MESSAGE_NOT_FOUND")
    # a reply of ANOTHER conversation is not this one's
    assert await code(f"{prefix}/{other}/messages/{reply}/files") == (404, "MESSAGE_NOT_FOUND")
    assert await code(f"{prefix}/nope/messages/{reply}/files") == (404, "CONVERSATION_NOT_FOUND")
    assert await code(f"{prefix}/{other}/messages/{reply}/files/diff", path="/w/test_ws.py") == (
        404,
        "MESSAGE_NOT_FOUND",
    )
    assert await code(f"{prefix}/{conv}/messages/{reply}/files/diff", path="/w/other.py") == (
        404,
        "REPLY_FILE_NOT_FOUND",
    )


async def test_a_reply_with_no_records_lists_none(env: _Env) -> None:
    conv = (await env.chat.create_conversation(agent_key="builtin")).id
    msg = await env.chat.append_message(conv, role=Role.ASSISTANT, content=[TextBlock(text="hi")])
    client = _client(env)

    r = await client.get(f"/api/v1/chat/conversations/{conv}/messages/{msg.id}/files")

    assert (r.status_code, r.json()) == (200, {"files": []})


async def _rows(env: _Env) -> int:
    async with env.sm() as s:
        return int((await s.execute(text("SELECT count(*) FROM chat_reply_files"))).scalar_one())


async def test_the_records_go_with_their_reply_and_with_their_conversation(env: _Env) -> None:
    conv = (await env.chat.create_conversation(agent_key="builtin")).id
    first = await env.chat.append_message(conv, role=Role.ASSISTANT, content=[])
    second = await env.chat.append_message(conv, role=Role.ASSISTANT, content=[])
    await env.chat.record_reply_files(first.id, [_EDITED, _NEW])
    await env.chat.record_reply_files(second.id, [_NEW])
    assert await _rows(env) == 3

    await env.chat.delete_message(first.id)
    assert await _rows(env) == 1

    await env.chat.delete_conversation(conv)
    assert await _rows(env) == 0


async def test_recording_a_reply_again_replaces_its_records(env: _Env) -> None:
    conv = (await env.chat.create_conversation(agent_key="builtin")).id
    reply = await env.chat.append_message(conv, role=Role.ASSISTANT, content=[])

    await env.chat.record_reply_files(reply.id, [_EDITED, _NEW])
    await env.chat.record_reply_files(reply.id, [_NEW, _NEW])

    assert [f.path for f in await env.chat.reply_files(conv, reply.id)] == [_NEW.path]


# --- the Claude adapter's hook ------------------------------------------------


class _EditingSession:
    """An SDK session that, like the CLI, runs the registered ``PreToolUse`` hook
    before each write, then ends the reply."""

    def __init__(self, options: ClaudeAgentOptions, work: Path) -> None:
        self.options = options
        self.work = work

    async def connect(self, prompt: Any) -> None:
        return None

    async def receive_messages(self) -> AsyncIterator[Any]:
        (matcher,) = self.options.hooks["PreToolUse"]  # type: ignore[index]
        assert matcher.matcher == "Edit|MultiEdit|Write|NotebookEdit"
        hook = matcher.hooks[0]
        target = self.work / "ws_client.py"
        for step, content in enumerate(("a\nB\nc\n", "a\nB\nC\n")):
            await hook(
                {"tool_name": "Edit", "tool_input": {"file_path": str(target)}}, f"t{step}", None
            )  # type: ignore[arg-type]
            target.write_text(content)
        new = self.work / "test_ws.py"
        await hook({"tool_name": "Write", "tool_input": {"file_path": str(new)}}, "t9", None)  # type: ignore[arg-type]
        new.write_text("x\n")
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            usage={"input_tokens": 1, "output_tokens": 1},
            total_cost_usd=0.0,
        )

    async def interrupt(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None


@pytest.mark.acceptance(spec="chat", scenario="a reply's edits to one file become one diff")
async def test_the_claude_adapter_records_the_files_its_writes_changed(tmp_path: Path) -> None:
    (tmp_path / "ws_client.py").write_text("a\nb\nc\n")

    async def sink(_: str) -> None:
        return None

    adapter = ClaudeSdkAgentAdapter(
        cwd=str(tmp_path),
        resume_session=None,
        extra={},
        session_factory=lambda options: _EditingSession(options, tmp_path),
        on_session=sink,
    )
    history = [
        Message(
            id="u",
            conversation_id="c",
            seq=0,
            role=Role.USER,
            content=[TextBlock(text="edit")],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )
    ]
    events: list[AgentEvent] = [ev async for ev in await adapter.run_turn(history=history)]

    assert isinstance(events[-1], TurnDone)
    edited, created = adapter.reply_files
    assert (edited.path, edited.added, edited.removed) == (str(tmp_path / "ws_client.py"), 2, 2)
    assert edited.diff is not None and "-b\n-c\n+B\n+C\n" in edited.diff
    assert (created.path, created.added, created.removed) == (str(tmp_path / "test_ws.py"), 1, 0)
