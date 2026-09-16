"""Agentic langgraph tidy loop over one collection's files (spec knowledge).

The create_react_agent loop driven by Coffer's internal model over the files a
collection already holds, with 4 internal write-capable tools. Lives in
``infrastructure.llm`` (Contract 9a — the only place langchain/langgraph may be
imported; ``infrastructure.chat``, where these adapters once lived, is now
forbidden one).

The reorg tools are internal-only: NOT registered on the MCP gateway or
BuiltinToolRegistry.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Sequence
from typing import Any

from coffer.infrastructure.llm.langchain_models import build_chat_model
from coffer.infrastructure.llm.tool_schema import sanitise_name, schema_to_pydantic

log = logging.getLogger(__name__)

DEFAULT_REORG_RECURSION_LIMIT = 24


async def run_agentic_reorg(
    *,
    lc_model: Any,
    tools: Sequence[Any],
    system_prompt: str,
    recursion_limit: int = DEFAULT_REORG_RECURSION_LIMIT,
) -> dict[str, Any]:
    """Run the reorg loop; return a result dict.

    Each tool in ``tools`` is duck-typed with ``.name``, ``.description``,
    ``.input_schema`` (JSON-Schema dict), and ``.handler`` (async callable).
    Catches ``GraphRecursionError`` and returns ``{"truncated": True}`` so the
    service can finalize from on-disk state + action counters even when the loop
    overruns.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent

    from langchain_core.messages import HumanMessage
    from langchain_core.tools import StructuredTool
    from langgraph.errors import GraphRecursionError
    from langgraph.prebuilt import ToolNode

    lc_tools: list[Any] = []
    for tool in tools:
        tool_name = tool.name
        tool_handler = tool.handler

        async def _coroutine(
            _name: str = tool_name,
            _handler: Any = tool_handler,
            **kwargs: Any,
        ) -> dict[str, Any]:
            result: dict[str, Any] = await _handler(kwargs)
            return result

        lc_tool = StructuredTool.from_function(
            coroutine=_coroutine,
            name=sanitise_name(tool_name),
            description=tool.description or tool_name,
            args_schema=schema_to_pydantic(tool_name, tool.input_schema),
        )
        lc_tools.append(lc_tool)

    tool_node = ToolNode(lc_tools, handle_tool_errors=True)
    graph = create_react_agent(lc_model, tools=tool_node, prompt=system_prompt)

    try:
        state = await graph.ainvoke(
            {"messages": [HumanMessage(content="Reorganize the files in this collection.")]},
            config={"recursion_limit": recursion_limit},
        )
    except GraphRecursionError:
        log.warning(
            "reorg recursion limit (%d) reached; finalizing from on-disk state",
            recursion_limit,
        )
        return {"truncated": True}

    return {"messages": state.get("messages", [])}


class LangchainAgenticReorg:
    """AgenticReorgPort implementation using the langgraph create_react_agent."""

    async def run(
        self,
        *,
        model: Any,
        tools: Sequence[Any],
        system_prompt: str,
        credential_resolver: Any,
        recursion_limit: int,
    ) -> dict[str, Any]:
        lc_model = build_chat_model(model, credential_resolver)
        return await run_agentic_reorg(
            lc_model=lc_model,
            tools=tools,
            system_prompt=system_prompt,
            recursion_limit=recursion_limit,
        )


__all__ = [
    "DEFAULT_REORG_RECURSION_LIMIT",
    "LangchainAgenticReorg",
    "run_agentic_reorg",
]
