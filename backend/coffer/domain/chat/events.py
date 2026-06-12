"""AgentEvent union — typed events streamed by an AgentAdapter during a turn.

Each class carries a ``type`` discriminator whose value is reused verbatim as
the SSE event name on the wire:

  TurnStarted      → ``turn_start``
  TextDelta        → ``text_delta``
  ToolCall         → ``tool_call``
  ToolResult       → ``tool_result``
  ApprovalRequest  → ``approval_request``
  TurnDone         → ``turn_done``
  TurnError        → ``turn_error``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class TurnStarted:
    """Emitted immediately when the agent loop starts processing a turn."""

    type: Literal["turn_start"] = "turn_start"


@dataclass(frozen=True)
class TextDelta:
    """A chunk of assistant text, streamed incrementally."""

    text: str
    type: Literal["text_delta"] = "text_delta"


@dataclass(frozen=True)
class ToolCall:
    """The agent has requested a tool invocation."""

    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]
    type: Literal["tool_call"] = "tool_call"


@dataclass(frozen=True)
class ToolResult:
    """The result (or error) for a prior ``ToolCall``."""

    tool_use_id: str
    tool_name: str
    output: dict[str, Any] | None
    error: str | None
    type: Literal["tool_result"] = "tool_result"


@dataclass(frozen=True)
class ApprovalRequest:
    """The agent is asking the user to allow or deny a tool call before it runs.

    The turn pauses after this event until a decision is delivered through the
    approval channel (``ApprovalGate``). ``request_id`` correlates the decision
    with this request. Coffer's built-in agent does not emit this event; it is
    a platform capability for any agent that requires per-call approval.
    """

    request_id: str
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]
    type: Literal["approval_request"] = "approval_request"


@dataclass(frozen=True)
class TurnDone:
    """The turn completed.

    ``stop_reason`` is a short token describing why the turn ended — e.g.
    ``"end_turn"`` (normal completion), ``"max_iterations"`` (the tool-step
    limit was reached), or ``"interrupted"`` (the user stopped the turn).
    Token counts may be ``None`` if the agent does not report them.
    """

    prompt_tokens: int | None
    completion_tokens: int | None
    stop_reason: str
    type: Literal["turn_done"] = "turn_done"


@dataclass(frozen=True)
class TurnError:
    """The turn failed — e.g. credential error, provider timeout, tool limit hit."""

    code: str
    message: str
    type: Literal["turn_error"] = "turn_error"


AgentEvent = (
    TurnStarted | TextDelta | ToolCall | ToolResult | ApprovalRequest | TurnDone | TurnError
)
