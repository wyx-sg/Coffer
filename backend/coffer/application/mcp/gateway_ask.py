"""Serving ``coffer__ask`` (spec mcp-gateway "Let an agent ask the owner a
question during a Coffer turn").

The tool is turn-scoped: it is listed to, and served for, a session whose
requests carry the ``X-Coffer-Turn`` token of a turn Coffer is running — and
nobody else. The kind that runs turns sits behind ``TurnAskPort``; the gateway
never imports it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from coffer.application.mcp.gateway_builtin import _log, _to_call_tool_result, _tool_error_text
from coffer.application.mcp.ports import MCPInvocationRepoPort
from coffer.application.turn_ask import (
    NOT_IN_TURN_TEXT,
    TurnAskPort,
    ask_tool_descriptor,
    current_turn_ask,
)


def with_ask_tool(
    tools: list[dict[str, Any]], port: TurnAskPort | None, token: str | None
) -> list[dict[str, Any]]:
    """``tools`` plus ``coffer__ask`` when ``token`` names a live Coffer turn.
    Not tiered: it is one tool, offered only inside a turn."""
    port = port or current_turn_ask()
    if port is not None and port.is_live(token):
        return [*tools, ask_tool_descriptor()]
    return tools


async def dispatch_turn_ask(
    *,
    params: dict[str, Any],
    port: TurnAskPort | None,
    token: str | None,
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
    session_agent_uid: str | None = None,
) -> dict[str, Any]:
    """Serve a ``coffer__ask`` call: wait for the owner's answer and return it.
    Outside a Coffer turn the call is answered with a note, not an error."""
    port = port or current_turn_ask()
    if port is None or token is None or not port.is_live(token):
        return {"content": [{"type": "text", "text": NOT_IN_TURN_TEXT}], "isError": True}
    started = clock()
    try:
        result = await port.ask(token, params.get("arguments") or {})
    except Exception as exc:
        await _log(
            invocations,
            "ask",
            started,
            int((clock() - started).total_seconds() * 1000),
            status="error",
            error_message=type(exc).__name__,
            session_id=session_id,
            agent_uid=session_agent_uid,
        )
        return {"content": [{"type": "text", "text": _tool_error_text(exc)}], "isError": True}
    await _log(
        invocations,
        "ask",
        started,
        int((clock() - started).total_seconds() * 1000),
        status="ok",
        error_message=None,
        session_id=session_id,
        agent_uid=session_agent_uid,
    )
    return _to_call_tool_result(result)
