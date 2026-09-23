"""Compacting one node's own conversation (spec workflow "Compact a long
node conversation into a summary").

A node can run for hours. Its opening message is bounded by
``context_budget``, but the turns that follow are not: tool output, a
developer's corrections, a retry's back-and-forth. Left alone the conversation
reaches the point where the next turn cannot start.

The answer is not to truncate. A turn's history is what the agent is reasoning
from, so the oldest turns are **replaced by a summary that stays in the
conversation** — the conversation keeps saying everything it said, more
briefly. What it never does is quietly forget: with no internal connection
configured there is nothing to summarise with, so nothing is removed at all and
the caller is told why. A conversation that is merely too long still runs; a
conversation with a silent hole in it produces work that contradicts what the
developer already decided.

Ordering matters at the seam: the summary is written from the messages that are
about to go, and the replacement is one call, so a process that dies between
reading and writing leaves the conversation exactly as it was.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from coffer.application.workflow.context_budget import (
    NODE_CONTEXT_TOKEN_BUDGET,
    estimate_tokens,
)
from coffer.application.workflow.ports import ConversationPort, SummariserPort
from coffer.application.workflow.transcripts import TranscriptMessage, render_messages

__all__ = [
    "COMPACTION_KEEP_SHARE",
    "COMPACTION_SUMMARY_PREFIX",
    "CONVERSATION_TOKEN_BUDGET",
    "Compaction",
    "ConversationCompactor",
]

_logger = logging.getLogger(__name__)

#: What one node's whole conversation may hold before its oldest turns are
#: compacted.
#:
#: Twice the opening message's budget. The opening message is composed once and
#: costs at most ``NODE_CONTEXT_TOKEN_BUDGET``; the work accumulates on top of
#: it, so a ceiling equal to the message would compact a node that has barely
#: started. Twice it leaves the node as much room for its own turns as its
#: brief cost, and still lands well inside the ~200,000-token window the
#: budget's own comment reasons from — the headroom is deliberate, because one
#: tool call can return more than anything else in the conversation.
CONVERSATION_TOKEN_BUDGET = 2 * NODE_CONTEXT_TOKEN_BUDGET

#: How much of that ceiling survives a compaction as verbatim turns. Half,
#: because compacting down to the ceiling itself would compact again on the
#: very next turn, and a conversation that summarises itself every turn spends
#: more on summarising than on working.
COMPACTION_KEEP_SHARE = 0.5

#: How the summary message announces itself. An agent that reads its own
#: history has to be able to tell a summary of its turns from its turns.
COMPACTION_SUMMARY_PREFIX = (
    "[Coffer compacted this conversation] The earlier turns of this task were replaced by "
    "the summary below to keep the conversation within its context budget. Treat it as your "
    "own earlier work, and say so if you need something it does not carry."
)

_SUMMARY_HINT = (
    "Summarise the earlier turns of one AI coding task so the same agent can carry on from "
    "the summary alone. Keep decisions made, files written, commands run and their outcome, "
    "instructions the developer gave, and anything still unfinished. Drop tool chatter."
)


@dataclass(frozen=True)
class Compaction:
    """What one compaction did, or why it did nothing."""

    #: Messages replaced by the summary. Zero when nothing was compacted.
    compacted: int
    #: Messages left verbatim at the end of the conversation.
    kept: int
    #: Why nothing happened, when nothing did — reported, never swallowed.
    skipped_reason: str | None = None

    @property
    def applied(self) -> bool:
        return self.compacted > 0


class ConversationCompactor:
    """Applies spec workflow "Compact a long node conversation into a
    summary" to one conversation, before a turn starts on it."""

    def __init__(
        self,
        *,
        conversations: ConversationPort,
        summariser: SummariserPort,
        budget: int = CONVERSATION_TOKEN_BUDGET,
        keep_share: float = COMPACTION_KEEP_SHARE,
    ) -> None:
        self._conversations = conversations
        self._summariser = summariser
        self._budget = budget
        self._keep = int(budget * keep_share)

    async def compact(self, conversation_id: str) -> Compaction:
        """Compact ``conversation_id`` if it is over budget; report either way."""
        messages = await self._conversations.transcript(conversation_id)
        if estimate_tokens(render_messages(messages)) <= self._budget:
            return Compaction(compacted=0, kept=len(messages))
        keep_last = _keep_last(messages, self._keep)
        going = messages[: len(messages) - keep_last]
        if not going:
            # Every message is inside the keep window and the conversation is
            # still over budget — one enormous turn. There is nothing OLD to
            # replace, so compacting would mean deleting what was just said.
            return Compaction(
                compacted=0,
                kept=len(messages),
                skipped_reason="the newest turns alone exceed the budget",
            )
        summary = await self._summarise(going)
        if summary is None:
            return Compaction(
                compacted=0,
                kept=len(messages),
                skipped_reason=(
                    "no internal model connection is configured, so the oldest turns were "
                    "left in place rather than dropped"
                ),
            )
        await self._conversations.compact(
            conversation_id,
            keep_last=keep_last,
            summary=f"{COMPACTION_SUMMARY_PREFIX}\n\n{summary.strip()}",
        )
        return Compaction(compacted=len(going), kept=keep_last)

    async def _summarise(self, messages: Sequence[TranscriptMessage]) -> str | None:
        try:
            summary = await self._summariser.summarise(
                render_messages(messages), hint=_SUMMARY_HINT
            )
        except Exception:  # pragma: no cover - the port is allowed to fail loudly
            _logger.warning("workflow.compaction.summarise_failed", exc_info=True)
            return None
        if summary is None or not summary.strip():
            return None
        return summary


def _keep_last(messages: Sequence[TranscriptMessage], allowance: int) -> int:
    """How many of the newest messages fit in ``allowance``, newest first.

    At least one whenever there is one: a conversation compacted down to
    nothing but a summary has lost the turn the agent is answering.
    """
    remaining = allowance
    kept = 0
    for message in reversed(messages):
        cost = estimate_tokens(render_messages([message]))
        if cost > remaining and kept:
            break
        remaining -= cost
        kept += 1
    return kept
