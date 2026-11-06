"""The status block a running turn shows (spec channels "Show a turn's working
state as one status line") — pure formatting, no transport."""

from __future__ import annotations

import pytest

from coffer.application.channel.turn_status import (
    ReplyText,
    TurnStatus,
    format_elapsed,
    split_snapshot,
)


@pytest.mark.parametrize(
    ("seconds", "shown"),
    [(0, "0s"), (45.9, "45s"), (60, "1m 00s"), (134, "2m 14s"), (3725, "1h 02m"), (-3, "0s")],
)
def test_elapsed_time_is_short_enough_for_a_header(seconds: float, shown: str) -> None:
    assert format_elapsed(seconds) == shown


@pytest.mark.acceptance(
    spec="channels",
    scenario="a long turn shows elapsed time and step count in one status line",
)
def test_the_block_shows_time_and_step_count_and_no_step_lines() -> None:
    status = TurnStatus(started=100.0)
    for i in range(7):
        status.call(f"t{i}")
        status.result(f"t{i}", error=i == 2)
    status.call("t7")

    assert status.block(234.0) == "⏳ Working · 2m 14s · 8 steps (1 failed)"


def test_a_turn_with_no_steps_yet_shows_just_the_clock() -> None:
    assert TurnStatus(started=0.0).block(0.0) == "⏳ Working · 0s"


def test_narration_is_the_last_line_clipped() -> None:
    status = TurnStatus(started=0.0)
    status.narrate("First I read it.\n\nNow " + "x" * 200)
    assert status.narration.startswith("Now ") and len(status.narration) == 80


def test_reply_text_joins_deltas_and_breaks_at_tool_boundaries() -> None:
    reply = ReplyText()
    reply.add("Let me ")
    reply.add("check.")
    assert reply.tail == "Let me check."
    assert reply.boundary() == "Let me check."
    assert reply.tail == ""
    reply.add("Found it.")
    assert reply.answer() == "Found it."


def test_the_answer_is_the_text_after_the_last_tool_call() -> None:
    reply = ReplyText()
    reply.add("Let me check the logs.")
    reply.boundary()
    reply.add("Now the deploy.")
    reply.boundary()
    reply.add("The deploy is green.")
    assert reply.answer() == "The deploy is green."


def test_a_turn_that_ends_on_a_tool_call_answers_with_its_last_text() -> None:
    reply = ReplyText()
    reply.add("First look.")
    reply.boundary()
    reply.add("The deploy is green.")
    reply.boundary()  # a tool ran after the last text, and nothing followed it
    reply.boundary()
    assert reply.answer() == "The deploy is green."
    assert ReplyText().answer() == ""


def test_a_snapshot_splits_into_its_block_and_its_answer() -> None:
    assert split_snapshot("⏳ Working · 3s\n─\nthe answer") == ("⏳ Working · 3s", "the answer")
    assert split_snapshot("⏳ Working · 3s") == ("⏳ Working · 3s", "")


def test_narration_the_agent_marked_is_left_out_of_the_answer() -> None:
    reply = ReplyText()
    reply.add("I'll check the sheet first.")
    assert reply.end_message(commentary=True) == "I'll check the sheet first."
    reply.add("The sheet is ready.")
    reply.end_message(commentary=False)
    assert reply.tail == "The sheet is ready."
    assert reply.answer() == "The sheet is ready."


def test_messages_of_one_segment_join_as_paragraphs() -> None:
    reply = ReplyText()
    reply.add("Part one.")
    reply.end_message(commentary=False)
    reply.add("Part two.")
    assert reply.answer() == "Part one.\n\nPart two."


def test_a_turn_of_narration_only_still_replies() -> None:
    reply = ReplyText()
    reply.add("Looking.")
    reply.end_message(commentary=True)
    assert reply.answer() == "Looking."
