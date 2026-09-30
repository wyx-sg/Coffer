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

#: The five actions a `/help` card offers (spec channels "Offer the commands as
#: a help card").
HELP_ACTIONS: tuple[tuple[str, str], ...] = (
    ("New", "new"),
    ("Stop", "stop"),
    ("Model", "model"),
    ("Status", "status"),
    ("Resume", "resume"),
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


def new_card(*, line: str) -> SelectionCard:
    """The `/new` answer: one line naming the agent, model and directory the
    fresh conversation runs on, with Agent, Model and Dir buttons to change
    them (spec channels "Answer the conversation commands from any paired
    chat")."""
    return SelectionCard(
        title="",
        text=f"**🆕 New conversation · {line}**",
        buttons=[
            ChoiceButton(label="Agent", value=f"agent:{PICK_AGENT}"),
            ChoiceButton(label="Model", value="cmd:model"),
            ChoiceButton(label="Dir", value="cmd:dir"),
        ],
    )


def command_card(
    *, title: str, text: str, actions: Sequence[tuple[str, str]] = HELP_ACTIONS
) -> SelectionCard:
    """A `/status` or `/help` card: ``text`` under ``title`` with its ``cmd:``
    actions — a tap runs exactly the command it names."""
    buttons = [ChoiceButton(label=label, value=f"cmd:{name}") for label, name in actions]
    return SelectionCard(title=title, text=text, buttons=buttons)
