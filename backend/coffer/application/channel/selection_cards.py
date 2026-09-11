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

#: How many model buttons a card may carry. The model catalogue is the whole
#: list of models an agent can run — 29 for claude_code — and a card built from
#: all of them is both unreadable on a phone and refused outright by SeaTalk
#: (``/messaging/v2/single_chat: code=102``), leaving the user with nothing.
#: A quick-pick card is a handful; ``/model <name>`` still reaches the rest.
MAX_MODEL_PICKS = 6


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


def _model_quick_picks(current: str | None, picks: Sequence[str]) -> list[str]:
    """At most ``MAX_MODEL_PICKS`` ids, the one in effect always among them.

    The current model leads so a refreshed card always has a tick to show —
    dropping it off the end of a long catalogue would leave the card claiming
    nothing is selected. The remaining slots follow ``picks`` in catalogue
    order, which for ``claude_code`` starts with the short aliases (``sonnet``,
    ``opus``, ``haiku``, …) — exactly the ones worth a button.
    """
    chosen: list[str] = []
    for candidate in ([current] if current else []) + list(picks):
        if len(chosen) >= MAX_MODEL_PICKS:
            break
        if candidate in chosen or not callback_fits(f"model:{candidate}"):
            continue
        chosen.append(candidate)
    return chosen


def model_card(*, current: str | None, picks: Sequence[str]) -> SelectionCard:
    """Pick the model the agent's CLI runs next turn.

    ``current`` is ``None`` when no model is pinned, in which case the body says
    the CLI's own default is in effect and no option carries the tick.

    ``picks`` is the agent's whole model catalogue; only a bounded handful of it
    becomes buttons (see ``MAX_MODEL_PICKS``). The body's ``/model <name>`` hint
    is what keeps that honest — it is how the rest of the catalogue is reached.
    """
    shown = current or "(CLI default)"
    return SelectionCard(
        title="Model",
        text=f"Current model: {shown}\nTap a quick-pick (or send /model <name>):",
        buttons=[
            ChoiceButton(label=_tick(m, m == current), value=f"model:{m}")
            for m in _model_quick_picks(current, picks)
        ],
    )
