"""The hand-off prompt's shape and the rules every hand-off ends with."""

from __future__ import annotations

from coffer.domain.handoff import (
    ASK_BEFORE_SYSTEM_CHANGES,
    NO_CREDENTIALS,
    Handoff,
    render_handoff,
)


def test_task_facts_then_steps_and_the_standing_rules() -> None:
    text = render_handoff(
        Handoff(
            task="Please set up the thing.",
            facts=("It is needed by X.", "  This machine: macOS 15.6, arm64.  "),
            steps=("Pick the right way.", "Confirm it works."),
        )
    )
    assert text == (
        "Please set up the thing.\n"
        "\n"
        "- It is needed by X.\n"
        "- This machine: macOS 15.6, arm64.\n"
        "\n"
        "Pick the right way.\n"
        "Confirm it works.\n"
        f"{ASK_BEFORE_SYSTEM_CHANGES}\n"
        f"{NO_CREDENTIALS}"
    )


def test_no_facts_leaves_no_empty_list_and_rules_are_not_repeated() -> None:
    text = render_handoff(Handoff(task="Do it.", facts=("", " "), steps=(NO_CREDENTIALS,)))
    assert text == f"Do it.\n\n{NO_CREDENTIALS}\n{ASK_BEFORE_SYSTEM_CHANGES}"
