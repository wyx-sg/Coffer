"""Translate opencode ``run --format json`` part events into Coffer AgentEvents.

Pure mapping over parsed JSON lines — unit-tested with fixtures derived from
opencode's OpenAPI ``Part`` schema and its on-disk ``part`` rows (see
:mod:`opencode_run` for the framing caveat). The terminal ``TurnDone`` /
``TurnError`` is synthesised by the adapter on process exit, NOT here: one turn
may contain many ``step-finish`` parts (an agentic loop), so a step finishing is
not the turn finishing.

Real part shapes (from opencode's ``part`` store):
  * text        ``{"type": "text", "text": "hi"}``
  * tool        ``{"type": "tool", "tool": "webfetch", "callID": "call_…",
                   "state": {"status": "completed", "input": {…}, "output": "…"}}``
  * step-finish ``{"type": "step-finish", "reason": "stop",
                   "tokens": {"input": …, "output": …, …}}``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coffer.domain.chat.events import (
    AgentEvent,
    TextDelta,
    ToolCall,
    ToolResult,
)

#: opencode tool ``state.status`` values that mean the call has started (so a
#: ``ToolCall`` can be emitted) and, separately, has finished (so a ``ToolResult``
#: can be emitted).
_STARTED = frozenset({"running", "completed", "error"})
_FINISHED = frozenset({"completed", "error"})


@dataclass
class OpencodeParseState:
    """Carried across the lines of one turn."""

    session_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False
    #: per text-part id → chars already emitted. opencode updates a text part in
    #: place with the FULL text so far; tracking the emitted length turns each
    #: update into a true incremental ``TextDelta`` (and a single final emit into
    #: the whole string).
    text_emitted: dict[str, int] = field(default_factory=dict)
    tool_called: set[str] = field(default_factory=set)
    tool_resulted: set[str] = field(default_factory=set)


def _inner_part(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Return the message ``Part`` carried by one stdout line, or ``None``.

    Tolerates both a raw part (``{"type": "text", …}``) and a
    ``message.part.updated`` / ``message.part.delta`` event envelope
    (``{"type": "message.part.updated", "properties": {"part": {…}}}``).
    """
    t = obj.get("type")
    if t in ("message.part.updated", "message.part.delta", "message.part.removed"):
        props = obj.get("properties")
        part = props.get("part") if isinstance(props, dict) else None
        return part if isinstance(part, dict) else None
    return obj if isinstance(t, str) else None


def _capture_session(state: OpencodeParseState, obj: dict[str, Any], part: dict[str, Any]) -> None:
    if state.session_id is not None:
        return
    sid = part.get("sessionID") or obj.get("sessionID")
    if isinstance(sid, str) and sid:
        state.session_id = sid


def _accumulate_tokens(state: OpencodeParseState, part: dict[str, Any]) -> None:
    tokens = part.get("tokens")
    if not isinstance(tokens, dict):
        return
    inp = tokens.get("input")
    out = tokens.get("output")
    if isinstance(inp, int):
        # A step's input ≈ the turn's prompt size; the last step wins.
        state.prompt_tokens = inp
    if isinstance(out, int):
        state.completion_tokens = (state.completion_tokens or 0) + out


def _map_tool(part: dict[str, Any], state: OpencodeParseState) -> list[AgentEvent]:
    call_id = part.get("callID")
    name = part.get("tool")
    if not isinstance(call_id, str) or not isinstance(name, str):
        return []
    tool_state = part.get("state")
    tool_state = tool_state if isinstance(tool_state, dict) else {}
    status = tool_state.get("status")
    events: list[AgentEvent] = []
    if status in _STARTED and call_id not in state.tool_called:
        state.tool_called.add(call_id)
        tool_input = tool_state.get("input")
        events.append(
            ToolCall(
                tool_use_id=call_id,
                tool_name=name,
                tool_input=tool_input if isinstance(tool_input, dict) else {},
            )
        )
    if status in _FINISHED and call_id not in state.tool_resulted:
        state.tool_resulted.add(call_id)
        output = tool_state.get("output")
        error = tool_state.get("error")
        result_output: dict[str, Any] | None
        if isinstance(output, dict):
            result_output = output
        elif isinstance(output, str):
            result_output = {"output": output}
        else:
            result_output = None
        events.append(
            ToolResult(
                tool_use_id=call_id,
                tool_name=name,
                output=result_output,
                error=str(error) if error else None,
            )
        )
    return events


def map_opencode_event(obj: dict[str, Any], state: OpencodeParseState) -> list[AgentEvent]:
    """Map one parsed stdout line to zero or more ``AgentEvent``s."""
    part = _inner_part(obj)
    if part is None:
        return []
    _capture_session(state, obj, part)

    ptype = part.get("type")
    if ptype == "text":
        if part.get("synthetic") or part.get("ignored"):
            return []
        text = part.get("text")
        if not isinstance(text, str) or not text:
            return []
        pid = str(part.get("id") or "_")
        prev = state.text_emitted.get(pid, 0)
        if len(text) <= prev:
            return []
        state.text_emitted[pid] = len(text)
        return [TextDelta(text=text[prev:])]

    if ptype == "tool":
        return _map_tool(part, state)

    if ptype == "step-finish":
        _accumulate_tokens(state, part)
        return []

    # step-start / reasoning / snapshot / patch / retry / … carry nothing the
    # chat surface renders as its own event.
    return []


__all__ = ["OpencodeParseState", "map_opencode_event"]
