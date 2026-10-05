"""The cards that end in actions rather than a list of choices: `/status`,
`/help` and `/new`, and the agent card the `/new` card's Agent button opens
(spec channels "Report the chat's state as a status card", "Offer the commands
as a help card" and "Switch the agent with /new").

Built on the same primitives as ``selection_cards`` — the tick, the pagination
window and the payload cap — so an action card and a choice card can never
disagree about what a button looks like or how a long list is browsed.

Pure functions over already-fetched values.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.application.channel.selection_cards import (
    SelectionCard,
    callback_fits,
    paginate,
    tick,
)
from coffer.domain.channel.commands import help_text, menu_entries
from coffer.domain.channel.envelopes import ChoiceButton

#: The ``agent:`` value of the `/new` card's Agent button: show the agent card
#: rather than switch to anything. No agent key contains ``?``.
PICK_AGENT = "?"

#: The actions a `/status` card offers, as ``(label, command)`` (spec channels
#: "Report the chat's state as a status card"). Stop is offered only while a
#: turn is running.
STATUS_ACTIONS: tuple[tuple[str, str], ...] = (
    ("Stop", "stop"),
    ("New", "new"),
    ("Model", "model"),
    ("Resume", "resume"),
    ("Dir", "dir"),
)


def agent_card(
    *,
    current: str,
    choices: Sequence[tuple[str, str]],
    page: int | None = None,
) -> SelectionCard:
    """Pick the agent a fresh conversation starts with — the `/new` card's Agent
    button (spec channels "Switch the agent with /new"). ``choices`` is
    ``(agent key, display name)`` for the agents the channel may drive; a tap
    carries the key (``agent:<key>``) and runs what `/new <agent>` would."""
    options = [
        ChoiceButton(
            label=tick(display, key == current), value=f"agent:{key}", selected=key == current
        )
        for key, display in choices
        if callback_fits(f"agent:{key}")
    ]
    shown = dict(choices).get(current, current)
    return paginate(
        kind="agent",
        title="Agent",
        header=(
            f"Current: {shown}\n"
            "A conversation keeps its agent, so another one starts a new conversation."
        ),
        options=options,
        current_value=f"agent:{current}",
        current_label=shown,
        page=page,
    )


def new_card(*, line: str, group: bool = False) -> SelectionCard:
    """The `/new` answer: one line naming the agent, model and directory the
    fresh conversation runs on, with Agent, Model and Dir buttons to change
    them (spec channels "Answer the conversation commands from any paired
    chat"). In a group only Agent is offered: Model and Dir are direct-chat
    commands."""
    buttons = [ChoiceButton(label="Agent", value=f"agent:{PICK_AGENT}")]
    if not group:
        buttons += [
            ChoiceButton(label="Model", value="cmd:model"),
            ChoiceButton(label="Dir", value="cmd:dir"),
        ]
    return SelectionCard(title="", text=f"**🆕 New conversation · {line}**", buttons=buttons)


def help_card(*, text: str, group: bool, page: int | None = None) -> SelectionCard:
    """The `/help` card: ``text`` under a ``cmd:`` button for every command the
    chat may use, from the roster — all of them in a direct chat, the group
    commands in a group — paged like any list too long for one card (spec
    channels "Offer the commands as a help card")."""
    options = [
        ChoiceButton(label=entry.name.capitalize(), value=f"cmd:{entry.name}")
        for entry in menu_entries(group=group)
    ]
    return paginate(
        kind="help",
        title="Commands",
        header=text,
        options=options,
        current_value=None,
        current_label="",
        page=page,
    )


def command_card(*, title: str, text: str, actions: Sequence[tuple[str, str]]) -> SelectionCard:
    """A `/status` card: ``text`` under ``title`` with its ``cmd:``
    actions — a tap runs exactly the command it names."""
    buttons = [ChoiceButton(label=label, value=f"cmd:{name}") for label, name in actions]
    return SelectionCard(title=title, text=text, buttons=buttons)


def current_help_card(*, group: bool, page: int | None = None) -> SelectionCard:
    """The help card for a chat of this kind, opened on ``page``."""
    return help_card(text=help_text(group=group), group=group, page=page)
