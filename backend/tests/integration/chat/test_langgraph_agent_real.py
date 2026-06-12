"""Integration tests for LangGraphBuiltinAgent against scripted LangChain models.

These tests drive the real ``LangGraphBuiltinAgent`` adapter (no mocking of the
infrastructure layer). The adapter is now self-contained — its model, tool
gateway, and system prompt are constructor arguments — so a scripted
``BaseChatModel`` is injected directly, no monkeypatching required.

Covered scenarios
-----------------
1. Plain text turn — ``TurnStarted`` + ``TextDelta``(s) + ``TurnDone``.
2. Tool-call turn — ``ToolCall`` + ``ToolResult`` emitted; tool invoked via gateway.
3. Tool raises — ``ToolResult(error=...)`` emitted; turn still completes normally.
4. Provider failure — model raises → ``TurnError``.
5. History with prior tool use is passed to the model.
6. ``run_turn`` is a coroutine returning an async iterator (protocol check).
7. Recursion limit — graph hits the cap → ``TurnDone(stop_reason='max_iterations')``.
8. List-form AIMessage content — Anthropic multi-part content is emitted as text.
"""

from __future__ import annotations

import inspect
import warnings
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.chat.approvals import ApprovalChannel
from coffer.application.chat.ports import ToolSpec
from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
    TurnDone,
    TurnError,
)
from coffer.domain.chat.message import Message, Role, TextBlock, ToolResultBlock, ToolUseBlock
from coffer.infrastructure.chat.langgraph_agent import LangGraphBuiltinAgent

# Suppress LangGraph deprecation warnings about create_react_agent location.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langgraph")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_message(text: str, seq: int = 0) -> Message:
    return Message(
        id=f"msg-{seq}",
        conversation_id="conv-1",
        seq=seq,
        role=Role.USER,
        content=[TextBlock(text=text)],
        status="complete",
        model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        created_at=datetime.now(tz=UTC),
    )


def _make_scripted_model(responses: list[Any]) -> Any:
    """Create a ``BaseChatModel`` that cycles through *responses* in order."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.outputs import ChatGeneration, ChatResult

    class ScriptedModel(BaseChatModel):
        responses: list[Any]
        call_count: int = 0

        @property
        def _llm_type(self) -> str:
            return "scripted-test-model"

        def _generate(
            self,
            messages: list[Any],
            stop: list[str] | None = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            idx = min(self.call_count, len(self.responses) - 1)
            response = self.responses[idx]
            self.call_count += 1
            return ChatResult(generations=[ChatGeneration(message=response)])

        def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
            return self

    return ScriptedModel(responses=responses)


class FakeToolGateway:
    """Minimal ToolGateway for testing."""

    def __init__(
        self,
        specs: list[Any] | None = None,
        results: dict[str, Any] | None = None,
        raise_on: str | None = None,
    ) -> None:
        self._specs = specs or []
        self._results = results or {}
        self._raise_on = raise_on
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[Any]:
        return self._specs

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, args))
        if self._raise_on and name == self._raise_on:
            raise RuntimeError(f"Tool '{name}' intentionally failed")
        return self._results.get(name, {"result": f"ok:{name}"})


def _make_agent(
    fake_model: Any,
    gateway: FakeToolGateway,
    *,
    recursion_limit: int | None = None,
) -> LangGraphBuiltinAgent:
    """Build a ``LangGraphBuiltinAgent`` with the scripted model baked in."""
    kwargs: dict[str, Any] = {
        "lc_model": fake_model,
        "tool_gateway": gateway,
        "system_prompt": "You are a helpful assistant.",
        "model_id": "m-test",
    }
    if recursion_limit is not None:
        kwargs["recursion_limit"] = recursion_limit
    return LangGraphBuiltinAgent(**kwargs)


async def _collect_events(
    agent: LangGraphBuiltinAgent, history: list[Message] | None = None
) -> list[AgentEvent]:
    """Run a single turn and collect all emitted events."""
    events: list[AgentEvent] = []
    async for event in await agent.run_turn(
        history=history or [_user_message("hello")],
        approvals=ApprovalChannel(),
    ):
        events.append(event)
    return events


# ---------------------------------------------------------------------------
# Test 1: plain text turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_text_turn() -> None:
    """A plain text response yields TurnStarted + TextDelta(s) + TurnDone."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    fake_model = _make_scripted_model(
        [
            AIMessage(
                content="Hello, I am a helpful assistant.",
                usage_metadata={"input_tokens": 10, "output_tokens": 6, "total_tokens": 16},
            ),
        ]
    )
    agent = _make_agent(fake_model, FakeToolGateway())

    events = await _collect_events(agent)

    types = [type(e).__name__ for e in events]
    assert "TurnStarted" in types
    assert "TextDelta" in types
    assert types[-1] == "TurnDone"
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "Hello" in text


# ---------------------------------------------------------------------------
# Test 2: tool-call turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="008-agent-chat", scenario="the agent calls a vault tool")
async def test_tool_call_turn() -> None:
    """A tool-call turn emits ToolCall + ToolResult; the tool runs via the gateway."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    spec = ToolSpec(
        name="search",
        description="Search for information",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    fake_model = _make_scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_abc",
                        "name": "search",
                        "args": {"query": "q"},
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="Based on the search results, here is what I found.",
                usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            ),
        ]
    )
    gateway = FakeToolGateway(specs=[spec], results={"search": {"results": ["r1", "r2"]}})
    agent = _make_agent(fake_model, gateway)

    events = await _collect_events(agent)

    types = [type(e).__name__ for e in events]
    assert "ToolCall" in types
    assert "ToolResult" in types
    assert types[-1] == "TurnDone"
    assert len(gateway.calls) >= 1
    tool_result = next(e for e in events if isinstance(e, ToolResult))
    assert tool_result.tool_name == "search"
    assert tool_result.error is None
    assert tool_result.output is not None
    tool_call = next(e for e in events if isinstance(e, ToolCall))
    assert tool_call.tool_name == "search"


# ---------------------------------------------------------------------------
# Test 3: tool raises — ToolResult with error, turn still completes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="a failed tool call does not break the turn"
)
async def test_tool_raises_emits_error_result() -> None:
    """A tool exception produces ToolResult(error=...), but the turn completes."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    spec = ToolSpec(
        name="risky_tool",
        description="A tool that may fail",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
    )
    fake_model = _make_scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "c1", "name": "risky_tool", "args": {"x": 42}, "type": "tool_call"}
                ],
            ),
            AIMessage(
                content="The tool failed, but I can still respond.",
                usage_metadata={"input_tokens": 15, "output_tokens": 8, "total_tokens": 23},
            ),
        ]
    )
    gateway = FakeToolGateway(specs=[spec], raise_on="risky_tool")
    agent = _make_agent(fake_model, gateway)

    events = await _collect_events(agent)

    types = [type(e).__name__ for e in events]
    assert "ToolResult" in types
    assert "TurnError" not in types
    assert types[-1] == "TurnDone"
    tool_result = next(e for e in events if isinstance(e, ToolResult))
    assert tool_result.error is not None
    assert tool_result.output is None


# ---------------------------------------------------------------------------
# Test 4: provider failure → TurnError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_failure_emits_turn_error() -> None:
    """A model/provider exception produces TurnError."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.outputs import ChatResult

    class ExplodingModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "exploding"

        def _generate(
            self,
            messages: list[Any],
            stop: list[str] | None = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            raise ConnectionError("Provider unreachable")

        def bind_tools(self, tools: Any, **kwargs: Any) -> ExplodingModel:
            return self

    agent = _make_agent(ExplodingModel(), FakeToolGateway())

    events = await _collect_events(agent)

    types = [type(e).__name__ for e in events]
    assert "TurnStarted" in types
    assert "TurnError" in types
    err = next(e for e in events if isinstance(e, TurnError))
    assert err.code == "AGENT_ERROR"
    assert "Provider unreachable" in err.message


# ---------------------------------------------------------------------------
# Test 5: history with prior tool use is passed to the model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_with_tool_use_is_converted() -> None:
    """Prior ToolUseBlock + ToolResultBlock in history convert to LangChain messages."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    fake_model = _make_scripted_model(
        [
            AIMessage(
                content="I remember the previous tool call.",
                usage_metadata={"input_tokens": 30, "output_tokens": 7, "total_tokens": 37},
            ),
        ]
    )
    agent = _make_agent(fake_model, FakeToolGateway())

    now = datetime.now(tz=UTC)
    history = [
        _user_message("Do something with a tool", seq=0),
        Message(
            id="msg-1",
            conversation_id="conv-1",
            seq=1,
            role=Role.ASSISTANT,
            content=[
                ToolUseBlock(tool_use_id="tc", tool_name="prior_tool", tool_input={"key": "val"}),
                ToolResultBlock(
                    tool_use_id="tc",
                    tool_name="prior_tool",
                    output={"result": "prior_result"},
                    error=None,
                ),
            ],
            status="complete",
            model_id="m-test",
            prompt_tokens=10,
            completion_tokens=5,
            created_at=now,
        ),
        _user_message("What happened?", seq=2),
    ]

    events = await _collect_events(agent, history=history)

    types = [type(e).__name__ for e in events]
    assert "TurnDone" in types
    assert "TurnError" not in types


# ---------------------------------------------------------------------------
# Test 6: run_turn is a coroutine returning an async iterator (protocol check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_is_awaitable_returning_async_iterator() -> None:
    """run_turn must be awaitable and return an AsyncIterator (AgentAdapter seam)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    fake_model = _make_scripted_model([AIMessage(content="ok")])
    agent = _make_agent(fake_model, FakeToolGateway())

    result = agent.run_turn(history=[_user_message("hi")], approvals=ApprovalChannel())
    assert inspect.iscoroutine(result)

    iterator = await result
    assert hasattr(iterator, "__aiter__")
    assert hasattr(iterator, "__anext__")
    async for _ in iterator:
        pass


# ---------------------------------------------------------------------------
# Test 7: recursion limit — graph caps tool loops → TurnDone(max_iterations)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="008-agent-chat", scenario="tool-iteration limit ends the turn cleanly"
)
async def test_recursion_limit_ends_turn_cleanly() -> None:
    """Hitting the recursion cap yields TurnDone(stop_reason='max_iterations'), not TurnError."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    spec = ToolSpec(
        name="loop_tool",
        description="A tool that gets called repeatedly",
        input_schema={
            "type": "object",
            "properties": {"n": {"type": "integer"}},
            "required": ["n"],
        },
    )
    always_tool_call = AIMessage(
        content="",
        tool_calls=[{"id": "cl", "name": "loop_tool", "args": {"n": 1}, "type": "tool_call"}],
    )
    fake_model = _make_scripted_model([always_tool_call])
    gateway = FakeToolGateway(specs=[spec], results={"loop_tool": {"result": "ok"}})
    agent = _make_agent(fake_model, gateway, recursion_limit=3)

    events = await _collect_events(agent)

    types = [type(e).__name__ for e in events]
    assert types[-1] == "TurnDone"
    assert "TurnError" not in types
    done = next(e for e in events if isinstance(e, TurnDone))
    assert done.stop_reason == "max_iterations"


# ---------------------------------------------------------------------------
# Test 8: list-form AIMessage content is emitted as TextDelta
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_content_aimessage_emits_text_delta() -> None:
    """An AIMessage with list-form content (Anthropic multi-part) emits TextDelta."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langchain_core.messages import AIMessage

    list_content_message = AIMessage(
        content=[
            {"type": "text", "text": "Hello from "},
            {"type": "text", "text": "multi-part content."},
        ],
        usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
    )
    fake_model = _make_scripted_model([list_content_message])
    agent = _make_agent(fake_model, FakeToolGateway())

    events = await _collect_events(agent)

    types = [type(e).__name__ for e in events]
    assert "TextDelta" in types
    assert types[-1] == "TurnDone"
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "Hello from " in text
    assert "multi-part content." in text


# ---------------------------------------------------------------------------
# Test 9: an orphan ToolUseBlock (interrupted before its result) gets a
# synthesized ToolMessage so the model history stays valid (no provider 400).
# ---------------------------------------------------------------------------


def test_history_to_lc_synthesizes_result_for_orphan_tool_use() -> None:
    """A ToolUseBlock with no matching ToolResultBlock must still produce a
    paired ToolMessage, or every later turn 400s on an unanswered tool_call."""
    from langchain_core.messages import AIMessage, ToolMessage

    from coffer.infrastructure.chat.langgraph_agent import _history_to_lc

    now = datetime.now(tz=UTC)
    history = [
        _user_message("call a tool", seq=0),
        # Assistant turn interrupted after the tool_use but before its result.
        Message(
            id="msg-1",
            conversation_id="conv-1",
            seq=1,
            role=Role.ASSISTANT,
            content=[
                TextBlock(text="working on it"),
                ToolUseBlock(tool_use_id="orphan", tool_name="some_tool", tool_input={"k": "v"}),
            ],
            status="complete",
            model_id="m-test",
            prompt_tokens=None,
            completion_tokens=None,
            created_at=now,
        ),
        _user_message("are you there?", seq=2),
    ]

    lc_messages = _history_to_lc(history)

    ai_messages = [m for m in lc_messages if isinstance(m, AIMessage) and m.tool_calls]
    assert len(ai_messages) == 1
    call_ids = {tc["id"] for tc in ai_messages[0].tool_calls}
    tool_message_ids = {m.tool_call_id for m in lc_messages if isinstance(m, ToolMessage)}
    # Every emitted tool_call must have a paired ToolMessage answering it.
    assert call_ids <= tool_message_ids, "orphan tool_call left without a ToolMessage"
