"""Agentic retrieval over the vault — the engine behind ``coffer__ask``.

This module (with ``langchain_models.py`` and ``llm_completion.py``) is one of
the only importers of ``langgraph`` / ``langchain*``; import-linter Contract 9
enforces the boundary (everything here lives under ``infrastructure.chat``).

``coffer__ask`` is an internal Coffer built-in MCP tool, NOT a chat persona
(ADR-024). The calling agent (Claude Code / Codex, or a Coffer-internal flow)
invokes it with a natural-language ``query``; the engine runs a bounded
retrieve-and-synthesize ReAct loop over the user's **knowledge base + memory**
(read-only tools only) using Coffer's configured internal model, and returns a
synthesized answer plus the list of sources it consulted.

The loop reuses the same in-process gateway session the rest of Coffer uses
(``coffer-builtin-agent``); only the retrieval tools below are exposed to the
model, so the loop can never call ``coffer__ask`` recursively or reach upstream
write tools.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.builtin_tools import BuiltinTool
from coffer.application.chat.ports import ToolGateway, ToolSpec
from coffer.domain.provider.config import ResolvedConnection
from coffer.infrastructure.chat.langchain_models import build_chat_model

log = logging.getLogger(__name__)

# Default cap on LangGraph graph steps before it stops. Each tool call is ~2
# steps (agent → tools); 16 steps ≈ 7 retrieval calls — enough to retrieve and
# synthesize, bounded so a confused model can't loop forever.
DEFAULT_RECURSION_LIMIT = 16

# Read-only knowledge + memory tools the agentic-RAG loop may call. Deliberately
# excludes write tools (remember), tool-search, and coffer__ask itself, so the
# loop stays a pure retrieval+synthesis over the vault and can never recurse into
# itself.
RETRIEVAL_TOOLS: frozenset[str] = frozenset(
    {
        "coffer__search_knowledge",
        "coffer__grep_knowledge",
        "coffer__read_document",
        "coffer__list_knowledge_bases",
        "coffer__recall",
        "coffer__list_memory",
    }
)

ASK_TOOL_NAME = "ask"

_ASK_DESCRIPTION = (
    "Ask a question of the Coffer vault (the user's knowledge base + memory) and "
    "get a synthesized, cited answer. Coffer runs a multi-step retrieval over the "
    "vault internally — use this instead of issuing many search_knowledge / "
    "read_document / recall calls yourself when you need an answer that spans "
    "several documents or memories."
)

_ASK_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The question to answer from the vault, in natural language.",
        },
    },
    "required": ["query"],
}

_SYSTEM_PROMPT = (
    "You are Coffer's internal retrieval assistant. Answer the user's question "
    "using ONLY the Coffer vault, reached through the provided tools (knowledge "
    "base search/grep/read and memory recall/list). Do not use outside "
    "knowledge.\n\n"
    "Work in steps: search or recall to find relevant material, read the most "
    "promising documents, then synthesize a concise answer. If the vault does "
    "not contain the answer, say so plainly rather than guessing. Cite the "
    "knowledge-base documents or memories you relied on."
)


async def run_agentic_rag(
    *,
    lc_model: Any,
    tool_gateway: ToolGateway,
    query: str,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> dict[str, Any]:
    """Run the retrieve-and-synthesize loop; return ``{answer, sources}``.

    Only the tools in :data:`RETRIEVAL_TOOLS` are exposed to the model. The
    final assistant message is the answer; ``sources`` lists every retrieval
    tool call the loop made (name + arguments), in order.
    """
    specs = [s for s in await tool_gateway.list_tools() if s.name in RETRIEVAL_TOOLS]
    lc_tools = _wrap_tool_specs(specs, tool_gateway)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent

    from langchain_core.messages import HumanMessage
    from langgraph.errors import GraphRecursionError
    from langgraph.prebuilt import ToolNode

    tool_node = ToolNode(lc_tools, handle_tool_errors=True)
    graph = create_react_agent(lc_model, tools=tool_node, prompt=_SYSTEM_PROMPT)

    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content=query)]},
            config={"recursion_limit": recursion_limit},
        )
    except GraphRecursionError:
        log.warning("coffer__ask recursion limit (%d) reached", recursion_limit)
        return {
            "answer": (
                "Could not finish retrieving an answer within the step budget. "
                "Try a more specific question."
            ),
            "sources": [],
            "truncated": True,
        }

    messages = state.get("messages", [])
    return {"answer": _final_text(messages), "sources": _collect_sources(messages)}


def make_ask_tool(
    *,
    resolve_connection: Callable[[], Awaitable[ResolvedConnection | None]],
    tool_gateway: ToolGateway,
    credential_resolver: Any,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> BuiltinTool:
    """Build the ``coffer__ask`` built-in tool, closing over its dependencies.

    ``resolve_connection`` returns Coffer's internal-engine connection (the
    ``internal_default`` provider) or ``None`` when none is configured.
    Registered into the ``BuiltinToolRegistry`` by the composition root so the
    gateway advertises it alongside the other ``coffer__`` built-ins.
    """

    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")
        model = await resolve_connection()
        if model is None:
            raise ValueError(
                "No internal connection configured. Set an LLM connection as the "
                "Coffer internal engine in Settings before using coffer__ask."
            )
        lc_model = build_chat_model(model, credential_resolver)
        return await run_agentic_rag(
            lc_model=lc_model,
            tool_gateway=tool_gateway,
            query=query,
            recursion_limit=recursion_limit,
        )

    return BuiltinTool(
        name=ASK_TOOL_NAME,
        description=_ASK_DESCRIPTION,
        input_schema=_ASK_INPUT_SCHEMA,
        handler=_handler,
    )


# ---------------------------------------------------------------------------
# Answer / source extraction
# ---------------------------------------------------------------------------


def _final_text(messages: list[Any]) -> str:
    """The text of the last AI message (the synthesized answer)."""
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        msg_type = getattr(msg, "type", None)
        if msg_type == "ai" and content:
            if isinstance(content, str):
                return content
            # Some providers return a list of content blocks.
            parts = [str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in content]
            joined = " ".join(p for p in parts if p)
            if joined:
                return joined
    return ""


def _collect_sources(messages: list[Any]) -> list[dict[str, Any]]:
    """List the retrieval tool calls the loop made, in order (name + args)."""
    sources: list[dict[str, Any]] = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
            if name:
                sources.append({"tool": name, "input": args or {}})
    return sources


# ---------------------------------------------------------------------------
# Tool wrapping (shared LangChain glue, formerly in langgraph_agent.py)
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


__all__ = [
    "ASK_TOOL_NAME",
    "DEFAULT_RECURSION_LIMIT",
    "RETRIEVAL_TOOLS",
    "make_ask_tool",
    "run_agentic_rag",
]
