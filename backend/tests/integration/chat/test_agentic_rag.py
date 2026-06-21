"""Tests for the agentic-RAG engine behind ``coffer__ask`` (ADR-024).

The built-in chat persona is retired; the local model's job is now this internal
retrieve-and-synthesize tool. These tests cover its descriptor, error paths,
answer/source extraction, the read-only tool whitelist, and a real (fake-model)
loop end to end.
"""

from __future__ import annotations

from typing import Any

import pytest

from coffer.application.chat.ports import ToolSpec
from coffer.infrastructure.chat.agentic_rag import (
    ASK_TOOL_NAME,
    RETRIEVAL_TOOLS,
    _collect_sources,
    _final_text,
    make_ask_tool,
    run_agentic_rag,
)


class _FakeGateway:
    """ToolGateway returning a fixed spec list; records every call_tool."""

    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs = specs
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[ToolSpec]:
        return self._specs

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, args))
        return {"results": ["a knowledge snippet"]}


class _FakeModelService:
    def __init__(self, default: Any = None) -> None:
        self._default = default

    async def get_default(self) -> Any:
        return self._default


def _fake_chat_model(scripted: list[Any]) -> Any:
    """A GenericFakeChatModel whose bind_tools is a no-op (returns self)."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    class _Model(GenericFakeChatModel):  # type: ignore[misc]
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

    return _Model(messages=iter(scripted))


def _spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=name,
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


# ---------------------------------------------------------------------------
# Descriptor + error paths (no graph needed)
# ---------------------------------------------------------------------------


def test_ask_tool_descriptor() -> None:
    tool = make_ask_tool(
        resolve_connection=_FakeModelService().get_default,
        tool_gateway=_FakeGateway([]),
        credential_resolver=lambda ref: "key",
    )
    assert tool.name == ASK_TOOL_NAME
    assert tool.input_schema["required"] == ["query"]


async def test_ask_rejects_empty_query() -> None:
    tool = make_ask_tool(
        resolve_connection=_FakeModelService().get_default,
        tool_gateway=_FakeGateway([]),
        credential_resolver=lambda ref: "key",
    )
    with pytest.raises(ValueError, match="non-empty string"):
        await tool.handler({"query": "   "})


async def test_ask_with_no_default_model_is_a_friendly_error() -> None:
    tool = make_ask_tool(
        resolve_connection=_FakeModelService(default=None).get_default,
        tool_gateway=_FakeGateway([]),
        credential_resolver=lambda ref: "key",
    )
    with pytest.raises(ValueError, match="No internal connection configured"):
        await tool.handler({"query": "what is in the vault?"})


# ---------------------------------------------------------------------------
# Whitelist + extraction helpers
# ---------------------------------------------------------------------------


def test_retrieval_whitelist_is_read_only_and_non_recursive() -> None:
    assert "coffer__search_knowledge" in RETRIEVAL_TOOLS
    assert "coffer__recall" in RETRIEVAL_TOOLS
    # Write tools, the tool-search meta-tool, and coffer__ask itself are excluded
    # so the loop can neither mutate the vault nor recurse into itself.
    for forbidden in ("coffer__remember", "coffer__forget", "coffer__ask", "coffer__search_tools"):
        assert forbidden not in RETRIEVAL_TOOLS


def test_final_text_picks_last_ai_message() -> None:
    from langchain_core.messages import AIMessage, HumanMessage

    msgs = [HumanMessage(content="q"), AIMessage(content="the synthesized answer")]
    assert _final_text(msgs) == "the synthesized answer"


def test_collect_sources_lists_retrieval_tool_calls() -> None:
    from langchain_core.messages import AIMessage

    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "1",
                "name": "coffer__search_knowledge",
                "args": {"query": "x"},
                "type": "tool_call",
            }
        ],
    )
    assert _collect_sources([ai]) == [{"tool": "coffer__search_knowledge", "input": {"query": "x"}}]


# ---------------------------------------------------------------------------
# End-to-end loop with a fake model
# ---------------------------------------------------------------------------


async def test_run_agentic_rag_direct_answer() -> None:
    """Model answers without retrieving: answer extracted, no sources."""
    from langchain_core.messages import AIMessage

    gateway = _FakeGateway([_spec("coffer__search_knowledge")])
    model = _fake_chat_model([AIMessage(content="The vault says 42.")])

    result = await run_agentic_rag(lc_model=model, tool_gateway=gateway, query="what?")

    assert result["answer"] == "The vault says 42."
    assert result["sources"] == []
    assert gateway.calls == []


async def test_run_agentic_rag_retrieves_then_synthesizes() -> None:
    """Model calls a retrieval tool, then synthesizes; only whitelisted tools
    are exposed, so the retrieval call reaches the gateway and is recorded as a
    source."""
    from langchain_core.messages import AIMessage

    # Gateway offers a read tool, a write tool, and coffer__ask itself; only the
    # read tool should be reachable by the loop.
    gateway = _FakeGateway(
        [
            _spec("coffer__search_knowledge"),
            _spec("coffer__remember"),
            _spec("coffer__ask"),
        ]
    )
    scripted = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "name": "coffer__search_knowledge",
                    "args": {"query": "topic"},
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Based on the vault, the answer is 42."),
    ]
    model = _fake_chat_model(scripted)

    result = await run_agentic_rag(lc_model=model, tool_gateway=gateway, query="topic?")

    assert result["answer"] == "Based on the vault, the answer is 42."
    assert [c[0] for c in gateway.calls] == ["coffer__search_knowledge"]
    assert result["sources"] == [{"tool": "coffer__search_knowledge", "input": {"query": "topic"}}]
