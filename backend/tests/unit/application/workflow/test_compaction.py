"""Compacting one node's own conversation (FR-049)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from coffer.application.workflow.compaction import (
    COMPACTION_SUMMARY_PREFIX,
    CONVERSATION_TOKEN_BUDGET,
    ConversationCompactor,
)
from coffer.application.workflow.transcripts import TranscriptMessage

from .fakes import FakeSummariser


class FakeConversations:
    def __init__(self, messages: Sequence[TranscriptMessage] = ()) -> None:
        self.messages = list(messages)
        self.compactions: list[tuple[str, int, str]] = []

    async def transcript(self, conversation_id: str) -> Sequence[TranscriptMessage]:
        return list(self.messages)

    async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None:
        self.compactions.append((conversation_id, keep_last, summary))


def turns(count: int, *, chars: int = 40_000) -> list[TranscriptMessage]:
    return [
        TranscriptMessage(role="assistant", text=f"turn {index} " + "x" * chars)
        for index in range(count)
    ]


async def test_a_conversation_inside_its_budget_is_left_alone() -> None:
    conversations = FakeConversations(turns(2, chars=100))
    compactor = ConversationCompactor(
        conversations=conversations, summariser=FakeSummariser("never asked")
    )

    result = await compactor.compact("conv-1")

    assert not result.applied
    assert result.skipped_reason is None
    assert conversations.compactions == []


@pytest.mark.acceptance(
    spec="workflow", scenario="a long conversation is compacted rather than truncated"
)
async def test_the_oldest_turns_become_a_summary_that_stays_in_the_conversation() -> None:
    conversations = FakeConversations(turns(20))
    summariser = FakeSummariser("Wrote td.md, ran the tests, one is still red.")
    compactor = ConversationCompactor(conversations=conversations, summariser=summariser)

    result = await compactor.compact("conv-1")

    assert result.applied
    assert result.compacted + result.kept == 20
    assert result.kept >= 1
    [(conversation_id, keep_last, summary)] = conversations.compactions
    assert conversation_id == "conv-1"
    assert keep_last == result.kept
    # The summary STAYS — it is a message the conversation keeps, not a
    # truncation, and it announces itself as one.
    assert summary.startswith(COMPACTION_SUMMARY_PREFIX)
    assert "Wrote td.md" in summary
    # What it summarised is what it replaced, oldest first.
    assert "turn 0" in summariser.asked[0]


@pytest.mark.acceptance(
    spec="workflow", scenario="a long conversation is compacted rather than truncated"
)
async def test_with_no_internal_connection_nothing_is_removed_and_the_reason_is_reported() -> None:
    conversations = FakeConversations(turns(20))
    compactor = ConversationCompactor(conversations=conversations, summariser=FakeSummariser(None))

    result = await compactor.compact("conv-1")

    assert not result.applied
    assert result.skipped_reason is not None
    assert "no internal model connection" in result.skipped_reason
    # FR-049's whole point: a conversation that cannot be compacted keeps every
    # turn rather than losing the oldest ones silently.
    assert conversations.compactions == []


async def test_a_summariser_that_raises_leaves_the_conversation_intact() -> None:
    class Exploding:
        async def summarise(self, text: str, *, hint: str) -> str | None:
            raise RuntimeError("model unreachable")

    conversations = FakeConversations(turns(20))
    compactor = ConversationCompactor(conversations=conversations, summariser=Exploding())

    result = await compactor.compact("conv-1")

    assert not result.applied
    assert conversations.compactions == []


async def test_one_enormous_turn_is_not_compacted_away() -> None:
    # Nothing here is OLD; compacting would mean deleting what was just said.
    conversations = FakeConversations([TranscriptMessage(role="user", text="x" * 2_000_000)])
    compactor = ConversationCompactor(
        conversations=conversations, summariser=FakeSummariser("nope")
    )

    result = await compactor.compact("conv-1")

    assert not result.applied
    assert result.skipped_reason == "the newest turns alone exceed the budget"
    assert conversations.compactions == []


async def test_the_conversation_budget_leaves_room_for_the_work_as_well_as_the_brief() -> None:
    from coffer.application.workflow.context_budget import NODE_CONTEXT_TOKEN_BUDGET

    assert CONVERSATION_TOKEN_BUDGET > NODE_CONTEXT_TOKEN_BUDGET
