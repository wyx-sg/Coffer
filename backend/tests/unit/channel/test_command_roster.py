"""The command roster is the single source for the help text and the
platform's command menu (FR-065)."""

from __future__ import annotations

import pytest

from coffer.application.channel.commands import HELP_TEXT
from coffer.domain.channel.commands import (
    COMMAND_ROSTER,
    help_text,
    is_group_private,
    names,
)
from coffer.infrastructure.channel.telegram_profile import menu_commands


@pytest.mark.acceptance(
    spec="channels", scenario="the command menu matches the commands that exist"
)
def test_registered_menu_lists_every_handled_command() -> None:
    registered = {entry["command"] for entry in menu_commands()}
    assert registered == {command.name for command in COMMAND_ROSTER}
    assert "agent" in registered and "model" in registered


def test_help_text_lists_every_command_with_its_arguments() -> None:
    rendered = help_text()
    for command in COMMAND_ROSTER:
        assert f"/{command.name}" in rendered
        assert command.description in rendered
    assert "/agent [key] — Show or switch the agent (opens a fresh conversation)" in rendered


def test_application_help_text_is_the_rendered_roster() -> None:
    # The command handler's HELP_TEXT must BE the roster's rendering, not a
    # second hand-maintained copy that can drift from the menu.
    assert help_text() == HELP_TEXT


def test_names_returns_typed_forms() -> None:
    assert names() == {"/new", "/agent", "/model", "/stop", "/status", "/help"}


@pytest.mark.parametrize(
    ("command", "private"),
    [("/status", True), ("/help", True), ("/agent", True), ("/new", False), ("/stop", False)],
)
def test_group_private_marks_the_asker_only_commands(command: str, private: bool) -> None:
    assert is_group_private(command) is private


def test_unknown_command_is_group_private() -> None:
    # An "unknown command" scolding is the least useful thing to broadcast.
    assert is_group_private("/nope") is True


def test_menu_descriptions_fit_the_platform_limit() -> None:
    for entry in menu_commands():
        assert 1 <= len(str(entry["command"])) <= 32
        assert entry["command"] == str(entry["command"]).lower()
        assert 1 <= len(str(entry["description"])) <= 256


def test_the_current_agent_is_marked_selected_on_its_card() -> None:
    from coffer.application.channel.selection_cards import agent_card

    card = agent_card(current="codex", choices=[("codex", "Codex"), ("claude_code", "Claude")])
    selected = [b for b in card.buttons if b.selected]
    assert [b.value for b in selected] == ["agent:codex"]


def test_the_current_model_is_marked_selected_on_its_card() -> None:
    from coffer.application.channel.selection_cards import model_card

    card = model_card(current="opus", picks=["opus", "sonnet"])
    assert [b.value for b in card.buttons if b.selected] == ["model:opus"]


# -- private answers in a group (FR-064) --------------------------------------


def test_the_asker_only_commands_are_registered_as_ephemeral() -> None:
    by_name = {entry["command"]: entry for entry in menu_commands()}
    # Typing these in a group should not put them in front of everyone.
    assert by_name["status"]["is_ephemeral"] is True
    assert by_name["help"]["is_ephemeral"] is True
    # /new and /stop change shared state and stay visible.
    assert by_name["new"]["is_ephemeral"] is False
    assert by_name["stop"]["is_ephemeral"] is False
