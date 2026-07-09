"""HermesProvider integration tests (ACP-backed hermes provider).

Mirrors ``test_codex_provider.py`` / ``test_opencode_provider.py`` but drives the
adapter over a **fake ACP peer** — a scripted JSON-RPC 2.0 server implementing the
same reader/writer seam ``CodexRpcClient`` consumes, with NO real ``hermes``
binary or model call. The fake answers ``initialize`` / ``session/new`` /
``session/load`` / ``session/prompt``, emits scripted ``session/update``
notifications during a prompt, and can raise a ``session/request_permission``
server→client request (whose auto-allow reply the fake captures).

Because hermes' model calls hang in the build sandbox, this substitutes for a
live end-to-end run: the ACP wire shapes are grounded in the Agent Client
Protocol schema, not a captured live session.

Asserts:
- ``init_conversation`` defaults/validates the cwd and stores the model.
- a turn yields ``TurnStarted`` → ``TextDelta`` → ``TurnDone`` and persists the
  session id; the next turn resumes via ``session/load``.
- ``COFFER_PROVIDER_KEY`` is injected (merged) when a connection is active, and
  left off otherwise.
- ``session/request_permission`` is auto-allowed.
- ``availability()`` reflects the injected ``which``; ``on_conversation_deleted``
  is a no-op.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.chat.conversation import Conversation
from coffer.domain.chat.events import TextDelta, ToolCall, ToolResult, TurnDone, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient
from coffer.infrastructure.chat.hermes_acp import HermesAcpSession
from coffer.infrastructure.chat.hermes_agent import HermesAcpAdapter
from coffer.infrastructure.chat.hermes_provider import HermesProvider
from coffer.infrastructure.chat.persistence import ConversationRepo
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# ---------------------------------------------------------------------------
# Fake ACP peer — a scripted JSON-RPC 2.0 server over the CodexRpcClient seam
# ---------------------------------------------------------------------------


class _FakePipe:
    """An in-memory NDJSON pipe: one side writes, the other reads."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False

    def write(self, data: bytes) -> None:
        self._queue.put_nowait(data)

    async def drain(self) -> None:
        return None

    async def readline(self) -> bytes:
        if self._closed and self._queue.empty():
            return b""
        return await self._queue.get()

    def close(self) -> None:
        self._closed = True
        self._queue.put_nowait(b"")


class FakeHermesAcp:
    """A scripted ``hermes acp`` peer over the ``CodexRpcClient`` seam.

    Reads client request/notification lines from ``client_to_server`` and writes
    scripted responses + ``session/update`` notifications (+ an optional
    ``session/request_permission`` request) to ``server_to_client``.
    """

    def __init__(
        self,
        *,
        session_id: str = "ses-1",
        updates: list[dict[str, Any]] | None = None,
        stop_reason: str = "end_turn",
        request_permission: bool = False,
    ) -> None:
        self.client_to_server = _FakePipe()  # adapter -> peer
        self.server_to_client = _FakePipe()  # peer -> adapter
        self._session_id = session_id
        self._updates = updates or []
        self._stop = stop_reason
        self._request_permission = request_permission
        # Observed client requests + notifications, for assertions.
        self.requests: list[tuple[str, dict[str, Any]]] = []
        #: The adapter's reply frame to our session/request_permission request.
        self.permission_reply: dict[str, Any] | None = None
        self._perm_replied = asyncio.Event()
        self._next_server_id = 9000
        self._task: asyncio.Task[None] | None = None
        self._prompt_tasks: set[asyncio.Task[None]] = set()

    def make_rpc(self) -> CodexRpcClient:
        return CodexRpcClient(self.server_to_client, self.client_to_server)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        for task in list(self._prompt_tasks):
            task.cancel()
        self._prompt_tasks.clear()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _send(self, obj: dict[str, Any]) -> None:
        self.server_to_client.write((json.dumps(obj) + "\n").encode("utf-8"))

    async def _run(self) -> None:
        while True:
            raw = await self.client_to_server.readline()
            if not raw:
                return
            try:
                frame = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if not isinstance(frame, dict):
                continue
            method = frame.get("method")
            req_id = frame.get("id")
            if method is not None and req_id is not None:
                await self._handle_request(method, req_id, frame.get("params") or {})
            elif method is not None:
                # client notification (e.g. session/cancel) — record, no reply.
                self.requests.append((method, frame.get("params") or {}))
            elif req_id is not None:
                # a RESPONSE from the adapter to our server→client request.
                self.permission_reply = frame
                self._perm_replied.set()

    async def _handle_request(self, method: str, req_id: int, params: dict[str, Any]) -> None:
        self.requests.append((method, params))
        if method == "initialize":
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"protocolVersion": 1, "agentCapabilities": {}, "authMethods": []},
                }
            )
        elif method == "session/new":
            await self._send(
                {"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": self._session_id}}
            )
        elif method == "session/load":
            # ACP session/load replays history then responds with null.
            await self._send({"jsonrpc": "2.0", "id": req_id, "result": None})
        elif method == "session/prompt":
            # Run the prompt sequence off the read loop so this loop can capture
            # the adapter's permission reply concurrently.
            task = asyncio.create_task(self._run_prompt(req_id, params))
            self._prompt_tasks.add(task)
            task.add_done_callback(self._prompt_tasks.discard)
        else:
            await self._send({"jsonrpc": "2.0", "id": req_id, "result": {}})

    async def _run_prompt(self, req_id: int, params: dict[str, Any]) -> None:
        sid = params.get("sessionId")
        if self._request_permission:
            rid = self._next_server_id
            self._next_server_id += 1
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": rid,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": sid,
                        "toolCall": {"toolCallId": "t1", "title": "Run"},
                        "options": [
                            {"optionId": "deny", "name": "Deny", "kind": "reject_once"},
                            {"optionId": "allow", "name": "Allow", "kind": "allow_once"},
                        ],
                    },
                }
            )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._perm_replied.wait(), timeout=2)
        for update in self._updates:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {"sessionId": sid, "update": update},
                }
            )
        await self._send({"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": self._stop}})


# ---------------------------------------------------------------------------
# Session + factory fakes wrapping the peer
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    """A ``HermesAcpSession`` backed by a ``FakeHermesAcp``."""

    server: FakeHermesAcp
    _rpc: CodexRpcClient | None = field(default=None, init=False)
    started: bool = field(default=False, init=False)
    closed: bool = field(default=False, init=False)

    @property
    def rpc(self) -> CodexRpcClient:
        if self._rpc is None:
            raise RuntimeError("session not started")
        return self._rpc

    async def start(self) -> None:
        self._rpc = self.server.make_rpc()
        self._rpc.start()
        self.server.start()
        self.started = True

    async def close(self) -> None:
        self.closed = True
        if self._rpc is not None:
            await self._rpc.close()
        await self.server.stop()


@dataclass
class _Factory:
    """A scripted ``AcpSessionFactory`` capturing the spawn config."""

    server: FakeHermesAcp
    last_cwd: str | None = field(default=None, init=False)
    last_env: dict[str, str] | None = field(default=None, init=False)
    session: _FakeSession | None = field(default=None, init=False)

    def __call__(self, cwd: str, env: dict[str, str] | None) -> HermesAcpSession:
        self.last_cwd = cwd
        self.last_env = env
        self.session = _FakeSession(self.server)
        return self.session


def _text_update(text: str) -> dict[str, Any]:
    return {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}


def _make_factory(**kwargs: Any) -> tuple[_Factory, FakeHermesAcp]:
    server = FakeHermesAcp(updates=kwargs.pop("updates", [_text_update("hi")]), **kwargs)
    return _Factory(server), server


# ---------------------------------------------------------------------------
# Helpers (mirror the codex/opencode provider tests)
# ---------------------------------------------------------------------------


async def _repo(tmp_path: Any) -> tuple[ConversationRepo, Any]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return ConversationRepo(session_maker(engine)), engine


def _conv(agent_key: str = "hermes") -> Conversation:
    now = datetime.now(tz=UTC)
    return Conversation(
        id=uuid.uuid4().hex,
        agent_key=agent_key,
        title="t",
        model_id=None,
        created_at=now,
        updated_at=now,
    )


def _user_turn(text: str, conv_id: str = "c1") -> list[Message]:
    return [
        Message(
            id=uuid.uuid4().hex,
            conversation_id=conv_id,
            seq=0,
            role=Role.USER,
            content=[TextBlock(text=text)],
            status="complete",
            model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            created_at=datetime.now(tz=UTC),
        )
    ]


async def _collect(adapter: HermesAcpAdapter, history: list[Message]) -> list[Any]:
    stream = await adapter.run_turn(history=history)
    return [ev async for ev in stream]


# ---------------------------------------------------------------------------
# init_conversation — cwd validation (parity with the other providers)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_conversation_defaults_missing_cwd_to_workspace(
    tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = HermesProvider(conversations=repo)

    await provider.init_conversation(conv.id, {})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path / ".coffer" / "workspace")
    assert (tmp_path / ".coffer" / "workspace").is_dir()

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_rejects_non_directory_cwd(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = HermesProvider(conversations=repo)

    with pytest.raises(AgentConfigRejected) as exc:
        await provider.init_conversation(conv.id, {"cwd": "/no/such/dir/xyz"})
    assert exc.value.reason == "cwd_not_a_directory"

    await engine.dispose()


@pytest.mark.asyncio
async def test_init_conversation_stores_cwd_and_model(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    provider = HermesProvider(conversations=repo)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path), "model": "hermes-4"})
    stored = await repo.get_agent_config(conv.id)
    assert stored.cwd == str(tmp_path)
    assert stored.model == "hermes-4"

    await engine.dispose()


# ---------------------------------------------------------------------------
# build_adapter — drives a turn over the fake ACP peer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_adapter_refreshes_context_block_first(tmp_path: Any) -> None:
    # hermes has no working hook (ADR-042 INSTRUCTIONS_BLOCK): the session-
    # context block in AGENTS.md is refreshed at the one moment Coffer controls —
    # adapter construction, i.e. once per turn.
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _server = _make_factory(session_id="ses-r", updates=[_text_update("hi")])
    calls: list[int] = []

    async def _refresh() -> int:
        calls.append(1)
        return 1

    provider = HermesProvider(conversations=repo, session_factory=factory, refresh_context=_refresh)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    await provider.build_adapter(conv.id)
    assert calls == [1]
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_survives_refresh_failure(tmp_path: Any) -> None:
    # A refresh failure must never block the turn (failure-is-silent contract).
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _server = _make_factory(session_id="ses-f", updates=[_text_update("hi")])

    async def _boom() -> int:
        raise RuntimeError("daemon hiccup")

    provider = HermesProvider(conversations=repo, session_factory=factory, refresh_context=_boom)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    assert isinstance(adapter, HermesAcpAdapter)
    await engine.dispose()


@pytest.mark.asyncio
async def test_turn_yields_text_and_terminal_from_prompt_response(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, server = _make_factory(session_id="ses-abc", updates=[_text_update("hi")])
    provider = HermesProvider(conversations=repo, session_factory=factory)

    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    assert isinstance(adapter, HermesAcpAdapter)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("hey", conv.id)), timeout=5)

    assert isinstance(events[0], TurnStarted)
    assert TextDelta(text="hi") in events
    done = events[-1]
    assert isinstance(done, TurnDone)
    assert done.stop_reason == "end_turn"

    # Handshake was driven: initialize → session/new → session/prompt.
    methods = [m for m, _ in server.requests]
    assert methods[:3] == ["initialize", "session/new", "session/prompt"]
    # session/new declined proxied fs capabilities; prompt carried the text.
    init_params = next(p for m, p in server.requests if m == "initialize")
    assert init_params["protocolVersion"] == 1
    prompt_params = next(p for m, p in server.requests if m == "session/prompt")
    assert prompt_params["prompt"][0]["text"] == "hey"
    assert prompt_params["sessionId"] == "ses-abc"
    assert factory.last_cwd == str(tmp_path)
    assert factory.session is not None
    assert factory.session.closed is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_turn_streams_tool_call_and_result(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    updates = [
        {
            "sessionUpdate": "tool_call",
            "toolCallId": "t1",
            "title": "Read",
            "rawInput": {"path": "/x"},
        },
        {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "t1",
            "status": "completed",
            "rawOutput": {"content": "data"},
        },
        _text_update("done"),
    ]
    factory, _server = _make_factory(updates=updates)
    provider = HermesProvider(conversations=repo, session_factory=factory)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("go", conv.id)), timeout=5)

    calls = [e for e in events if isinstance(e, ToolCall)]
    results = [e for e in events if isinstance(e, ToolResult)]
    assert calls == [ToolCall(tool_use_id="t1", tool_name="Read", tool_input={"path": "/x"})]
    assert results == [
        ToolResult(tool_use_id="t1", tool_name="Read", output={"content": "data"}, error=None)
    ]
    assert isinstance(events[-1], TurnDone)

    await engine.dispose()


@pytest.mark.asyncio
async def test_turn_persists_session_and_resumes_via_session_load(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())

    factory1, _ = _make_factory(session_id="ses-xyz")
    provider1 = HermesProvider(conversations=repo, session_factory=factory1)
    await provider1.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter1 = await provider1.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter1, _user_turn("hi", conv.id)), timeout=5)

    cfg = await repo.get_agent_config(conv.id)
    assert cfg.session_id == "ses-xyz"

    # Next turn resumes via session/load with the persisted id.
    factory2, server2 = _make_factory(session_id="ses-xyz")
    provider2 = HermesProvider(conversations=repo, session_factory=factory2)
    adapter2 = await provider2.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter2, _user_turn("again", conv.id)), timeout=5)

    methods = [m for m, _ in server2.requests]
    assert "session/load" in methods
    assert "session/new" not in methods
    load_params = next(p for m, p in server2.requests if m == "session/load")
    assert load_params["sessionId"] == "ses-xyz"

    await engine.dispose()


@pytest.mark.asyncio
async def test_request_permission_is_auto_allowed(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, server = _make_factory(request_permission=True, updates=[_text_update("ok")])
    provider = HermesProvider(conversations=repo, session_factory=factory)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)

    events = await asyncio.wait_for(_collect(adapter, _user_turn("go", conv.id)), timeout=5)
    assert isinstance(events[-1], TurnDone)

    # The adapter replied to session/request_permission by selecting the allow option.
    assert server.permission_reply is not None
    outcome = server.permission_reply["result"]["outcome"]
    assert outcome == {"outcome": "selected", "optionId": "allow"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_build_adapter_raises_conversation_not_found(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    factory, _ = _make_factory()
    provider = HermesProvider(conversations=repo, session_factory=factory)
    with pytest.raises(ConversationNotFound):
        await provider.build_adapter("nonexistent-conv-id")
    await engine.dispose()


# ---------------------------------------------------------------------------
# COFFER_PROVIDER_KEY injection (ADR-032 env_key seam, shared with Codex)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_key_injected_and_merged(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _ = _make_factory()

    async def resolve_key() -> str | None:
        return "sk-hermes-abc"

    provider = HermesProvider(conversations=repo, session_factory=factory, resolve_key=resolve_key)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)

    assert factory.last_env is not None
    assert factory.last_env["COFFER_PROVIDER_KEY"] == "sk-hermes-abc"
    assert "PATH" in factory.last_env  # merged with the daemon env, not replaced

    await engine.dispose()


@pytest.mark.asyncio
async def test_no_active_key_inherits_daemon_env(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    conv = await repo.create(_conv())
    factory, _ = _make_factory()

    async def resolve_key() -> str | None:
        return None

    provider = HermesProvider(conversations=repo, session_factory=factory, resolve_key=resolve_key)
    await provider.init_conversation(conv.id, {"cwd": str(tmp_path)})
    adapter = await provider.build_adapter(conv.id)
    await asyncio.wait_for(_collect(adapter, _user_turn("hi", conv.id)), timeout=5)
    assert factory.last_env is None

    await engine.dispose()


# ---------------------------------------------------------------------------
# availability + on_conversation_deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_availability_reflects_injected_which(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    present = HermesProvider(conversations=repo, which=lambda _b: "/opt/homebrew/bin/hermes")
    absent = HermesProvider(conversations=repo, which=lambda _b: None)
    assert await present.availability() is True
    assert await absent.availability() is False
    assert present.agent_key == "hermes"
    await engine.dispose()


@pytest.mark.asyncio
async def test_on_conversation_deleted_is_noop(tmp_path: Any) -> None:
    repo, engine = await _repo(tmp_path)
    provider = HermesProvider(conversations=repo)
    await provider.on_conversation_deleted("any-id")
    await engine.dispose()
