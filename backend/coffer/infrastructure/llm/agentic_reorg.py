"""The agentic langgraph loop the knowledge curation pass runs on.

A ``create_react_agent`` loop driven by Coffer's internal model over one
collection's documents, with four internal write-capable tools. Lives in
``infrastructure.llm`` (Contract 9a — the only place langchain/langgraph may be
imported; ``infrastructure.chat``, where these adapters once lived, is now a
forbidden one).

The two prompts are kept apart on purpose. ``system_prompt`` carries the rules
a pass must obey, which are the same on every call; ``user_prompt`` carries the
brief — the source to absorb, the candidate documents and the catalogue — which
is different every time and can run to tens of kilobytes. Folding the brief
into the system prompt would work and would be wrong: it mixes what the model
must always do with what it happens to be looking at, and it is the system
prompt that a provider caches.

These tools are internal-only: NOT registered on the MCP gateway or the
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
    user_prompt: str,
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
            {"messages": [HumanMessage(content=user_prompt)]},
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
    """``AgenticCurationPort`` implementation over ``create_react_agent``."""

    async def run(
        self,
        *,
        model: Any,
        tools: Sequence[Any],
        system_prompt: str,
        user_prompt: str,
        credential_resolver: Any,
        recursion_limit: int,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        # The bound goes on the CLIENT, so it applies to each turn of the loop
        # rather than to the loop as a whole — see ``build_chat_model``.
        lc_model = build_chat_model(model, credential_resolver, timeout=timeout)
        return await run_agentic_reorg(
            lc_model=lc_model,
            tools=tools,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            recursion_limit=recursion_limit,
        )


__all__ = [
    "DEFAULT_REORG_RECURSION_LIMIT",
    "LangchainAgenticReorg",
    "run_agentic_reorg",
]
