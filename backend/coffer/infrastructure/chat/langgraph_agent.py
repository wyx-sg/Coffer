"""LangGraphBuiltinAgent — the ``AgentAdapter`` for Coffer's built-in agent.

This file (with ``langchain_models.py`` and ``_event_mapping.py``) is the only
importer of ``langgraph`` / ``langchain*``. Import-linter Contract 9 enforces
the boundary.

The adapter is **self-contained** (the platform's ``AgentAdapter`` seam): it is
built once per turn by ``BuiltinAgentProvider.build_adapter`` with its
LangChain model, tool gateway, system prompt, and the resolved model id all
baked in. ``run_turn`` is then given only the conversation history and the
approval channel.

History trimming
----------------
The built-in agent trims the history to its context budget itself — the budget
is an agent-specific concern, not the orchestrator's. A truncation notice is
appended to the system prompt when older messages are dropped.

Approval channel
----------------
The built-in agent relies on the MCP gateway's capability gating and never
pauses for per-call human approval, so ``run_turn``'s ``approvals`` argument is
accepted (to satisfy the ``AgentAdapter`` seam) but not used.

Tool wrapping
-------------
Each ``ToolSpec`` from the gateway becomes a ``StructuredTool`` whose coroutine
calls ``tool_gateway.call_tool(name, args)``. The ``ToolNode`` is configured
with ``handle_tool_errors=True`` so a gateway exception becomes a
``ToolMessage(status='error')`` rather than crashing the graph — it surfaces as
a ``ToolResult(error=...)`` event and the turn stays alive (FR-014).

Recursion limit
---------------
A ``GraphRecursionError`` means the model kept calling tools past the iteration
cap. It is caught and turned into ``TurnDone(stop_reason='max_iterations')``
rather than a ``TurnError`` (FR-008).
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import AsyncIterator, Sequence
from typing import Any

from coffer.application.chat.history import DEFAULT_CHAR_BUDGET, trim_history
from coffer.application.chat.ports import ApprovalGate, ToolGateway, ToolSpec
from coffer.domain.chat.events import AgentEvent, TurnDone, TurnError, TurnStarted
from coffer.domain.chat.message import Message, Role, TextBlock, ToolResultBlock, ToolUseBlock

log = logging.getLogger(__name__)

# Default cap on how many graph steps LangGraph takes before raising
# GraphRecursionError. Each tool call counts as ~2 steps (agent → tools);
# 25 steps ≈ 12 tool calls.
DEFAULT_RECURSION_LIMIT = 25

# Appended to the system prompt for a turn whose older history was trimmed.
_TRUNCATION_NOTICE = (
    "\n\nNote: earlier messages in this conversation were omitted to fit the context window."
)


class LangGraphBuiltinAgent:
    """Built-in agent adapter using LangGraph's ``create_react_agent`` loop.

    Parameters
    ----------
    lc_model:
        A ready LangChain ``BaseChatModel`` (built by the provider).
    tool_gateway:
        Coffer's in-process MCP gateway view; its tools are wrapped per turn.
    system_prompt:
        The base system prompt (Coffer identity + skill catalogue).
    model_id:
        The ``chat_models.id`` this turn runs on; read by the orchestrator to
        stamp the assistant message.
    recursion_limit:
        Max LangGraph graph steps before the turn ends with
        ``TurnDone(stop_reason='max_iterations')``.
    char_budget:
        Context-window budget (chars) for history trimming.
    """

    def __init__(
        self,
        *,
        lc_model: Any,
        tool_gateway: ToolGateway,
        system_prompt: str,
        model_id: str,
        recursion_limit: int = DEFAULT_RECURSION_LIMIT,
        char_budget: int = DEFAULT_CHAR_BUDGET,
    ) -> None:
        self._lc_model = lc_model
        self._tool_gateway = tool_gateway
        self._system_prompt = system_prompt
        self.model_id = model_id
        self._recursion_limit = recursion_limit
        self._char_budget = char_budget

    # ------------------------------------------------------------------
    # AgentAdapter protocol
    # ------------------------------------------------------------------

    async def run_turn(
        self,
        *,
        history: Sequence[Message],
        approvals: ApprovalGate,
    ) -> AsyncIterator[AgentEvent]:
        """Coroutine that performs setup and returns an async-generator.

        ``approvals`` is part of the ``AgentAdapter`` seam but unused: the
        built-in agent relies on the gateway's capability gating.
        """
        del approvals  # unused — see module docstring

        trimmed, truncated = trim_history(list(history), self._char_budget)
        system_prompt = self._system_prompt
        if truncated:
            system_prompt = system_prompt + _TRUNCATION_NOTICE

        # Fetch and wrap tools from the gateway.
        tool_specs = await self._tool_gateway.list_tools()
        lc_tools = _wrap_tool_specs(tool_specs, self._tool_gateway)

        # Convert domain history to LangChain messages.
        lc_history = _history_to_lc(trimmed)

        return self._stream(
            lc_model=self._lc_model,
            lc_tools=lc_tools,
            lc_history=lc_history,
            system_prompt=system_prompt,
        )

    # ------------------------------------------------------------------
    # Internal async-generator
    # ------------------------------------------------------------------

    async def _stream(
        self,
        *,
        lc_model: Any,
        lc_tools: list[Any],
        lc_history: list[Any],
        system_prompt: str,
    ) -> AsyncIterator[AgentEvent]:
        """Async-generator: drive the LangGraph graph and yield AgentEvents."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from langgraph.prebuilt import create_react_agent

        from langgraph.errors import GraphRecursionError
        from langgraph.prebuilt import ToolNode

        from coffer.infrastructure.chat._event_mapping import map_graph_stream

        yield TurnStarted()

        try:
            # ToolNode with error handling so tool exceptions become
            # ToolMessage(status='error') instead of crashing the graph.
            tool_node = ToolNode(lc_tools, handle_tool_errors=True)

            graph = create_react_agent(lc_model, tools=tool_node, prompt=system_prompt)

            raw_stream = graph.astream(
                {"messages": lc_history},
                stream_mode=["messages", "updates"],
                config={"recursion_limit": self._recursion_limit},
            )

            async for event in map_graph_stream(raw_stream):
                yield event

        except GraphRecursionError:
            log.warning("LangGraph recursion limit (%d) reached", self._recursion_limit)
            yield TurnDone(
                prompt_tokens=None,
                completion_tokens=None,
                stop_reason="max_iterations",
            )
        except Exception as exc:
            log.exception("LangGraph turn failed: %s", exc)
            yield TurnError(code="AGENT_ERROR", message=str(exc))


# ---------------------------------------------------------------------------
# History conversion
# ---------------------------------------------------------------------------


def _history_to_lc(history: Sequence[Message]) -> list[Any]:
    """Convert domain ``Message`` objects to LangChain message objects."""
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        ToolMessage,
    )

    lc_messages: list[Any] = []

    for msg in history:
        if msg.role == Role.USER:
            text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
            text = " ".join(text_parts)
            if text:
                lc_messages.append(HumanMessage(content=text))
        elif msg.role == Role.ASSISTANT:
            text_parts = [b.text for b in msg.content if isinstance(b, TextBlock)]
            tool_use_blocks = [b for b in msg.content if isinstance(b, ToolUseBlock)]
            tool_result_blocks = [b for b in msg.content if isinstance(b, ToolResultBlock)]

            if tool_use_blocks:
                tool_calls = [
                    {
                        "id": b.tool_use_id,
                        "name": b.tool_name,
                        "args": b.tool_input,
                        "type": "tool_call",
                    }
                    for b in tool_use_blocks
                ]
                text = " ".join(text_parts)
                lc_messages.append(AIMessage(content=text, tool_calls=tool_calls))
                results_by_id = {b.tool_use_id: b for b in tool_result_blocks}
                # Every tool_call MUST be answered by a ToolMessage, or the
                # provider rejects the whole history with a 400. A turn that was
                # interrupted (or crashed) after emitting a tool_call but before
                # its result leaves an orphan ToolUseBlock; synthesize a result
                # for it so the conversation stays usable.
                for use_block in tool_use_blocks:
                    result_block = results_by_id.get(use_block.tool_use_id)
                    if result_block is not None:
                        output_str = (
                            result_block.error
                            if result_block.error is not None
                            else str(result_block.output or "")
                        )
                        status = "error" if result_block.error is not None else "success"
                        name = result_block.tool_name
                    else:
                        output_str = "Tool call did not complete (the turn was interrupted)."
                        status = "error"
                        name = use_block.tool_name
                    lc_messages.append(
                        ToolMessage(
                            content=output_str,
                            tool_call_id=use_block.tool_use_id,
                            name=name,
                            status=status,
                        )
                    )
            else:
                text = " ".join(text_parts)
                if text:
                    lc_messages.append(AIMessage(content=text))

    return lc_messages


# ---------------------------------------------------------------------------
# Tool wrapping
# ---------------------------------------------------------------------------


def _wrap_tool_specs(specs: list[ToolSpec], gateway: ToolGateway) -> list[Any]:
    """Wrap each ``ToolSpec`` as a LangChain ``StructuredTool``."""
    from langchain_core.tools import StructuredTool

    tools: list[Any] = []
    for spec in specs:
        spec_name = spec.name
        spec_input_schema = spec.input_schema

        async def _coroutine(
            _name: str = spec_name,
            _gateway: ToolGateway = gateway,
            **kwargs: Any,
        ) -> dict[str, Any]:
            return await _gateway.call_tool(_name, kwargs)

        tool = StructuredTool.from_function(
            coroutine=_coroutine,
            name=spec_name,
            description=spec.description or spec_name,
            args_schema=_schema_to_pydantic(spec_name, spec_input_schema),
        )
        tools.append(tool)

    return tools


def _schema_to_pydantic(tool_name: str, schema: dict[str, Any]) -> Any:
    """Build a minimal Pydantic v2 model from a JSON Schema dict."""
    from pydantic import BaseModel, create_model
    from pydantic.fields import FieldInfo

    properties: dict[str, Any] = schema.get("properties") or {}
    required: list[str] = schema.get("required") or []

    field_definitions: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        json_type = field_schema.get("type", "string")
        py_type: type = _json_type_to_python(json_type)
        description = field_schema.get("description", "")

        if field_name in required:
            field_definitions[field_name] = (py_type, FieldInfo(description=description))
        else:
            field_definitions[field_name] = (
                py_type | None,
                FieldInfo(default=None, description=description),
            )

    if not field_definitions:
        return create_model(f"Args_{_sanitise_name(tool_name)}", __base__=BaseModel)

    return create_model(
        f"Args_{_sanitise_name(tool_name)}",
        __base__=BaseModel,
        **field_definitions,
    )


def _json_type_to_python(json_type: str) -> type:
    mapping: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    return mapping.get(json_type, str)


def _sanitise_name(name: str) -> str:
    """Convert a tool name to a valid Python identifier fragment."""
    return name.replace("-", "_").replace(".", "_")


__all__ = ["DEFAULT_RECURSION_LIMIT", "LangGraphBuiltinAgent"]
