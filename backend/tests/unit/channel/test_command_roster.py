"""The command roster is the single source for the help text, the dispatch
switch, the typo guard and the platform's command menus (spec channels
"Register the bot's command menu and profile from one roster", "Pass
unreserved slash text to the agent")."""

from __future__ import annotations

import pytest

from coffer.application.channel.selection_cards import effort_card, model_card
from coffer.domain.channel.commands import (
    COMMAND_ROSTER,
    command_name,
    help_text,
    is_group_private,
    menu_entries,
    names,
    near_miss,
)

_ALL = {"new", "stop", "model", "dir", "status", "resume", "thread", "kb", "help"}


@pytest.mark.acceptance(
    spec="channels", scenario="the command menu matches the commands that exist"
)
def test_the_menu_offers_exactly_the_reserved_words() -> None:
    assert {c.name for c in menu_entries(group=False, knowledge=True)} == _ALL
    assert {c.name for c in COMMAND_ROSTER} == _ALL
    # Removed with no pointer: they are ordinary words now.
    for gone in ("agent", "effort", "threads", "save"):
        assert command_name(f"/{gone}") is None


def test_a_group_menu_offers_the_group_set() -> None:
    group = {c.name for c in menu_entries(group=True, knowledge=True)}
    assert group == {"new", "stop", "model", "status", "resume", "help"}


@pytest.mark.acceptance(spec="channels", scenario="/kb is offered only while knowledge is on")
def test_kb_is_offered_only_while_knowledge_is_on() -> None:
    assert "/kb" in help_text(knowledge=True)
    assert "/kb" not in help_text(knowledge=False)
    assert "kb" not in {c.name for c in menu_entries(group=False, knowledge=False)}
    # Still reserved, so it answers why it cannot run rather than reaching the agent.
    assert command_name("/kb notes") == "kb"


def test_help_text_lists_every_command_with_its_arguments() -> None:
    rendered = help_text()
    for command in COMMAND_ROSTER:
        assert f"/{command.name}" in rendered
        assert command.description in rendered
    assert "/new [agent] — " in rendered
    assert "/model [name] [level] — " in rendered


def test_names_returns_typed_forms() -> None:
    assert names() == {f"/{n}" for n in _ALL}
    assert names(knowledge=False) == {f"/{n}" for n in _ALL - {"kb"}}


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
        # Opening a thread posts into the chat either way.
        ("/thread", False),
        ("/kb", False),
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


def test_the_current_effort_is_marked_selected_on_its_card() -> None:
    card = effort_card(current="xhigh", levels=["low", "high", "xhigh"])
    assert [b.value for b in card.buttons if b.selected] == ["effort:xhigh"]
    # With none pinned the agent's own default is in effect, and nothing is
    # ticked — a card must not claim a choice the conversation has not made.
    assert [b.value for b in effort_card(current=None, levels=["low"]).buttons if b.selected] == []
