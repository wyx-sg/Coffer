"""The ``NEEDS YOU:`` sentinel (spec channels "Turn a question for the owner
into buttons")."""

from __future__ import annotations

from coffer.application.channel.needs_you import (
    Question,
    extract_question,
    question_buttons,
    reply_text,
)


def test_a_final_needs_you_line_becomes_a_yes_no_question() -> None:
    body, question = extract_question("Preview:\n- live\n\nNEEDS YOU: Apply to checkout-live?")
    assert body == "Preview:\n- live"
    assert question == Question("Apply to checkout-live?", ("Yes", "No"))


def test_options_in_parentheses_or_brackets_are_read() -> None:
    assert extract_question("NEEDS YOU: Which one? (staging / live / cancel)")[1] == Question(
        "Which one?", ("staging", "live", "cancel")
    )
    assert extract_question("**NEEDS YOU:** Go? [yes | no]")[1] == Question("Go?", ("yes", "no"))


def test_more_than_four_options_offer_no_buttons() -> None:
    _, question = extract_question("NEEDS YOU: Pick (a / b / c / d / e)")
    assert question == Question("Pick", ())


def test_a_needs_you_line_that_is_not_last_is_just_text() -> None:
    text = "NEEDS YOU: not really\n\nmore text"
    assert extract_question(text) == (text, None)


def test_a_button_carries_its_answer_within_the_callback_budget() -> None:
    [button] = question_buttons(Question("q", ("é" * 60,)))
    assert button.label == "é" * 60
    assert len(button.value.encode("utf-8")) <= 64
    assert reply_text(button.value) == button.value.removeprefix("reply:")
    assert reply_text("model:x") is None
    assert reply_text("reply:  ") is None
