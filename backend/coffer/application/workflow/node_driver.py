"""One node attempt's life: conversation, turn, outcome (FR-019, FR-030).

A node's work is **one ordinary Coffer conversation** — there is no second
agent runtime here. The driver opens it in the run's working directory, starts
one turn with the composed shared context, drains that turn's event queue to
its terminating ``None``, and reports what came out.

It reports rather than writes. Every state change a run has — the attempt's
status, the event appended, the projection — belongs to the node service, which
owns the version check and the event log. The driver is handed three callbacks
and calls exactly one of the outcome pair per attempt, so a run cannot end up
with two places that decide what an attempt did.

Four shapes are worth knowing before reading the code:

* **A ``manual`` node opens no conversation.** Its type says a human does the
  work (``NodeType.MANUAL``), so the driver reports it as ready for the
  developer immediately — no agent, no turn, no tokens.
* **A follow-up is not a new node.** ``NodeDispatch.follow_up`` is more to do on
  the attempt already in flight (FR-021's ``feedback``): it runs a turn on that
  attempt's existing conversation and composes nothing, because the agent
  already has the context and re-sending it would read as a restart.
* **Cancellation is not a failure.** If the daemon is stopping mid-turn the
  driver re-raises rather than reporting, because the attempt genuinely is
  still running; start-up reconciliation is what marks it ``interrupted``
  (FR-027), and reporting a failure here would race it with a worse answer.
* **A long conversation is compacted, not truncated.** Before a turn starts on
  a conversation that already has history, the driver compacts it (FR-049) —
  the oldest turns become a summary that stays in the conversation. It is best
  effort: a conversation that could not be compacted still gets its turn, and
  the compactor says why rather than dropping anything.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.workflow.compaction import ConversationCompactor
from coffer.application.workflow.context_composer import (
    ContextComposer,
    NodeContextRequest,
    parse_inputs,
)
from coffer.application.workflow.dispatch import NodeDispatch
from coffer.application.workflow.ports import TurnPlatformPort
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone, TurnError
from coffer.domain.workflow.run import FailureReason
from coffer.domain.workflow.template import NodeType

__all__ = [
    "MANUAL_NODE_SUMMARY",
    "NodeDriver",
    "OnConversationOpened",
    "OnFailed",
    "OnOutputReady",
]

_logger = logging.getLogger(__name__)

#: What a ``manual`` node reports instead of an agent's reply. It is a summary
#: like any other so the node reaches ``waiting_review`` down the same path as
#: an agent node, and the developer sees a sentence rather than an empty panel.
MANUAL_NODE_SUMMARY = (
    "Manual step — Coffer ran nothing. Do the work, then complete or skip this node."
)

#: The attempt's conversation exists and has been opened. Called *before* the
#: turn starts, which is what makes an interrupted attempt readable: the
#: conversation id is already on the row when the process stops (FR-027).
OnConversationOpened = Callable[[str, str], Awaitable[None]]

#: ``(attempt_id, summary, tokens)`` — the node produced its output and is now
#: the developer's to review.
OnOutputReady = Callable[[str, str, int], Awaitable[None]]

#: ``(attempt_id, reason, detail)`` — the closed-vocabulary reason plus the
#: agent's own words, which are the only thing that tells the developer whether
#: a retry is worth anything.
OnFailed = Callable[[str, FailureReason, str], Awaitable[None]]


@dataclass
class _TurnResult:
    """What draining one turn's queue produced."""

    text: str = ""
    tokens: int = 0
    error: str | None = None


class NodeDriver:
    """Drives one node attempt at a time.

    Satisfies ``dispatch.NodeDispatcher``, so the composition root hands the
    instance itself to the advancer and to the node service.
    """

    def __init__(
        self,
        *,
        platform: TurnPlatformPort,
        composer: ContextComposer,
        compactor: ConversationCompactor,
        on_conversation_opened: OnConversationOpened,
        on_output_ready: OnOutputReady,
        on_failed: OnFailed,
    ) -> None:
        self._platform = platform
        self._composer = composer
        self._compactor = compactor
        self._on_conversation_opened = on_conversation_opened
        self._on_output_ready = on_output_ready
        self._on_failed = on_failed

    async def __call__(self, dispatch: NodeDispatch) -> None:
        """``NodeDispatcher``'s shape, so the seam takes the driver as it is."""
        await self.run(dispatch)

    async def run(self, dispatch: NodeDispatch) -> None:
        """Take one attempt to an outcome.

        Exactly one of ``on_output_ready`` / ``on_failed`` is called, unless the
        driver is cancelled — see the module docstring.
        """
        attempt_id = dispatch.attempt.id
        if dispatch.follow_up is not None:
            await self._follow_up(dispatch)
            return
        if dispatch.node.type is NodeType.MANUAL:
            await self._on_output_ready(attempt_id, MANUAL_NODE_SUMMARY, 0)
            return

        conversation_id = await self._open(dispatch)
        if conversation_id is None:
            return
        opening = await self._compose(dispatch)
        if opening is None:
            return
        await self._run_turn(dispatch, conversation_id, opening)

    # -- the three ways a turn begins ---------------------------------------

    async def _open(self, dispatch: NodeDispatch) -> str | None:
        """Open the attempt's conversation, or report why it could not be."""
        attempt_id = dispatch.attempt.id
        try:
            conversation_id = await self._platform.create_conversation(
                agent_key=dispatch.agent_key,
                cwd=dispatch.workdir,
                # Read verbatim by the gateway to attribute this agent's tool
                # calls back to the run and attempt that caused them (FR-035).
                # The shape is the contract; do not decorate it.
                run_context=f"{dispatch.run.id}/{attempt_id}",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _logger.exception("workflow.node.open_failed", extra={"attempt": attempt_id})
            await self._on_failed(attempt_id, FailureReason.AGENT_ERROR, str(exc))
            return None
        await self._on_conversation_opened(attempt_id, conversation_id)
        return conversation_id

    async def _compose(self, dispatch: NodeDispatch) -> str | None:
        """The shared opening context (FR-029), or a reported failure."""
        attempt_id = dispatch.attempt.id
        try:
            return await self._composer.compose(_request_for(dispatch))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _logger.exception("workflow.node.compose_failed", extra={"attempt": attempt_id})
            await self._on_failed(attempt_id, FailureReason.AGENT_ERROR, str(exc))
            return None

    async def _follow_up(self, dispatch: NodeDispatch) -> None:
        """More to do on the attempt already in flight — same conversation."""
        attempt_id = dispatch.attempt.id
        conversation_id = dispatch.attempt.conversation_id
        if conversation_id is None:
            await self._on_failed(
                attempt_id,
                FailureReason.AGENT_ERROR,
                "this attempt has no conversation to carry the feedback",
            )
            return
        # The only path that starts a turn on a conversation that already has
        # history, and therefore the only one that can be over its share of the
        # budget (FR-049).
        await self._compact(conversation_id)
        await self._run_turn(dispatch, conversation_id, dispatch.follow_up or "")

    async def _compact(self, conversation_id: str) -> None:
        """Bring the conversation back inside its budget, best effort.

        A compaction that could not happen is not a reason to refuse the turn:
        the compactor never drops anything it could not summarise, so the worst
        case here is a conversation that is merely long — and failing the
        attempt over it would cost the developer work that is already done.
        """
        try:
            result = await self._compactor.compact(conversation_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning(
                "workflow.node.compaction_failed",
                extra={"conversation": conversation_id},
                exc_info=True,
            )
            return
        if result.skipped_reason is not None:
            _logger.info(
                "workflow.node.compaction_skipped",
                extra={"conversation": conversation_id, "reason": result.skipped_reason},
            )

    async def _run_turn(self, dispatch: NodeDispatch, conversation_id: str, text: str) -> None:
        """Start one turn and report what draining it produced."""
        attempt_id = dispatch.attempt.id
        try:
            queue = await self._platform.start_turn(conversation_id, text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _logger.exception("workflow.node.start_failed", extra={"attempt": attempt_id})
            await self._on_failed(attempt_id, FailureReason.AGENT_ERROR, str(exc))
            return
        result = await _drain(queue)
        if result.error is not None:
            await self._on_failed(attempt_id, FailureReason.AGENT_ERROR, result.error)
            return
        await self._on_output_ready(attempt_id, result.text.strip(), result.tokens)

    def interrupt(self, conversation_id: str) -> None:
        """Stop the turn in flight — a pause or an abort, nothing else."""
        with contextlib.suppress(Exception):
            self._platform.interrupt(conversation_id)


def _request_for(dispatch: NodeDispatch) -> NodeContextRequest:
    """The composer's question, read off the dispatch and the run row."""
    return NodeContextRequest(
        run_id=dispatch.run.id,
        run_title=dispatch.run.title,
        workdir=dispatch.workdir,
        attempt_id=dispatch.attempt.id,
        node=dispatch.node,
        attempt=dispatch.attempt.attempt,
        inputs=parse_inputs(dispatch.run.inputs),
    )


async def _drain(queue: asyncio.Queue[AgentEvent | None]) -> _TurnResult:
    """Drain one turn's events to the terminating ``None``.

    The assistant's text is accumulated from the deltas — it is the node's
    summary, which is what the developer reviews. Token counts are summed from
    every ``TurnDone``, and an adapter that reports none contributes zero rather
    than making the run's spend a guess (FR-018).

    The first ``TurnError`` wins: a stream that errors and then keeps talking is
    still a turn that failed, and the first reason is the one that explains it.
    """
    result = _TurnResult()
    while True:
        event = await queue.get()
        if event is None:
            return result
        if isinstance(event, TextDelta):
            result.text += event.text
        elif isinstance(event, TurnDone):
            result.tokens += (event.prompt_tokens or 0) + (event.completion_tokens or 0)
        elif isinstance(event, TurnError) and result.error is None:
            result.error = f"{event.code}: {event.message}"
