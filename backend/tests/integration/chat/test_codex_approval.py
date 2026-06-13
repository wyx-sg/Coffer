"""E2E acceptance test: per-tool approval relay for app-server-backed Codex.

Proves the FULL per-tool approval relay works for Codex through the REAL turn
machinery:

- A turn driven by ``CodexAppServerProvider`` (wired to a ``FakeCodexAppServer``)
  emits assistant text, then sends an unsolicited
  ``item/commandExecution/requestApproval`` server→client REQUEST mid-turn.
- The turn pauses and emits an ``ApprovalRequest`` on the orchestrator's event
  queue.
- The human answers through the real ``orchestrator.submit_approval(...)`` path.
- Allow path: the adapter writes ``{decision: "accept"}`` back to the fake server
  and the turn ends with ``TurnDone``.
- Deny path: the adapter writes ``{decision: "decline"}`` back and the turn also
  ends cleanly with ``TurnDone``.

No real ``codex`` binary or subprocess is touched — everything runs through the
``FakeCodexAppServer`` fake imported from the adapter-level tests.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.application.audit_service import AuditService
from coffer.application.chat.ports import ApprovalDecision
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, clear_active_turns
from coffer.domain.chat.events import ApprovalRequest, TurnDone, TurnError
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.chat.persistence import (
    ConversationRepo,
    MessageRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# Re-use the FakeCodexAppServer + scripting helpers from the adapter-level tests.
from tests.integration.chat.test_codex_app_server_agent import (
    FakeCodexAppServer,
    _Factory,
    _Frame,
)
from tests.unit.chat.conftest import FakeAuditRepo

# ---------------------------------------------------------------------------
# Scripted frame sets
# ---------------------------------------------------------------------------


def _approval_frames() -> list[_Frame]:
    """An ``item/commandExecution/requestApproval`` mid-turn followed by completion."""
    return [
        _Frame("thread/start", "thread/started", {"thread": {"id": "thread-a1"}}),
        _Frame(
            "turn/start",
            "turn/started",
            {"threadId": "thread-a1", "turn": {"id": "turn-a1", "status": "running"}},
        ),
        _Frame(
            "turn/start",
            "item/agentMessage/delta",
            {
                "threadId": "thread-a1",
                "turnId": "turn-a1",
                "itemId": "msg-1",
                "delta": "Running a command for you.",
            },
        ),
        # The approval request — a server→client REQUEST (has an id, expects a
        # reply).  The fake blocks emitting ``turn/completed`` until the adapter's
        # reply round-trips (see ``FakeCodexAppServer._emit_frames``).
        _Frame(
            "turn/start",
            "item/commandExecution/requestApproval",
            {
                "threadId": "thread-a1",
                "turnId": "turn-a1",
                "itemId": "cmd-approval-1",
                "command": "ls /",
                "cwd": "/tmp",
            },
            request_method=True,
        ),
        _Frame(
            "turn/start",
            "turn/completed",
            {"threadId": "thread-a1", "turn": {"id": "turn-a1", "status": "completed"}},
        ),
    ]


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


async def _build_services(
    tmp_path: Any,
    factory: _Factory,
) -> tuple[ChatService, TurnOrchestrator]:
    """Wire a real SQLite repo + CodexAppServerProvider + orchestrator."""
    engine = create_async_engine_with_pragmas(
        f"sqlite+aiosqlite:///{tmp_path / 'codex_approval.db'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = session_maker(engine)
    conv_repo = ConversationRepo(sm)
    msg_repo = MessageRepo(sm)

    audit = AuditService(repo=FakeAuditRepo())  # type: ignore[arg-type]

    codex_provider = CodexAppServerProvider(
        conversations=conv_repo,
        session_factory=factory,
        which=lambda _: "/usr/bin/codex",  # pretend the binary exists
    )

    registry = AgentProviderRegistry()
    registry.register(codex_provider, display_name="Codex")

    chat_svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
        audit=audit,  # type: ignore[arg-type]
    )
    orchestrator = TurnOrchestrator(
        chat_service=chat_svc,
        registry=registry,
        audit=audit,
    )
    return chat_svc, orchestrator


async def _drain(queue: asyncio.Queue[Any]) -> list[Any]:
    """Collect events until the ``None`` sentinel arrives."""
    events: list[Any] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            return events
        events.append(item)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_active_turns() -> Any:
    clear_active_turns()
    yield
    clear_active_turns()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="008-agent-chat",
    scenario="per-tool approval relay works for app-server-backed Codex",
)
async def test_codex_approval_allow_via_orchestrator(tmp_path: Any) -> None:
    """Allow path: the turn proceeds after the human grants permission.

    The ``FakeCodexAppServer`` sends an unsolicited
    ``item/commandExecution/requestApproval`` REQUEST mid-turn.  The
    ``CodexAppServerAdapter`` emits an ``ApprovalRequest`` event and awaits
    the human decision.  The test observes the event on the queue, calls
    ``submit_approval`` with ``behavior="allow"``, and asserts:
    - The adapter wrote ``{decision: "accept"}`` back to the fake server.
    - The turn stream ends with ``TurnDone`` (not ``TurnError``).
    """
    server = FakeCodexAppServer(frames=_approval_frames())
    factory = _Factory(server)

    chat_svc, orchestrator = await _build_services(tmp_path, factory)
    conv = await chat_svc.create_conversation(
        agent_key="codex",
        agent_config={"cwd": str(tmp_path)},
    )

    queue = await orchestrator.start_turn(conv.id, "list root directory")

    # Drain until the ApprovalRequest arrives (the turn is paused at this point).
    collected: list[Any] = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert event is not None, "stream ended before ApprovalRequest arrived"
        collected.append(event)
        if isinstance(event, ApprovalRequest):
            break

    approval_event: ApprovalRequest = event

    # The approval request must describe the shell command.
    assert approval_event.tool_name == "shell"
    assert approval_event.tool_input == {"command": "ls /", "cwd": "/tmp"}

    # Deliver the allow decision through the real orchestrator path.
    orchestrator.submit_approval(
        conv.id,
        approval_event.request_id,
        ApprovalDecision(behavior="allow"),
    )

    # Collect the rest of the stream.
    collected.extend(await _drain(queue))

    # The adapter must have written {decision: "accept"} back to the fake.
    assert server.approval_replies.get(approval_event.request_id) == {"decision": "accept"}, (
        f"expected {{decision: accept}}, got {server.approval_replies!r}"
    )

    # The turn must contain an ApprovalRequest and finish with TurnDone.
    assert any(isinstance(e, ApprovalRequest) for e in collected)
    assert any(isinstance(e, TurnDone) for e in collected), (
        f"no TurnDone in events: {[type(e).__name__ for e in collected]}"
    )
    assert not any(isinstance(e, TurnError) for e in collected)


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="008-agent-chat",
    scenario="per-tool approval relay works for app-server-backed Codex",
)
async def test_codex_approval_deny_via_orchestrator(tmp_path: Any) -> None:
    """Deny path: the denial is delivered to the adapter and the turn completes.

    Same setup as the allow path, but ``submit_approval`` carries
    ``behavior="deny"``.  Asserts:
    - The adapter wrote ``{decision: "decline"}`` back to the fake server.
    - The turn stream ends cleanly (``TurnDone``, no ``TurnError``).
    """
    server = FakeCodexAppServer(frames=_approval_frames())
    factory = _Factory(server)

    chat_svc, orchestrator = await _build_services(tmp_path, factory)
    conv = await chat_svc.create_conversation(
        agent_key="codex",
        agent_config={"cwd": str(tmp_path)},
    )

    queue = await orchestrator.start_turn(conv.id, "dangerous command")

    # Drain until the ApprovalRequest arrives.
    collected: list[Any] = []
    while True:
        event = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert event is not None, "stream ended before ApprovalRequest arrived"
        collected.append(event)
        if isinstance(event, ApprovalRequest):
            break

    approval_event: ApprovalRequest = event

    # Deliver the deny decision through the real orchestrator path.
    orchestrator.submit_approval(
        conv.id,
        approval_event.request_id,
        ApprovalDecision(behavior="deny", message="tool call not permitted"),
    )

    # Collect the rest of the stream.
    collected.extend(await _drain(queue))

    # The adapter must have written {decision: "decline"} back to the fake.
    assert server.approval_replies.get(approval_event.request_id) == {"decision": "decline"}, (
        f"expected {{decision: decline}}, got {server.approval_replies!r}"
    )

    # The turn must finish cleanly.
    assert any(isinstance(e, ApprovalRequest) for e in collected)
    assert any(isinstance(e, TurnDone) for e in collected), (
        f"no TurnDone in events: {[type(e).__name__ for e in collected]}"
    )
    assert not any(isinstance(e, TurnError) for e in collected)
