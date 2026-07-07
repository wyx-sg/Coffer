"""Translate opencode ``run --format json`` part events into Coffer AgentEvents.

Pure mapping over parsed JSON lines — unit-tested with fixtures derived from
opencode's OpenAPI ``Part`` schema and its on-disk ``part`` rows (see
:mod:`opencode_run` for the framing caveat). The terminal ``TurnDone`` /
``TurnError`` is synthesised by the adapter on process exit, NOT here: one turn
may contain many ``step-finish`` parts (an agentic loop), so a step finishing is
not the turn finishing.

Two text-framing conventions are handled because the exact ``run --format json``
framing could not be captured live (opencode's model calls hang in the sandbox):

* **cumulative** — a raw ``{"type":"text",...}`` part or a ``message.part.updated``
  envelope carries the FULL text so far; we diff against the emitted length to
  produce an incremental ``TextDelta``. (Confirmed by opencode's on-disk ``part``
  store, which holds the whole text.)
* **incremental** — a ``message.part.delta`` envelope is assumed to carry a text
  CHUNK to append verbatim (the ``delta`` name); we emit it directly without
  diffing, so an incremental stream is not collapsed to its first character.

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

#: opencode session ids are prefixed ``ses`` (e.g. ``ses_1e84…``). Guarding on the
#: prefix means a stray ``messageID`` / ``id`` field can never be mistaken for the
#: session id when we widen the capture net.
_SESSION_PREFIX = "ses"


@dataclass
class OpencodeParseState:
    """Carried across the lines of one turn."""

    session_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    terminal_emitted: bool = False
    #: per text-part id → chars already emitted (for the CUMULATIVE convention).
    #: opencode updates a text part in place with the full text so far; tracking
    #: the emitted length turns each update into a true incremental ``TextDelta``.
    text_emitted: dict[str, int] = field(default_factory=dict)
    tool_called: set[str] = field(default_factory=set)
    tool_resulted: set[str] = field(default_factory=set)


def _classify(obj: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    """Return ``(inner_part, is_incremental_text)`` for one stdout line.

    Tolerates a raw part (``{"type": "text", …}``, cumulative), a
    ``message.part.updated`` / ``message.part.removed`` envelope (cumulative), and
    a ``message.part.delta`` envelope (incremental text chunk). ``(None, _)`` for
    lines that carry no part.
    """
    t = obj.get("type")
    if t in ("message.part.updated", "message.part.removed", "message.part.delta"):
        props = obj.get("properties")
        props = props if isinstance(props, dict) else {}
        part = props.get("part")
        if not isinstance(part, dict):
            # A delta envelope may carry the chunk fields directly in properties.
            part = props if props.get("text") is not None else None
        return (part if isinstance(part, dict) else None, t == "message.part.delta")
    return (obj if isinstance(t, str) else None, False)


def _capture_session(state: OpencodeParseState, obj: dict[str, Any], part: dict[str, Any]) -> None:
    if state.session_id is not None:
        return
    props = obj.get("properties")
    props = props if isinstance(props, dict) else {}
    info = props.get("info")
    info = info if isinstance(info, dict) else {}
    # Check the part, the envelope, its properties, and a session.* info object;
    # only accept a value that looks like a session id (``ses`` prefix).
    for cand in (
        part.get("sessionID"),
        obj.get("sessionID"),
        props.get("sessionID"),
        info.get("id"),
    ):
        if isinstance(cand, str) and cand.startswith(_SESSION_PREFIX):
            state.session_id = cand
            return


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
    tool_input = tool_state.get("input")
    events: list[AgentEvent] = []
    # Emit the call only once the input is available, so a bare ``running`` update
    # that precedes the args doesn't fix an empty ``{}`` input in place.
    if status in _STARTED and call_id not in state.tool_called and isinstance(tool_input, dict):
        state.tool_called.add(call_id)
        events.append(ToolCall(tool_use_id=call_id, tool_name=name, tool_input=tool_input))
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
    part, incremental = _classify(obj)
    if part is None:
        return []
    _capture_session(state, obj, part)

    ptype = part.get("type")
    # A delta envelope has no part-``type`` when its chunk sits directly in
    # properties; treat a text-bearing incremental part as text regardless.
    if ptype == "text" or (incremental and isinstance(part.get("text"), str)):
        if part.get("synthetic") or part.get("ignored"):
            return []
        text = part.get("text")
        if not isinstance(text, str) or not text:
            return []
        if incremental:
            # A ``.delta`` chunk is appended verbatim — no diffing.
            return [TextDelta(text=text)]
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
