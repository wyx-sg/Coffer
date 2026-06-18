"""App-server-backed Codex adapter tests (spec 008).

Drives ``CodexAppServerAdapter`` through a ``FakeCodexAppServer`` — a fake
JSON-RPC peer implementing the same reader/writer seam ``CodexRpcClient``
consumes, with NO real ``codex`` subprocess. The fake answers the
``initialize`` / ``thread/start`` / ``thread/resume`` / ``turn/start`` requests
and emits scripted notifications.
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

from coffer.domain.chat.events import (
    TextDelta,
    TurnDone,
    TurnStarted,
)
from coffer.domain.chat.message import Message, Role, TextBlock
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient

# ---------------------------------------------------------------------------
# Fake JSON-RPC peer (the "server" side of codex app-server)
# ---------------------------------------------------------------------------


@dataclass
class _Frame:
    """A scripted notification the fake emits.

    ``after_request`` names the client request method after whose result the
    frame is emitted (e.g. emit ``turn/started`` after ``turn/start``).
    """

    after_request: str
    method: str
    params: dict[str, Any]


class _FakePipe:
    """An in-memory NDJSON pipe: the adapter writes here; the peer reads here."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False

    # writer side (sync write + async drain), matching ``_Writer``.
    def write(self, data: bytes) -> None:
        self._queue.put_nowait(data)

    async def drain(self) -> None:
        return None

    # reader side, matching ``_Reader``.
    async def readline(self) -> bytes:
        if self._closed and self._queue.empty():
            return b""
        return await self._queue.get()

    def close(self) -> None:
        self._closed = True
        self._queue.put_nowait(b"")


class FakeCodexAppServer:
    """A scripted ``codex app-server`` peer over the ``CodexRpcClient`` seam.

    Reads client request lines from ``client_to_server`` and writes scripted
    JSON-RPC responses + notifications (+ optional approval requests) to
    ``server_to_client``. The adapter's RPC client reads ``server_to_client``
    and writes ``client_to_server``.
    """

    def __init__(
        self,
        *,
        thread_id: str = "thread-1",
        turn_id: str = "turn-1",
        frames: list[_Frame] | None = None,
    ) -> None:
        self.client_to_server = _FakePipe()  # adapter -> peer
        self.server_to_client = _FakePipe()  # peer -> adapter
        self._thread_id = thread_id
        self._turn_id = turn_id
        self._frames = frames or []
        # Observed client requests, for assertions.
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._task: asyncio.Task[None] | None = None
        self._emit_tasks: set[asyncio.Task[None]] = set()

    # The adapter builds its RPC client over (reader=server_to_client,
    # writer=client_to_server).
    def make_rpc(self) -> CodexRpcClient:
        return CodexRpcClient(self.server_to_client, self.client_to_server)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        for emit in list(self._emit_tasks):
            emit.cancel()
        self._emit_tasks.clear()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _send(self, obj: dict[str, Any]) -> None:
        self.server_to_client.write((json.dumps(obj) + "\n").encode("utf-8"))

    async def _emit_frames(self, after_request: str) -> None:
        for frame in self._frames:
            if frame.after_request != after_request:
                continue
            await self._send({"jsonrpc": "2.0", "method": frame.method, "params": frame.params})

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
                await self._handle_client_request(method, req_id, frame.get("params") or {})
            # client notifications (e.g. ``initialized``) need no reply.

    async def _handle_client_request(
        self, method: str, req_id: int, params: dict[str, Any]
    ) -> None:
        self.requests.append((method, params))
        if method == "initialize":
            result: dict[str, Any] = {
                "userAgent": "codex/0.125.0 fake",
                "codexHome": "/home/.codex",
                "platformFamily": "unix",
                "platformOs": "macos",
            }
        elif method in ("thread/start", "thread/resume"):
            result = {"thread": {"id": self._thread_id, "path": "/tmp/x.jsonl"}}
        elif method == "turn/start":
            result = {"turn": {"id": self._turn_id, "status": "running"}}
        elif method == "turn/interrupt":
            result = {}
        else:
            result = {}
        await self._send({"jsonrpc": "2.0", "id": req_id, "result": result})
        # Emit scripted frames in a separate task: a request frame blocks the
        # batch on the adapter's reply, and that reply is read by ``_run`` — so
        # emission must not block the read loop itself.
        emit = asyncio.create_task(self._emit_frames(method))
        self._emit_tasks.add(emit)
        emit.add_done_callback(self._emit_tasks.discard)


# ---------------------------------------------------------------------------
# Session adapter wrapping the fake peer
# ---------------------------------------------------------------------------


@dataclass
class _FakeSession:
    """A ``CodexAppServerSession`` backed by a ``FakeCodexAppServer``."""

    server: FakeCodexAppServer
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
    """A scripted ``AppServerSessionFactory`` capturing the spawn config."""

    server: FakeCodexAppServer
    last_cwd: str | None = field(default=None, init=False)
    last_env: dict[str, str] | None = field(default=None, init=False)
    session: _FakeSession | None = field(default=None, init=False)

    def __call__(self, cwd: str, env: dict[str, str] | None) -> _FakeSession:
        self.last_cwd = cwd
        self.last_env = env
        self.session = _FakeSession(self.server)
        return self.session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_turn(text: str) -> list[Message]:
    return [
        Message(
            id=uuid.uuid4().hex,
            conversation_id="c1",
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


async def _dummy_sink(sid: str) -> None:
    return None


def _adapter(
    factory: _Factory,
    *,
    on_session: Any = _dummy_sink,
    resume: str | None = None,
    extra: dict[str, Any] | None = None,
) -> CodexAppServerAdapter:
    return CodexAppServerAdapter(
        cwd="/tmp",
        resume_session=resume,
        extra=extra or {},
        session_factory=factory,
        on_session=on_session,
    )


async def _collect(adapter: CodexAppServerAdapter, history: list[Message]) -> list[Any]:
    stream = await adapter.run_turn(history=history)
    return [ev async for ev in stream]


def _basic_frames() -> list[_Frame]:
    """thread/started + turn/started, agent text delta, turn/completed."""
    return [
        _Frame("thread/start", "thread/started", {"thread": {"id": "thread-1"}}),
        _Frame(
            "turn/start",
            "turn/started",
            {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "running"}},
        ),
        _Frame(
            "turn/start",
            "item/agentMessage/delta",
            {"threadId": "thread-1", "turnId": "turn-1", "itemId": "i1", "delta": "Hello"},
        ),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-1", "turn": {"id": "turn-1", "status": "completed"}},
        ),
    ]


# ---------------------------------------------------------------------------
# T4 — lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_streams_events_and_persists_thread_id():
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    server = FakeCodexAppServer(frames=_basic_frames())
    factory = _Factory(server)
    adapter = _adapter(factory, on_session=on_session)
    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi")), timeout=5)

    assert isinstance(events[0], TurnStarted)
    assert isinstance(events[-1], TurnDone)
    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert deltas == ["Hello"]
    assert [type(e) for e in events].count(TurnDone) == 1
    assert saved == ["thread-1"]
    # The handshake sequence was driven correctly.
    methods = [m for m, _ in server.requests]
    assert methods[:3] == ["initialize", "thread/start", "turn/start"]
    # turn/start carried the prompt text.
    turn_params = next(p for m, p in server.requests if m == "turn/start")
    assert turn_params["input"][0]["text"] == "hi"
    # Agents always run unattended: never ask for approval, full access.
    start_params = next(p for m, p in server.requests if m == "thread/start")
    assert start_params["approvalPolicy"] == "never"
    assert start_params["sandbox"] == "danger-full-access"
    assert factory.session is not None
    assert factory.session.closed is True


@pytest.mark.asyncio
async def test_adapter_empty_prompt_is_rejected():
    server = FakeCodexAppServer(frames=[])
    factory = _Factory(server)
    adapter = _adapter(factory)
    events = await _collect(adapter, [])
    assert len(events) == 1
    from coffer.domain.chat.events import TurnError

    assert isinstance(events[0], TurnError)
    assert events[0].code == "empty_prompt"


@pytest.mark.asyncio
async def test_resume_uses_thread_resume_with_thread_id():
    server = FakeCodexAppServer(
        frames=[
            _Frame(
                "turn/start",
                "turn/completed",
                {"threadId": "thread-1", "turn": {"id": "turn-1"}},
            ),
        ]
    )
    factory = _Factory(server)
    adapter = _adapter(factory, resume="thread-existing")
    await asyncio.wait_for(_collect(adapter, _user_turn("hi")), timeout=5)

    methods = [m for m, _ in server.requests]
    assert "thread/resume" in methods
    assert "thread/start" not in methods
    resume_params = next(p for m, p in server.requests if m == "thread/resume")
    assert resume_params["threadId"] == "thread-existing"


# ---------------------------------------------------------------------------
# T4 — cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_interrupts_and_closes_and_persists_thread():
    saved: list[str] = []

    async def on_session(sid: str) -> None:
        saved.append(sid)

    # thread/started arrives (so thread id is captured) but no terminal — the
    # turn hangs waiting, so it can be cancelled at a known point.
    server = FakeCodexAppServer(
        frames=[_Frame("thread/start", "thread/started", {"thread": {"id": "thread-1"}})]
    )
    factory = _Factory(server)
    adapter = _adapter(factory, on_session=on_session)

    stream = await adapter.run_turn(history=_user_turn("go"))

    async def consume() -> None:
        async for _ in stream:
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert factory.session is not None
    assert factory.session.closed is True
    assert saved == ["thread-1"]
    # turn/interrupt was sent on cancel.
    methods = [m for m, _ in server.requests]
    assert "turn/interrupt" in methods


@pytest.mark.asyncio
async def test_stream_end_without_terminal_synthesizes_turn_done():
    # The peer closes its stream without a turn/completed.
    server = FakeCodexAppServer(
        frames=[
            _Frame(
                "turn/start",
                "item/agentMessage/delta",
                {"itemId": "i1", "delta": "hi"},
            )
        ]
    )
    factory = _Factory(server)
    adapter = _adapter(factory)

    stream = await adapter.run_turn(history=_user_turn("hi"))
    out: list[Any] = []

    async def drive() -> None:
        async for ev in stream:
            out.append(ev)
            if isinstance(ev, TextDelta):
                # Once the delta is seen, close the peer's stream to end the turn.
                server.server_to_client.close()

    await asyncio.wait_for(drive(), timeout=5)
    terminals = [e for e in out if isinstance(e, TurnDone)]
    assert len(terminals) == 1


@pytest.mark.asyncio
async def test_stream_end_without_terminal_no_pending_task_warning(recwarn: Any) -> None:
    """EOF-without-terminal path must not leak pending futures.

    The pump is cancelled at session close; the old ``_notifications_until_eof``
    leaked the in-flight ``nxt`` future and asyncio emitted a
    "Task was destroyed but it is pending!" warning.  With the fix the warning
    must not appear.
    """
    import warnings

    server = FakeCodexAppServer(
        frames=[
            _Frame(
                "turn/start",
                "item/agentMessage/delta",
                {"itemId": "i1", "delta": "bye"},
            )
        ]
    )
    factory = _Factory(server)
    adapter = _adapter(factory)

    stream = await adapter.run_turn(history=_user_turn("hi"))
    out: list[Any] = []

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        async def drive() -> None:
            async for ev in stream:
                out.append(ev)
                if isinstance(ev, TextDelta):
                    server.server_to_client.close()

        await asyncio.wait_for(drive(), timeout=5)
        # Allow the event loop to run one more iteration so any GC-triggered
        # "Task destroyed but pending" warnings have a chance to surface.
        await asyncio.sleep(0)

    terminals = [e for e in out if isinstance(e, TurnDone)]
    assert len(terminals) == 1

    pending_warnings = [
        w for w in caught if "Task was destroyed but it is pending" in str(w.message)
    ]
    assert pending_warnings == [], f"Unexpected pending-task warnings: {pending_warnings}"
