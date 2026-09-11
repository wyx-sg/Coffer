"""The selection cards Coffer offers in a chat, built in one place.

There are two — pick an agent, pick a model — and each is now built twice: once
when the user asks for it, and again after they tap, so the card stops offering
the option they just took. Building them here rather than inline in
``commands.py`` keeps those two renderings from drifting apart, which is the
whole failure the refresh exists to fix: a card that says one thing while the
system does another.

Pure functions over already-fetched values. Whoever calls them owns the I/O of
finding out what "current" is.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from coffer.domain.channel.envelopes import ChoiceButton

#: Telegram caps ``callback_data`` at 64 bytes and SeaTalk's custom ``value``
#: is likewise small. A choice whose payload does not fit is dropped from the
#: card rather than sent as a button that errors on tap.
CALLBACK_MAX_BYTES = 64


def callback_fits(value: str) -> bool:
    return len(value.encode("utf-8")) <= CALLBACK_MAX_BYTES


@dataclass(frozen=True)
class SelectionCard:
    """One rendered card: the title element, the body, and the buttons.

    ``buttons`` empty means there is nothing tappable to show — every candidate
    was dropped for an oversized payload, or there were none to begin with — and
    the caller falls back to plain text.
    """

    title: str
    text: str
    buttons: list[ChoiceButton]


def _tick(label: str, selected: bool) -> str:
    """Mark the option currently in effect. The tick is what makes a refreshed
    card readable at a glance: the same list, one mark moved."""
    return f"{label} ✓" if selected else label


def agent_card(*, current: str, choices: Sequence[tuple[str, str]]) -> SelectionCard:
    """Pick which agent answers in this chat/thread.

    ``choices`` is ``(key, display name)``; ``current`` is the key in effect.
    """
    return SelectionCard(
        title="Agent",
        text=f"Current agent: {current}\nTap to switch:",
        buttons=[
            ChoiceButton(label=_tick(name, key == current), value=f"agent:{key}")
            for key, name in choices
            if callback_fits(f"agent:{key}")
        ],
    )


def model_card(*, current: str | None, picks: Sequence[str]) -> SelectionCard:
    """Pick the model the agent's CLI runs next turn.

    ``current`` is ``None`` when no model is pinned, in which case the body says
    the CLI's own default is in effect and no option carries the tick.
    """
    shown = current or "(CLI default)"
    return SelectionCard(
        title="Model",
        text=f"Current model: {shown}\nTap a quick-pick (or send /model <name>):",
        buttons=[
            ChoiceButton(label=_tick(m, m == current), value=f"model:{m}")
            for m in picks
            if callback_fits(f"model:{m}")
        ],
    )
