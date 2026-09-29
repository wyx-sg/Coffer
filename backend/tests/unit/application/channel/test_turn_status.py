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
def test_the_block_shows_time_steps_and_only_the_newest_three() -> None:
    status = TurnStatus(started=100.0)
    for i in range(7):
        status.call(f"t{i}", "Bash", {"description": f"step {i}"})
        status.result(f"t{i}", "Bash", error=i == 2)
    status.call("t7", "Grep", {"pattern": "retry"})

    block = status.block(234.0).splitlines()

    assert block[0] == "⏳ Working · 2m 14s · 8 steps (1 failed)"
    assert block[1] == "+5 earlier"
    assert block[2:] == ["✅ Bash · step 5", "✅ Bash · step 6", "⏳ Grep · retry"]


@pytest.mark.acceptance(spec="channels", scenario="hiding steps keeps only the header")
def test_hiding_steps_keeps_the_header_and_the_narration() -> None:
    status = TurnStatus(started=0.0, show_steps=False)
    status.call("t1", "Read", {"file_path": "/a/b/spec.ts"})
    status.narrate("Let me look at the spec.")

    assert status.block(5.0) == "⏳ Working · 5s · 1 step\n💬 Let me look at the spec."


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
    assert reply.full() == "Let me check.\n\nFound it."


def test_a_snapshot_splits_into_its_block_and_its_answer() -> None:
    assert split_snapshot("⏳ Working · 3s\n─\nthe answer") == ("⏳ Working · 3s", "the answer")
    assert split_snapshot("⏳ Working · 3s") == ("⏳ Working · 3s", "")
