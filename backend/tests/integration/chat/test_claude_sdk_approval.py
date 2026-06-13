"""E2E acceptance test: per-tool approval relay for SDK-backed Claude Code.

Proves the FULL per-tool approval relay works for Claude Code through the REAL
turn machinery:

- A turn driven by ``ClaudeSdkProvider`` (wired to a ``FakeSdkSession``) streams
  assistant text, then requests a tool via ``can_use_tool`` (the SDK's permission
  callback).
- The turn pauses and emits an ``ApprovalRequest`` on the orchestrator's event
  queue.
- The human answers through the real ``orchestrator.submit_approval(...)`` path.
- Allow path: ``can_use_tool`` resolves to ``PermissionResultAllow`` and the turn
  ends with ``TurnDone``.
- Deny path: ``can_use_tool`` resolves to ``PermissionResultDeny`` (with the
  denial message) and the turn completes cleanly.

No real ``claude`` binary or network is touched — everything runs through the
``FakeSdkSession`` / ``_Factory`` fakes imported from the adapter-level unit
tests.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
)
from claude_agent_sdk import TextBlock as SdkTextBlock
from claude_agent_sdk import ToolUseBlock as SdkToolUseBlock

from coffer.application.audit_service import AuditService
from coffer.application.chat.ports import ApprovalDecision
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator, clear_active_turns
from coffer.domain.chat.events import ApprovalRequest, TurnDone, TurnError
from coffer.infrastructure.chat.claude_sdk_provider import ClaudeSdkProvider
from coffer.infrastructure.chat.persistence import (
    ConversationRepo,
    MessageRepo,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

# Re-use the fully-fledged FakeSdkSession + scripting helpers from the
# adapter-level unit tests (the task brief explicitly allows this).
from tests.integration.chat.test_claude_sdk_agent import (
    FakeSdkSession,  # noqa: F401
    _ApprovalScript,
    _Factory,
)
from tests.unit.chat.conftest import FakeAuditRepo

# ---------------------------------------------------------------------------
# Canned SDK message stream
# ---------------------------------------------------------------------------


def _approval_messages(session_id: str = "sdk-sess-1") -> list[Any]:
    """A scripted SDK stream: init → assistant text + tool-use → tool result → done."""
    return [
        SystemMessage(subtype="init", data={"session_id": session_id}),
        AssistantMessage(
            content=[
                SdkTextBlock(text="Running command for you."),
                SdkToolUseBlock(id="tu_approval", name="Bash", input={"command": "ls /"}),
            ],
            model="claude",
        ),
        AssistantMessage(
            content=[SdkTextBlock(text="Done.")],
            model="claude",
        ),
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id=session_id,
            usage={"input_tokens": 10, "output_tokens": 5},
            total_cost_usd=0.0,
        ),
    ]


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


async def _build_services(
    tmp_path: Any,
    factory: _Factory,
) -> tuple[ChatService, TurnOrchestrator]:
    """Wire a real SQLite repo + ClaudeSdkProvider + orchestrator."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'sdk_approval.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = session_maker(engine)
    conv_repo = ConversationRepo(sm)
    msg_repo = MessageRepo(sm)

    audit = AuditService(repo=FakeAuditRepo())  # type: ignore[arg-type]

    # ClaudeSdkProvider uses the same conv_repo so get/set_agent_config works.
    sdk_provider = ClaudeSdkProvider(
        conversations=conv_repo,
        session_factory=factory,
        which=lambda _: "/usr/bin/claude",  # pretend the binary exists
    )

    registry = AgentProviderRegistry()
    registry.register(sdk_provider, display_name="Claude Code (SDK)")

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


async def _drain(
    queue: asyncio.Queue[Any],
) -> list[Any]:
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
    scenario="per-tool approval relay works for SDK-backed Claude Code",
)
async def test_sdk_approval_allow_via_orchestrator(tmp_path: Any) -> None:
    """Allow path: the turn proceeds after the human grants permission.

    The FakeSdkSession fires ``can_use_tool`` (the adapter's permission
    callback) after the first AssistantMessage (index 1).  The orchestrator
    wires that callback to its ApprovalChannel; the test observes the
    ApprovalRequest event on the queue, calls ``submit_approval`` with
    ``behavior="allow"``, and asserts:
    - ``can_use_tool`` resolved to ``PermissionResultAllow``.
    - The turn stream ends with ``TurnDone`` (not ``TurnError``).
    """
    approval = _ApprovalScript(
        after_index=1,
        tool_name="Bash",
        tool_input={"command": "ls /"},
        tool_use_id="tu_approval",
    )
    factory = _Factory(_approval_messages(), approval=approval)

    chat_svc, orchestrator = await _build_services(tmp_path, factory)
    conv = await chat_svc.create_conversation(
        agent_key="claude_code",
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

    # Deliver the allow decision through the real orchestrator path.
    orchestrator.submit_approval(
        conv.id,
        event.request_id,
        ApprovalDecision(behavior="allow"),
    )

    # Collect the rest of the stream.
    collected.extend(await _drain(queue))

    # Await the approval task so its result field is populated.
    if factory.session is not None and factory.session.approval_task is not None:
        await asyncio.wait_for(factory.session.approval_task, timeout=5.0)

    # The can_use_tool callback must have received PermissionResultAllow.
    assert isinstance(approval.result, PermissionResultAllow), (
        f"expected PermissionResultAllow, got {approval.result!r}"
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
    scenario="per-tool approval relay works for SDK-backed Claude Code",
)
async def test_sdk_approval_deny_via_orchestrator(tmp_path: Any) -> None:
    """Deny path: the denial is delivered to the SDK callback and the turn completes.

    Same setup as the allow path, but ``submit_approval`` carries
    ``behavior="deny"`` with a message.  Asserts:
    - ``can_use_tool`` resolved to ``PermissionResultDeny`` with the correct message.
    - The turn stream ends cleanly (``TurnDone``, no ``TurnError``).
    """
    approval = _ApprovalScript(
        after_index=1,
        tool_name="Bash",
        tool_input={"command": "rm -rf /"},
        tool_use_id="tu_approval",
    )
    factory = _Factory(_approval_messages(), approval=approval)

    chat_svc, orchestrator = await _build_services(tmp_path, factory)
    conv = await chat_svc.create_conversation(
        agent_key="claude_code",
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

    # Deliver the deny decision through the real orchestrator path.
    orchestrator.submit_approval(
        conv.id,
        event.request_id,
        ApprovalDecision(behavior="deny", message="tool call not permitted"),
    )

    # Collect the rest of the stream.
    collected.extend(await _drain(queue))

    # Await the approval task so its result field is populated.
    if factory.session is not None and factory.session.approval_task is not None:
        await asyncio.wait_for(factory.session.approval_task, timeout=5.0)

    # The can_use_tool callback must have received PermissionResultDeny with the message.
    assert isinstance(approval.result, PermissionResultDeny), (
        f"expected PermissionResultDeny, got {approval.result!r}"
    )
    assert approval.result.message == "tool call not permitted"

    # The turn must finish cleanly.
    assert any(isinstance(e, ApprovalRequest) for e in collected)
    assert any(isinstance(e, TurnDone) for e in collected), (
        f"no TurnDone in events: {[type(e).__name__ for e in collected]}"
    )
    assert not any(isinstance(e, TurnError) for e in collected)
