"""A question as a card: its text, its buttons, its callback payload and the line
it is rewritten to (spec channels
"Ask the owner in the chat and take the chat's answer back to the agent")."""

from __future__ import annotations

import re

import pytest

from coffer.application.channel.question_card import (
    card_body,
    card_buttons,
    closed_body,
    closed_line,
    parse_callback,
    question_ping,
)
from coffer.application.channel.turn_status import format_elapsed
from coffer.domain.chat.question import QuestionAnswer, QuestionBlock, parse_ask_input

_ASK = {
    "context": "```diff\n- a: 2\n+ a: 3\n```",
    "questions": [
        {
            "header": "Apply",
            "question": "Apply this change to staging?",
            "options": [{"label": "Yes"}, {"label": "No"}],
        },
        {
            "header": "Parts",
            "question": "Which parts?",
            "multi_select": True,
            "options": [
                {"label": "api", "description": "the HTTP layer"},
                {"label": "web"},
                {"label": "docs"},
            ],
        },
    ],
}


def _block() -> QuestionBlock:
    context, specs = parse_ask_input(_ASK)
    return QuestionBlock(question_id="q" * 32, questions=specs, context=context)


@pytest.mark.acceptance(
    spec="channels", scenario="a question with described options lists them in the card"
)
def test_the_card_holds_context_question_described_options_and_footer() -> None:
    block = _block()

    first = card_body(block, 0)
    assert first == (
        "```diff\n- a: 2\n+ a: 3\n```\n\n❓ Apply this change to staging?\n\n"
        "Or reply with your answer."
    )
    # Context rides on the first card only; descriptions list when any option has one.
    second = card_body(block, 1)
    assert second == (
        "❓ Which parts?\n\n• api — the HTTP layer\n• web\n• docs\n\nOr reply with your answer."
    )


def test_buttons_are_equal_one_to_a_line_and_multi_select_ticks_and_submits() -> None:
    block = _block()

    single = card_buttons(block, 0)
    assert [b.label for b in single] == ["Yes", "No"]
    assert all(b.own_row and not b.selected for b in single)

    multi = card_buttons(block, 1, {0, 2})
    assert [b.label for b in multi] == ["✓ api", "web", "✓ docs", "Submit"]


def test_a_callback_fits_telegrams_budget_and_round_trips() -> None:
    block = _block()
    for question in range(2):
        for button in card_buttons(block, question):
            assert len(button.value.encode()) <= 64
    tap = parse_callback(card_buttons(block, 1)[2].value)
    assert (tap.question_id, tap.index, tap.option) == ("q" * 32, 1, 2)
    submit = parse_callback(card_buttons(block, 1)[3].value)
    assert submit is not None and submit.option is None
    assert parse_callback("reply:yes") is None
    assert parse_callback("ask:broken") is None


def test_without_buttons_the_options_are_listed_and_the_reply_is_typed() -> None:
    assert card_body(_block(), 0, buttons=False) == (
        "```diff\n- a: 2\n+ a: 3\n```\n\n❓ Apply this change to staging?\n\n"
        "• Yes\n• No\n\nReply with your answer."
    )


def test_the_closed_line_says_where_and_when_or_that_it_stopped() -> None:
    answer = QuestionAnswer(header="Apply", selected=("Yes",))
    assert re.fullmatch(
        r"✓ Answered: Yes · \d\d:\d\d",
        closed_line(answer, web=False, moment="2026-10-03T11:42:00+00:00"),
    )
    assert re.fullmatch(
        r"✓ Answered in Coffer: Yes · \d\d:\d\d", closed_line(answer, web=True, moment=None)
    )
    text = QuestionAnswer(header="Apply", text="only the replica")
    assert closed_line(text, web=False, moment=None).startswith("✓ Answered: only the replica · ")
    both = QuestionAnswer(header="Parts", selected=("api", "web"))
    assert closed_line(both, web=False, moment=None).startswith("✓ Answered: api, web · ")
    assert closed_line(None, web=False, moment=None) == "⏹ Stopped"


def test_a_closed_card_keeps_what_it_asked_and_drops_the_buttons_and_footer() -> None:
    body = closed_body(_block(), 0, "✓ Answered: Yes · 11:42")
    assert body == (
        "```diff\n- a: 2\n+ a: 3\n```\n\nApply this change to staging?\n\n✓ Answered: Yes · 11:42"
    )


def test_the_ping_reads_needs_you_with_the_elapsed_time() -> None:
    assert question_ping(format_elapsed(48), "Apply?") == "❓ Needs you · 48s — Apply?"
    assert question_ping(format_elapsed(65), "Apply?") == "❓ Needs you · 1m 05s — Apply?"
