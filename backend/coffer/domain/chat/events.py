"""AgentEvent union — typed events streamed by an AgentAdapter during a turn.

Each class carries a ``type`` discriminator whose value is reused verbatim as
the SSE event name on the wire:

  TurnStarted      → ``turn_start``
  TextDelta        → ``text_delta``
  ToolCall         → ``tool_call``
  ToolResult       → ``tool_result``
  TurnDone         → ``turn_done``
  TurnError        → ``turn_error``
  QueueChanged     → ``queue_changed``
  QuestionAsked    → ``question_asked``
  QuestionClosed   → ``question_closed``

``QueueChanged`` is a conversation-level event (the pending-message queue, spec chat
"Queue messages sent during a turn")
rather than a turn-content event: it is broadcast by the orchestrator, never
emitted by an adapter, and is not accumulated into the assistant message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from coffer.domain.chat.question import QuestionBlock


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
    #: How long the tool ran; stamped by the turn runner, null from an adapter.
    duration_ms: int | None = None
    type: Literal["tool_result"] = "tool_result"


@dataclass(frozen=True)
class TurnDone:
    """The turn completed.

    ``stop_reason`` is a short token describing why the turn ended — e.g.
    ``"end_turn"`` (normal completion) or ``"interrupted"`` (the user stopped the
    turn). A turn the agent cuts short (its own turn limit) arrives as a ``TurnError``.
    Token counts may be ``None`` if the agent does not report them.
    """

    prompt_tokens: int | None
    completion_tokens: int | None
    stop_reason: str
    type: Literal["turn_done"] = "turn_done"


#: ``TurnError.code`` when the agent's event stream ended without a terminal —
#: the process died or its connection dropped mid-turn. Shared by every adapter
#: so a surface can recognise the one failure that is not the agent's own.
STREAM_ENDED = "stream_ended"
STREAM_ENDED_MESSAGE = "the agent stopped responding before finishing the turn"

#: ``TurnError.code`` when the orchestrator's idle watchdog cancelled a turn
#: that produced no event for the configured window (the agent process is
#: then terminated); the partial reply is kept.
TURN_TIMEOUT = "turn_timeout"


@dataclass(frozen=True)
class TurnError:
    """The turn failed — e.g. secret error, provider timeout, tool limit hit.

    ``code`` is a short machine token; :data:`STREAM_ENDED` and
    :data:`TURN_TIMEOUT` are the two the platform itself raises.
    """

    code: str
    message: str
    type: Literal["turn_error"] = "turn_error"


@dataclass(frozen=True)
class QueueChanged:
    """The conversation's pending-message queue changed (spec chat "Express a turn
    as typed events").

    Carries the ordered texts still waiting to run as their own turns, so every
    subscriber renders the same pending state. Conversation-level, not turn
    content — never emitted by an adapter.
    """

    pending: list[str]
    type: Literal["queue_changed"] = "queue_changed"


@dataclass(frozen=True)
class QuestionAsked:
    """The agent asked the owner a question and the turn is waiting (spec chat
    "Pause a turn on a question for the owner"). Carries the pending block;
    sent again, with the same ``question_id``, each time one question of a
    several-question ask is answered and the rest still wait."""

    question: QuestionBlock
    type: Literal["question_asked"] = "question_asked"


@dataclass(frozen=True)
class QuestionClosed:
    """A question left the pending state — answered (in full), or cancelled.
    Carries the block as it now stands."""

    question: QuestionBlock
    type: Literal["question_closed"] = "question_closed"


AgentEvent = (
    TurnStarted
    | TextDelta
    | ToolCall
    | ToolResult
    | TurnDone
    | TurnError
    | QueueChanged
    | QuestionAsked
    | QuestionClosed
)
