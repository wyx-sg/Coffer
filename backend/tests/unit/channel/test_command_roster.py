"""The command roster is the single source for the help text, the dispatch
switch, the typo guard and the platform's command menus (spec channels
"Register the bot's command menu and profile from one roster", "Pass
unreserved slash text to the agent")."""

from __future__ import annotations

import pytest

from coffer.application.channel.selection_cards import model_card
from coffer.domain.channel.commands import (
    COMMAND_ROSTER,
    command_name,
    help_text,
    is_dm_only,
    is_group_private,
    menu_entries,
    names,
    near_miss,
)

_ALL = {"new", "stop", "model", "dir", "status", "resume", "thread", "del", "help"}


@pytest.mark.acceptance(
    spec="channels", scenario="the command menu matches the commands that exist"
)
def test_the_menu_offers_exactly_the_reserved_words() -> None:
    assert {c.name for c in menu_entries(group=False)} == _ALL
    assert {c.name for c in COMMAND_ROSTER} == _ALL
    # Removed with no pointer: they are ordinary words now.
    for gone in ("agent", "effort", "threads", "save"):
        assert command_name(f"/{gone}") is None


def test_a_group_menu_offers_the_group_set() -> None:
    group = {c.name for c in menu_entries(group=True)}
    assert group == {"new", "stop", "del", "help"}


def test_a_group_help_lists_only_the_group_commands() -> None:
    assert help_text(group=True).splitlines()[0] == "/new [agent] · /stop · /del · /help"
    assert "/model" in help_text() and "/thread" in help_text()


def test_the_direct_chat_commands_are_dm_only() -> None:
    for command in ("/model", "/dir", "/status", "/resume", "/thread", "/Model opus"):
        assert is_dm_only(command)
    for command in ("/new", "/stop", "/help", "/start", "/compact"):
        assert not is_dm_only(command)


def test_help_text_lists_every_command_with_its_arguments() -> None:
    rendered = help_text()
    for command in COMMAND_ROSTER:
        assert f"/{command.name}" in rendered
    assert rendered.startswith("/new [agent] · /stop · /model [name] · ")
    assert rendered.splitlines()[-1] == "Anything else is a message to the agent."


def test_names_returns_typed_forms() -> None:
    assert names() == {f"/{n}" for n in _ALL}


def test_start_is_a_hidden_alias_of_help() -> None:
    assert command_name("/start") == "help"
    assert "start" not in {c.name for c in COMMAND_ROSTER}


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("/Model opus", "model"),
        ("/new codex", "new"),
        ("/compact", None),
        ("/Users/me/app crashes", None),
        ("hello /new", None),
    ],
)
def test_only_a_reserved_first_word_is_a_command(text: str, name: str | None) -> None:
    assert command_name(text) == name


@pytest.mark.parametrize(
    ("text", "guess"),
    [("/stpo", "stop"), ("/stat", "status"), ("/threads", "thread"), ("/compact", None)],
)
def test_a_near_miss_is_named(text: str, guess: str | None) -> None:
    assert near_miss(text) == guess


@pytest.mark.parametrize(
    ("command", "private"),
    [
        ("/status", True),
        ("/help", True),
        ("/model", True),
        ("/Model opus", True),
        ("/dir", True),
        ("/resume", True),
        ("/new", False),
        ("/stop", False),
        # Direct-chat commands answer a group privately (their notice).
        ("/thread", True),
    ],
)
def test_group_private_marks_the_asker_only_commands(command: str, private: bool) -> None:
    assert is_group_private(command) is private


def test_a_near_miss_is_group_private() -> None:
    # A "Did you mean" correction is the least useful thing to broadcast.
    assert is_group_private("/stpo") is True


def test_menu_descriptions_fit_the_platform_limit() -> None:
    for entry in COMMAND_ROSTER:
        assert 1 <= len(entry.name) <= 32
        assert entry.name == entry.name.lower()
        assert 1 <= len(entry.description) <= 256
        assert 1 <= len(entry.description_zh) <= 256


def test_the_current_model_is_marked_selected_on_its_card() -> None:
    card = model_card(current="opus", picks=["opus", "sonnet"])
    assert [b.value for b in card.buttons if b.selected] == ["model:opus"]
