"""Translate ``cursor-agent`` stream-json NDJSON events into Coffer AgentEvents.

Pure mapping over parsed JSON lines — unit-tested with fixtures derived from
Cursor's documented ``--output-format stream-json`` schema (see :mod:`cursor_run`
for the framing caveat). The terminal ``TurnDone`` / ``TurnError`` is synthesised
by the adapter on process exit, NOT here: the mapper only records the ``result``
marker's ``is_error`` flag into state so the adapter can decide.

Cursor NDJSON event shapes (one JSON object per line):

* system   ``{"type":"system","subtype":"init","session_id":"<uuid>","model":…}``
           — capture ``session_id`` (for ``--resume``); emit nothing.
* user     ``{"type":"user","message":{…},"session_id":…}`` — ignore (emit []).
* assistant``{"type":"assistant","message":{"role":"assistant","content":[
             {"type":"text","text":"<segment>"}]},"session_id":…}`` — each event is
           ONE complete assistant message segment (between tool calls), NOT a
           cumulative snapshot, so emit its text VERBATIM as a ``TextDelta`` (no
           diffing/accumulation); multiple text blocks are concatenated.
* tool_call``{"type":"tool_call","subtype":"started","call_id":"<id>",
             "tool_call":{…}}`` → ``ToolCall`` once per ``call_id``; the
           ``tool_call`` object is one of ``readToolCall`` / ``writeToolCall`` /
           ``function`` — the name is that key (``ToolCall`` suffix stripped) or,
           for ``function``, the function's ``name``.
           ``{"type":"tool_call","subtype":"completed","call_id":"<id>",
             "result":{"success":{…}}}`` → ``ToolResult`` once per ``call_id``.
* result   ``{"type":"result","subtype":"success","is_error":false,…}`` — the
           terminal marker; record ``is_error`` and emit nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
)

#: The suffix Cursor's tool_call sub-object keys carry (``readToolCall`` /
#: ``writeToolCall`` / …); stripped to derive the tool name (``read`` / ``write``).
_TOOL_KEY_SUFFIX = "ToolCall"


@dataclass
class CursorParseState:
    """Carried across the NDJSON lines of one turn."""

    session_id: str | None = None
    #: The terminal ``result`` marker's ``is_error`` flag; the adapter turns this
    #: (plus the exit code) into a ``TurnDone`` or ``TurnError``.
    is_error: bool = False
    terminal_emitted: bool = False
    #: call_id → derived tool name, so a ``completed`` event's ``ToolResult`` can
    #: reuse the name discovered on the ``started`` event.
    tool_names: dict[str, str] = field(default_factory=dict)
    tool_called: set[str] = field(default_factory=set)
    tool_resulted: set[str] = field(default_factory=set)


def _capture_session(state: CursorParseState, obj: dict[str, Any]) -> None:
    if state.session_id is not None:
        return
    cand = obj.get("session_id")
    if isinstance(cand, str) and cand:
        state.session_id = cand


def _derive_tool(tool_call: Any) -> tuple[str, dict[str, Any]]:
    """Best-effort ``(tool_name, tool_input)`` from a cursor ``tool_call`` object.

    The object holds one of ``readToolCall`` / ``writeToolCall`` / ``function``.
    Defensive: returns ``("", {})`` for anything unexpected — never raises.
    """
    if not isinstance(tool_call, dict):
        return ("", {})
    # Look up the known variants explicitly rather than trusting the first key —
    # the object may carry sibling metadata (``type``/``status``/``id``/…) that
    # is not the tool variant.
    func = tool_call.get("function")
    if isinstance(func, dict):
        name = func.get("name")
        name = name if isinstance(name, str) else ""
        args = func.get("arguments")
        if isinstance(args, dict):
            return (name, args)
        if isinstance(args, str):
            try:
                parsed = json.loads(args)
            except ValueError:
                parsed = None
            return (name, parsed if isinstance(parsed, dict) else {})
        return (name, {})
    # readToolCall / writeToolCall / … → the variant key ends with ``ToolCall``.
    for key, sub in tool_call.items():
        if key.endswith(_TOOL_KEY_SUFFIX):
            return (key[: -len(_TOOL_KEY_SUFFIX)], sub if isinstance(sub, dict) else {})
    return ("", {})


def _interpret_result(result: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort ``(output, error)`` from a cursor tool ``result`` object.

    ``{"success": {…}}`` → that dict as the output; ``{"failure": …}`` /
    ``{"error": …}`` → a stringified error. Defensive — never raises.
    """
    if not isinstance(result, dict):
        return ({"result": result}, None)
    if "success" in result:
        success = result["success"]
        return (success if isinstance(success, dict) else {"result": success}, None)
    if "failure" in result:
        return (None, str(result["failure"]))
    if "error" in result:
        return (None, str(result["error"]))
    return (result, None)


def _map_assistant(obj: dict[str, Any]) -> list[AgentEvent]:
    message = obj.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    # Cursor mirrors the Anthropic Messages shape, where ``content`` is legally a
    # bare string OR a list of blocks — handle both, else the whole reply is lost.
    if isinstance(content, str):
        return [TextDelta(text=content)] if content else []
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
    combined = "".join(texts)
    return [TextDelta(text=combined)] if combined else []


def _map_tool_call(obj: dict[str, Any], state: CursorParseState) -> list[AgentEvent]:
    call_id = obj.get("call_id")
    if not isinstance(call_id, str) or not call_id:
        return []
    events: list[AgentEvent] = []
    name, tool_input = _derive_tool(obj.get("tool_call"))
    if name:
        state.tool_names.setdefault(call_id, name)
    # Emit the ToolCall once per call_id — on the ``started`` event, or on a
    # synchronously-``completed`` event that never had a prior ``started``.
    if call_id not in state.tool_called:
        state.tool_called.add(call_id)
        events.append(
            ToolCall(
                tool_use_id=call_id,
                tool_name=state.tool_names.get(call_id, name),
                tool_input=tool_input,
            )
        )
    # Emit the ToolResult once, whenever a result is present — a ``completed``
    # event, or a ``started`` event that already carries its result.
    result = obj.get("result")
    if result is not None and call_id not in state.tool_resulted:
        state.tool_resulted.add(call_id)
        output, error = _interpret_result(result)
        events.append(
            ToolResult(
                tool_use_id=call_id,
                tool_name=state.tool_names.get(call_id, name),
                output=output,
                error=error,
            )
        )
    return events


def map_cursor_event(obj: dict[str, Any], state: CursorParseState) -> list[AgentEvent]:
    """Map one parsed NDJSON line to zero or more ``AgentEvent``s.

    Tolerant of missing/mis-typed fields throughout: an unknown ``type`` or a
    malformed object yields ``[]`` rather than raising.
    """
    _capture_session(state, obj)
    t = obj.get("type")
    if t == "assistant":
        return _map_assistant(obj)
    if t == "tool_call":
        return _map_tool_call(obj, state)
    if t == "result":
        # Error if the boolean flag says so OR the subtype is a non-success value
        # (a ``result`` need not carry a boolean ``is_error``).
        subtype = obj.get("subtype")
        state.is_error = bool(obj.get("is_error")) or (
            isinstance(subtype, str) and subtype not in ("", "success")
        )
        return []
    # system (session captured above) / user / anything else → nothing.
    return []


__all__ = ["CursorParseState", "map_cursor_event"]
