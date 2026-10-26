"""Questions an agent asks the owner mid-turn (spec chat "Pause a turn on a
question for the owner").

Process-global, like :mod:`turn_state`: a pending question lives exactly as long
as the turn that asked it, so it is held in memory — the daemon going down ends
the turn and with it every question. What is persisted is the ``question`` block
inside the reply (the turn's content folds the events below).

Flow. A turn registers a **turn token** (``register_turn``) which the adapter
puts into its agent process's environment as ``COFFER_TURN_TOKEN``. The agent
asks through ``coffer__ask`` (the gateway calls :meth:`QuestionService.ask`) or
through Claude Code's ``AskUserQuestion`` (the adapter's ``can_use_tool`` calls
``ask_owner``); both end in :func:`raise_question`, which publishes
``QuestionAsked`` on the turn and blocks until the question is answered, cancelled
or 24 hours pass. A turn that finishes while its question is still open leaves it
open (``close_turn(keep_open=True)``): the question outlives the turn and its
answer becomes the conversation's next message (spec chat "Keep a question open
past the turn that asked it"). :func:`answer_question` is the one place an answer is taken —
the channels call it — and the first answer wins: it is
a synchronous check-and-set, so a second one finds the question closed and gets
``QuestionClosed``.

API for other kinds (the channels' turn renderer)::

    add_raised_listener(cb)    # cb(conversation_id, block): a question was raised
    add_progress_listener(cb)  # cb(conversation_id, block): one of several answered
    add_closed_listener(cb)    # cb(conversation_id, block): answered in full, or cancelled
    pending_question_for(conversation_id) -> QuestionBlock | None
    answer_question(conversation_id, question_id, answers, via=<channel uid>, by=<name>)
    answer_pending_with_text(conversation_id, text, via=, by=)   # text-as-answer routing
    cancel_conversation_questions(conversation_id)

Listeners are synchronous callables and must not raise; one that fails is
logged and skipped.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from coffer.application.chat.question_listeners import (
    add_closed_listener,
    add_progress_listener,
    add_raised_listener,
    clear_listeners,
    notify_closed,
    notify_progress,
    notify_raised,
)
from coffer.application.chat.question_turns import (
    _TURN_BY_CONVERSATION,
    _TURNS,
    TurnContext,
    register_turn,
    token_for,
    turn_env,
    turn_is_live,
)
from coffer.domain.chat.errors import QuestionAnswerInvalid, QuestionClosed
from coffer.domain.chat.events import (
    AgentEvent,
    QuestionAsked,
)
from coffer.domain.chat.events import (
    QuestionClosed as QuestionClosedEvent,
)
from coffer.domain.chat.question import (
    QuestionAnswer,
    QuestionBlock,
    check_answer,
    parse_ask_input,
)

log = logging.getLogger(__name__)

#: How long a question waits before it is given up on.
EXPIRY_SECONDS = 24 * 60 * 60

MSG_STOPPED = "The owner stopped the task."
MSG_NO_ANSWER = "The owner did not answer."
MSG_EXPIRED = "No answer: the owner did not answer within 24 hours."
MSG_TURN_ENDED = (
    "The turn ended before the owner answered. The question stays open; their "
    "answer will arrive as the next message."
)


@dataclass
class _Pending:
    block: QuestionBlock
    ctx: TurnContext
    closed: asyncio.Future[QuestionBlock]
    message: str = MSG_NO_ANSWER
    #: The turn that asked has finished; the question waits on without it.
    outlived: bool = False
    asked_at: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class AnswerInput:
    """One answer as the owner gave it."""

    selected: Sequence[str] = ()
    text: str | None = None


@dataclass(frozen=True)
class QuestionOutcome:
    """How a raised question ended."""

    answered: bool
    block: QuestionBlock
    #: What to tell the agent when nothing was answered.
    message: str = ""


_PENDING: dict[str, _Pending] = {}


# ---------------------------------------------------------------------------
# Turn registry
# ---------------------------------------------------------------------------


def release_turn(ctx: TurnContext) -> None:
    """End the turn's registration and cancel its pending questions, without
    publishing (the synchronous last resort; :func:`close_turn` publishes). A
    question that outlived the turn stays."""
    for pending in [p for p in _PENDING.values() if p.ctx is ctx and not p.outlived]:
        _finish(pending, "cancelled", MSG_STOPPED)
    _TURNS.pop(ctx.token, None)
    if _TURN_BY_CONVERSATION.get(ctx.conversation_id) is ctx:
        del _TURN_BY_CONVERSATION[ctx.conversation_id]


async def close_turn(ctx: TurnContext, *, keep_open: bool = False) -> None:
    """The turn is ending: cancel its pending questions (publishing each
    ``QuestionClosed``) and unregister the token. ``keep_open`` (the turn
    finished on its own, not stopped or failed): they stay open instead, and
    whatever still awaits one is told the turn ended."""
    for pending in [p for p in _PENDING.values() if p.ctx is ctx]:
        if keep_open:
            pending.outlived = True
            pending.message = MSG_TURN_ENDED
            if not pending.closed.done():
                pending.closed.set_result(pending.block)
        else:
            await _close(pending, "cancelled", MSG_STOPPED)
    release_turn(ctx)


def clear_all() -> None:
    """Forget everything (test teardown only)."""
    for pending in list(_PENDING.values()):
        _finish(pending, "cancelled", MSG_STOPPED)
    _TURNS.clear()
    _TURN_BY_CONVERSATION.clear()
    _PENDING.clear()
    clear_listeners()


# ---------------------------------------------------------------------------
# Listeners and reads
# ---------------------------------------------------------------------------


def outlived_turn(question_id: str) -> bool:
    """Whether the open question ``question_id`` outlived the turn that asked it,
    so an answer to it has no turn to go back to."""
    pending = _PENDING.get(question_id)
    return pending is not None and pending.outlived


def _expire_outlived() -> None:
    """Give up on questions that outlived their turn by more than a day."""
    now = time.monotonic()
    for pending in [p for p in _PENDING.values() if p.outlived]:
        if now - pending.asked_at > EXPIRY_SECONDS:
            block = _finish(pending, "cancelled", MSG_EXPIRED)
            if block is not None:
                notify_closed(pending.ctx.conversation_id, block)


def pending_question_for(conversation_id: str) -> QuestionBlock | None:
    """The oldest question the conversation is waiting on, if any."""
    _expire_outlived()
    for pending in _PENDING.values():
        if pending.ctx.conversation_id == conversation_id:
            return pending.block
    return None


def needs_you(conversation_id: str) -> bool:
    """Whether a question is waiting on the owner in the conversation."""
    return pending_question_for(conversation_id) is not None


# ---------------------------------------------------------------------------
# Raise / close
# ---------------------------------------------------------------------------


async def _publish(ctx: TurnContext, event: AgentEvent) -> None:
    if ctx.on_event is not None:
        try:
            await ctx.on_event(event)
        except Exception:
            log.warning("publishing a question event failed", exc_info=True)


def _waiting_changed(ctx: TurnContext) -> None:
    if ctx.on_waiting is not None:
        ctx.on_waiting(any(p.ctx is ctx for p in _PENDING.values()))


def _finish(pending: _Pending, status: str, message: str) -> QuestionBlock | None:
    """Synchronous check-and-set: leave the pending state exactly once."""
    if _PENDING.pop(pending.block.question_id, None) is None:
        return None
    if status == "cancelled":
        pending.block = replace(pending.block, status="cancelled")
    pending.message = message
    if not pending.closed.done():
        pending.closed.set_result(pending.block)
    _waiting_changed(pending.ctx)
    return pending.block


async def _close(
    pending: _Pending, status: str, message: str, *, on: TurnContext | None = None
) -> None:
    """Close ``pending`` and say so on its turn (``on``: the live turn instead)."""
    block = _finish(pending, status, message)
    if block is None:
        return
    await _publish(on or pending.ctx, QuestionClosedEvent(question=block))
    notify_closed(pending.ctx.conversation_id, block)


async def raise_question(token: str, arguments: dict[str, Any]) -> QuestionOutcome:
    """Raise the question ``arguments`` describe on the turn ``token`` names and
    wait for it to be answered, cancelled or to expire.

    Raises ``ValueError`` for a malformed ask and ``QuestionClosed``-free:
    an unknown token is a ``ValueError`` too (the caller checks liveness first).
    """
    ctx = _TURNS.get(token)
    if ctx is None:
        raise ValueError("this turn is not running any more")
    context, specs = parse_ask_input(arguments)
    # A new question supersedes one an earlier turn left open: the owner is asked
    # this one now, and its card is closed on the turn that is running.
    for old in [p for p in _PENDING.values() if p.outlived]:
        if old.ctx.conversation_id == ctx.conversation_id:
            await _close(old, "cancelled", MSG_STOPPED, on=ctx)
    block = QuestionBlock(question_id=uuid.uuid4().hex, questions=specs, context=context)
    pending = _Pending(block=block, ctx=ctx, closed=asyncio.get_running_loop().create_future())
    _PENDING[block.question_id] = pending
    _waiting_changed(ctx)
    await _publish(ctx, QuestionAsked(question=block))
    notify_raised(ctx.conversation_id, block)
    try:
        async with asyncio.timeout(EXPIRY_SECONDS):
            final = await asyncio.shield(pending.closed)
    except TimeoutError:
        await _close(pending, "cancelled", MSG_EXPIRED)
        return QuestionOutcome(answered=False, block=pending.block, message=MSG_EXPIRED)
    except asyncio.CancelledError:
        # The agent's call was abandoned (its process died, the call was
        # cancelled): nobody is waiting for the answer any more.
        await asyncio.shield(_close(pending, "cancelled", MSG_NO_ANSWER))
        raise
    return QuestionOutcome(
        answered=final.status == "answered", block=final, message=pending.message
    )


# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------


def _check_in_order(
    block: QuestionBlock, answers: Sequence[AnswerInput]
) -> tuple[QuestionAnswer, ...]:
    remaining = len(block.questions) - block.next_index
    if not answers or len(answers) > remaining:
        raise QuestionAnswerInvalid(f"expected 1 to {remaining} answers, got {len(answers)}")
    return tuple(
        check_answer(block.questions[block.next_index + i], list(a.selected), a.text)
        for i, a in enumerate(answers)
    )


async def answer_question(
    conversation_id: str,
    question_id: str,
    answers: Sequence[AnswerInput],
    *,
    via: str,
    by: str,
    index: int | None = None,
) -> QuestionBlock:
    """Answer the next unanswered question(s) of ``question_id``, in order.

    The first answer wins: a question already answered in full, cancelled, gone
    with its turn, or whose question ``index`` was answered meanwhile raises
    ``QuestionClosed`` and changes nothing. ``via`` is the answering channel's
    uid; ``by`` names who answered. Raises ``QuestionAnswerInvalid`` for an
    answer that does not fit.
    """
    _expire_outlived()
    pending = _PENDING.get(question_id)
    if pending is None or pending.ctx.conversation_id != conversation_id:
        raise QuestionClosed(question_id)
    if index is not None and index != pending.block.next_index:
        raise QuestionClosed(question_id)
    given = _check_in_order(pending.block, answers)
    # From here to the state change there is no await: the check-and-set is atomic.
    block = replace(pending.block, answers=(*pending.block.answers, *given))
    if len(block.answers) < len(block.questions):
        pending.block = block
        await _publish(pending.ctx, QuestionAsked(question=block))
        notify_progress(conversation_id, block)
        return block
    block = replace(
        block,
        status="answered",
        answered_via=via,
        answered_by=by,
        answered_at=datetime.now(tz=UTC).isoformat(),
    )
    pending.block = block
    _finish(pending, "answered", "")
    await _publish(pending.ctx, QuestionClosedEvent(question=block))
    notify_closed(conversation_id, block)
    return block


async def answer_pending_with_text(
    conversation_id: str, text: str, *, via: str, by: str
) -> QuestionBlock | None:
    """Take ``text`` as the "Other" answer of the first unanswered question of
    the conversation's oldest pending question. ``None`` when nothing is pending
    (the caller then treats the text as an ordinary message)."""
    block = pending_question_for(conversation_id)
    if block is None:
        return None
    return await answer_question(
        conversation_id,
        block.question_id,
        [AnswerInput(text=text)],
        via=via,
        by=by,
        index=block.next_index,
    )


async def cancel_conversation_questions(conversation_id: str) -> None:
    """Cancel every pending question of the conversation (it is being deleted)."""
    for pending in [p for p in _PENDING.values() if p.ctx.conversation_id == conversation_id]:
        await _close(pending, "cancelled", MSG_STOPPED)


__all__ = [
    "EXPIRY_SECONDS",
    "AnswerInput",
    "QuestionOutcome",
    "TurnContext",
    "add_closed_listener",
    "add_progress_listener",
    "add_raised_listener",
    "answer_pending_with_text",
    "answer_question",
    "cancel_conversation_questions",
    "clear_all",
    "close_turn",
    "needs_you",
    "outlived_turn",
    "pending_question_for",
    "raise_question",
    "register_turn",
    "release_turn",
    "token_for",
    "turn_env",
    "turn_is_live",
]
