"""App-server-backed Codex adapter tests (spec 008 — per-tool approval relay).

Drives ``CodexAppServerAdapter`` through a ``FakeCodexAppServer`` — a fake
JSON-RPC peer implementing the same reader/writer seam ``CodexRpcClient``
consumes, with NO real ``codex`` subprocess. The fake answers the
``initialize`` / ``thread/start`` / ``thread/resume`` / ``turn/start`` requests
and emits scripted notifications, and (for the approval cases) sends an
unsolicited ``item/commandExecution/requestApproval`` / ``item/fileChange/...``
server→client REQUEST mid-turn that the adapter must answer.

Mirrors ``FakeSdkSession`` / ``_ApprovalScript`` in ``test_claude_sdk_agent.py``.
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

from coffer.application.chat.approvals import ApprovalChannel
from coffer.application.chat.ports import ApprovalDecision
from coffer.domain.chat.events import (
    ApprovalRequest,
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
    """A scripted notification or server→client request the fake emits.

    ``after_request`` names the client request method after whose result the
    frame is emitted (e.g. emit ``turn/started`` after ``turn/start``). A
    ``request_method`` makes the frame an unsolicited server→client REQUEST
    (carries an id, expects a reply); otherwise it is a notification.
    """

    after_request: str
    method: str
    params: dict[str, Any]
    request_method: bool = False


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
        # Approval reply decisions captured by approvalId -> decision dict.
        self.approval_replies: dict[Any, dict[str, Any]] = {}
        self._next_req_id = 1000
        self._task: asyncio.Task[None] | None = None
        self._emit_tasks: set[asyncio.Task[None]] = set()
        # Map of server-request id -> (approval key, reply-arrived event).
        self._pending_approvals: dict[int, tuple[str, asyncio.Event]] = {}

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
            if frame.request_method:
                req_id = self._next_req_id
                self._next_req_id += 1
                # Track this id so we can capture the adapter's reply by key —
                # match the request_id the adapter derives (approvalId / itemId
                # for v2, callId for the legacy methods).
                key = (
                    frame.params.get("approvalId")
                    or frame.params.get("itemId")
                    or frame.params.get("callId")
                    or frame.method
                )
                replied = asyncio.Event()
                self._pending_approvals[req_id] = (key, replied)
                await self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "method": frame.method,
                        "params": frame.params,
                    }
                )
                # Mirror real codex: it sends ``turn/completed`` only AFTER the
                # approval is answered, so block the rest of this batch until the
                # adapter's reply round-trips.
                await replied.wait()
            else:
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
            elif req_id is not None and "result" in frame:
                # A reply to one of our server→client approval requests.
                pending = self._pending_approvals.pop(req_id, None)
                if pending is not None:
                    key, replied = pending
                    self.approval_replies[key] = frame.get("result") or {}
                    replied.set()
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


class _NoApprovals:
    async def wait(self, request_id: str) -> ApprovalDecision:  # pragma: no cover
        raise AssertionError("this turn requests no approval")


async def _collect(
    adapter: CodexAppServerAdapter, history: list[Message], approvals: Any
) -> list[Any]:
    stream = await adapter.run_turn(history=history, approvals=approvals)
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
    events = await asyncio.wait_for(_collect(adapter, _user_turn("hi"), _NoApprovals()), timeout=5)

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
    # thread/start used on-request + workspace-write so approvals surface.
    start_params = next(p for m, p in server.requests if m == "thread/start")
    assert start_params["approvalPolicy"] == "on-request"
    assert start_params["sandbox"] == "workspace-write"
    assert factory.session is not None
    assert factory.session.closed is True


@pytest.mark.asyncio
async def test_adapter_empty_prompt_is_rejected():
    server = FakeCodexAppServer(frames=[])
    factory = _Factory(server)
    adapter = _adapter(factory)
    events = await _collect(adapter, [], _NoApprovals())
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
    await asyncio.wait_for(_collect(adapter, _user_turn("hi"), _NoApprovals()), timeout=5)

    methods = [m for m, _ in server.requests]
    assert "thread/resume" in methods
    assert "thread/start" not in methods
    resume_params = next(p for m, p in server.requests if m == "thread/resume")
    assert resume_params["threadId"] == "thread-existing"


# ---------------------------------------------------------------------------
# T5 — approval relay (command)
# ---------------------------------------------------------------------------


def _command_approval_frames(*, approval_id: str | None = None) -> list[_Frame]:
    params: dict[str, Any] = {
        "threadId": "thread-1",
        "turnId": "turn-1",
        "itemId": "cmd-item-1",
        "command": "rm -rf build",
        "cwd": "/tmp/proj",
    }
    if approval_id is not None:
        params["approvalId"] = approval_id
    return [
        _Frame(
            "turn/start",
            "item/commandExecution/requestApproval",
            params,
            request_method=True,
        ),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-1", "turn": {"id": "turn-1"}},
        ),
    ]


async def _drive_with_decision(
    adapter: CodexAppServerAdapter,
    channel: ApprovalChannel,
    decision: ApprovalDecision,
) -> list[Any]:
    stream = await adapter.run_turn(history=_user_turn("go"), approvals=channel)
    out: list[Any] = []
    async for ev in stream:
        out.append(ev)
        if isinstance(ev, ApprovalRequest):
            channel.resolve(ev.request_id, decision)
    return out


@pytest.mark.asyncio
async def test_command_approval_allow_writes_accept():
    server = FakeCodexAppServer(frames=_command_approval_frames())
    factory = _Factory(server)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    events = await asyncio.wait_for(
        _drive_with_decision(adapter, channel, ApprovalDecision(behavior="allow")),
        timeout=5,
    )

    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert reqs[0].tool_name == "shell"
    assert reqs[0].tool_input == {"command": "rm -rf build", "cwd": "/tmp/proj"}
    assert reqs[0].request_id == "cmd-item-1"
    assert reqs[0].tool_use_id == "cmd-item-1"
    assert server.approval_replies["cmd-item-1"] == {"decision": "accept"}
    assert isinstance(events[-1], TurnDone)


@pytest.mark.asyncio
async def test_command_approval_deny_writes_decline():
    server = FakeCodexAppServer(frames=_command_approval_frames())
    factory = _Factory(server)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    events = await asyncio.wait_for(
        _drive_with_decision(adapter, channel, ApprovalDecision(behavior="deny", message="no")),
        timeout=5,
    )

    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert server.approval_replies["cmd-item-1"] == {"decision": "decline"}


@pytest.mark.asyncio
async def test_command_approval_prefers_approval_id_as_request_id():
    server = FakeCodexAppServer(frames=_command_approval_frames(approval_id="appr-99"))
    factory = _Factory(server)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    events = await asyncio.wait_for(
        _drive_with_decision(adapter, channel, ApprovalDecision(behavior="allow")),
        timeout=5,
    )
    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert reqs[0].request_id == "appr-99"
    assert server.approval_replies["appr-99"] == {"decision": "accept"}


# ---------------------------------------------------------------------------
# T5 — approval relay (fileChange — join by itemId)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_change_approval_joins_changes_by_item_id():
    changes = [{"path": "a.py", "kind": "modify"}]
    frames = [
        # The fileChange item starts first, carrying the changes payload.
        _Frame(
            "turn/start",
            "item/started",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "item": {"id": "fc-1", "type": "fileChange", "changes": changes},
            },
        ),
        # Then the approval request arrives, carrying ONLY the itemId.
        _Frame(
            "turn/start",
            "item/fileChange/requestApproval",
            {"threadId": "thread-1", "turnId": "turn-1", "itemId": "fc-1"},
            request_method=True,
        ),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-1", "turn": {"id": "turn-1"}},
        ),
    ]
    server = FakeCodexAppServer(frames=frames)
    factory = _Factory(server)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    events = await asyncio.wait_for(
        _drive_with_decision(adapter, channel, ApprovalDecision(behavior="allow")),
        timeout=5,
    )
    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert reqs[0].tool_name == "file_change"
    assert reqs[0].request_id == "fc-1"
    assert reqs[0].tool_input == {"changes": changes}
    assert server.approval_replies["fc-1"] == {"decision": "accept"}


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
    channel = ApprovalChannel()

    stream = await adapter.run_turn(history=_user_turn("go"), approvals=channel)

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

    stream = await adapter.run_turn(history=_user_turn("hi"), approvals=_NoApprovals())
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


# ---------------------------------------------------------------------------
# T9 — legacy protocol-version guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_exec_command_approval_returns_review_decision():
    # An older/future codex sends the legacy ``execCommandApproval`` request
    # shape; the adapter must answer with the ``ReviewDecision`` shape.
    frames = [
        _Frame(
            "turn/start",
            "execCommandApproval",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "callId": "legacy-1",
                "command": ["rm", "x"],
                "cwd": "/tmp",
            },
            request_method=True,
        ),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-1", "turn": {"id": "turn-1"}},
        ),
    ]
    server = FakeCodexAppServer(frames=frames)
    factory = _Factory(server)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    events = await asyncio.wait_for(
        _drive_with_decision(adapter, channel, ApprovalDecision(behavior="allow")),
        timeout=5,
    )
    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert server.approval_replies["legacy-1"] == {"decision": "approved"}


@pytest.mark.asyncio
async def test_legacy_apply_patch_approval_denied_returns_review_decision():
    frames = [
        _Frame(
            "turn/start",
            "applyPatchApproval",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "callId": "legacy-patch",
                "changes": {"a.py": {}},
            },
            request_method=True,
        ),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-1", "turn": {"id": "turn-1"}},
        ),
    ]
    server = FakeCodexAppServer(frames=frames)
    factory = _Factory(server)
    adapter = _adapter(factory)
    channel = ApprovalChannel()

    events = await asyncio.wait_for(
        _drive_with_decision(adapter, channel, ApprovalDecision(behavior="deny")),
        timeout=5,
    )
    reqs = [e for e in events if isinstance(e, ApprovalRequest)]
    assert len(reqs) == 1
    assert server.approval_replies["legacy-patch"] == {"decision": "denied"}
