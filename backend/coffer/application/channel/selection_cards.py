"""The selection cards Coffer offers in a chat, built in one place.

There are a few — pick a model and then how hard it thinks, pick a working
directory, pick an earlier conversation to resume, pick where a document is
saved — and each is built three times:
when the user asks for it, when they turn a page, and again after they tap, so
the card stops offering the option they just took. Building them here rather
than inline in ``commands.py`` keeps those renderings from drifting apart,
which is the whole failure the refresh exists to fix: a card that says one
thing while the system does another.

The ``cmd:`` buttons a `/status` or `/help` card carries are built here too
(spec channels "Offer the commands as a help card").

Pagination lives here too, for every card rather than for models alone. A card
is a window onto a list, not the list: the model catalogue runs to 29 entries
for ``claude_code`` and SeaTalk refuses a card that long outright
(``/messaging/v2/single_chat: code=102``). The window is browsed with Prev/Next
buttons that rewrite the same message, so a long list is read inside the one
card instead of being truncated away.

Pure functions over already-fetched values. Whoever calls them owns the I/O of
finding out what "current" is, and ``card_delivery`` owns putting the result on
the wire.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coffer.domain.channel.envelopes import ChoiceButton

#: Telegram caps ``callback_data`` at 64 bytes and SeaTalk's custom ``value``
#: is likewise small. A choice whose payload does not fit is dropped from the
#: card rather than sent as a button that errors on tap.
CALLBACK_MAX_BYTES = 64

#: The namespace a *navigation* payload lives in — ``page:<kind>:<index>``,
#: e.g. ``page:model:3`` (13 bytes, fixed-size, nowhere near the cap).
#:
#: It is deliberately disjoint from the ``model:`` / ``effort:`` / ``dir:`` /
#: ``resume:`` / ``collection:`` / ``cmd:`` namespaces the *choices* use: a page
#: turn must change nothing, and the one way it could change something is by
#: being mistaken for a choice. Because the prefix is read first and a whole
#: page value can never parse as ``model:<id>``, no catalogue entry — however
#: it is named — can collide with a page turn.
PAGE_PREFIX = "page"

#: The most buttons any card carries, navigation included.
#:
#: SeaTalk's ceilings are documented (read 2026-09-11): a card takes at most 5
#: bare ``button`` elements, OR up to 3 ``button_group`` elements of 1-3 buttons
#: each — which is why the SeaTalk adapter emits rows rather than bare buttons,
#: and why six buttons are legal where six bare ones would not be. Six is
#: therefore a choice, not a guess: it fits the three allowed rows even when
#: long labels force two to a row, and it is enough for Prev/Next plus four
#: choices. It is also
#: what Coffer already shipped (the ``MAX_MODEL_PICKS`` bound this pagination
#: replaces), so pagination adds no new risk of a refused card — it only makes
#: the rest of the list reachable. Telegram has no comparable ceiling, so the
#: tighter platform sets the number for both.
MAX_CARD_BUTTONS = 6

#: Choices per page. Prev and Next consume button slots of their own, so a
#: paginated card shows ``MAX_CARD_BUTTONS - 2`` choices and still fits.
PAGE_SIZE = MAX_CARD_BUTTONS - 2

#: The card kinds that can be paged — closed and explicit, so a page value
#: naming anything else is dropped rather than re-rendered.
PAGED_KINDS: frozenset[str] = frozenset({"model", "effort", "collection", "resume", "dir"})

#: The ``effort:`` value of the effort step's "Keep …" button: no change.
KEEP_EFFORT = "-"

#: The five actions a `/status` and a `/help` card offer, as ``(label, command)``
#: (spec channels "Report the chat's state as a status card").
COMMAND_ACTIONS: tuple[tuple[str, str], ...] = (
    ("Stop", "stop"),
    ("New", "new"),
    ("Model", "model"),
    ("Resume", "resume"),
    ("Dir", "dir"),
)

#: A button label longer than this is cut (a resume card's titles).
_LABEL_MAX = 32


def callback_fits(value: str) -> bool:
    return len(value.encode("utf-8")) <= CALLBACK_MAX_BYTES


def is_page_turn(value: str) -> bool:
    """Whether a tapped value asks for another page rather than making a choice."""
    return value.partition(":")[0] == PAGE_PREFIX


def parse_page_turn(value: str) -> tuple[str, int] | None:
    """``"page:model:3"`` → ``("model", 3)``; anything else → ``None``.

    Returning ``None`` for every non-navigation value is what keeps the two
    kinds of tap apart at the routing layer: the caller asks this question
    first, and only a well-formed page turn for a card kind we actually render
    ever reaches the re-render path. A malformed one is not "then it must be a
    choice" — it is dropped.
    """
    prefix, _, rest = value.partition(":")
    if prefix != PAGE_PREFIX:
        return None
    kind, _, index = rest.partition(":")
    if kind not in PAGED_KINDS or not index.isdigit():
        return None
    return kind, int(index)


@dataclass(frozen=True)
class SelectionCard:
    """One rendered card: the title element, the body, and the buttons.

    ``buttons`` empty means there is nothing tappable to show — every candidate
    was dropped for an oversized payload, or there were none to begin with — and
    the caller falls back to plain text.

    ``page``/``pages`` describe the window: ``pages == 1`` is a card that fits
    whole and therefore carries no navigation chrome at all.
    """

    title: str
    text: str
    buttons: list[ChoiceButton]
    page: int = 0
    pages: int = 1


def _tick(label: str, selected: bool) -> str:
    """Mark the option currently in effect. The tick is what makes a refreshed
    card readable at a glance: the same list, one mark moved."""
    return f"{label} ✓" if selected else label


def _home_page(options: Sequence[ChoiceButton], current_value: str | None) -> int | None:
    """The page holding the option in effect, or ``None`` when it is on no page.

    This is also the page a card opens on, so the tick is visible the moment
    the card arrives, and the page a card returns to after a choice is applied
    — which is exactly the page the tap came from.

    ``None`` is a real case, not a defensive one: a model set by name can be an
    alias, or newer than the installed catalogue, and then no button carries it.
    A card must not answer "where is the tick" with a page that has no tick.
    """
    for index, button in enumerate(options):
        if button.value == current_value:
            return index // PAGE_SIZE
    return None


def _navigation(kind: str, page: int, pages: int) -> list[ChoiceButton]:
    """Prev/Next for this page — each omitted at the end it would run off, so
    the last page is never followed by an empty one."""
    nav: list[ChoiceButton] = []
    if page > 0:
        nav.append(ChoiceButton(label="← Prev", value=f"{PAGE_PREFIX}:{kind}:{page - 1}"))
    if page + 1 < pages:
        nav.append(ChoiceButton(label="Next →", value=f"{PAGE_PREFIX}:{kind}:{page + 1}"))
    return nav


def _paginate(
    *,
    kind: str,
    title: str,
    header: str,
    options: list[ChoiceButton],
    current_value: str | None,
    current_label: str,
    page: int | None,
) -> SelectionCard:
    """Window ``options`` into one card — the single place the rule lives.

    A list that fits is rendered exactly as it always was: no Prev, no Next, no
    "Page 1/1" footer.

    ``page`` is ``None`` for "open on whichever page holds the current choice";
    an explicit index is clamped into range, so a stale Next from an older,
    longer catalogue cannot land past the end.
    """
    if len(options) <= MAX_CARD_BUTTONS:
        return SelectionCard(title=title, text=header, buttons=options)
    pages = (len(options) + PAGE_SIZE - 1) // PAGE_SIZE
    home = _home_page(options, current_value)
    index = (home or 0) if page is None else max(0, min(page, pages - 1))
    window = options[index * PAGE_SIZE : index * PAGE_SIZE + PAGE_SIZE]
    footer = f"Page {index + 1}/{pages}"
    if home is not None and not any(b.value == current_value for b in window):
        # The tick lives on another page. The header already names what is in
        # effect; say where it is too, so a card showing no tick never reads as
        # a card claiming nothing is selected.
        footer += f" · ✓ {current_label} is on page {home + 1}"
    return SelectionCard(
        title=title,
        text=f"{header}\n{footer}",
        buttons=window + _navigation(kind, index, pages),
        page=index,
        pages=pages,
    )


def model_card(
    *,
    current: str | None,
    picks: Sequence[str],
    labels: Mapping[str, str] | None = None,
    page: int | None = None,
) -> SelectionCard:
    """Pick the model the agent's CLI runs next turn.

    ``current`` is ``None`` when no model is pinned, in which case the body says
    the CLI's own default is in effect and no option carries the tick.

    ``picks`` is the agent's whole model catalogue, and the whole of it is now
    browsable: a long catalogue becomes pages rather than a truncated handful.
    The ``/model <name>`` hint stays — it is still the fastest way to a model
    you can already name, and the only way to one the catalogue does not list.

    ``labels`` maps an id to the name its button shows; an id it does not name
    shows itself. The tap still carries the id.
    """
    names = labels or {}
    shown = current or "(CLI default)"
    options = [
        ChoiceButton(
            label=_tick(names.get(name) or name, name == current),
            value=f"model:{name}",
            selected=name == current,
        )
        for name in dict.fromkeys(picks)
        if callback_fits(f"model:{name}")
    ]
    return _paginate(
        kind="model",
        title="Model",
        header=f"Current model: {shown}\nTap a choice (or send /model <name>):",
        options=options,
        current_value=f"model:{current}" if current else None,
        current_label=shown,
        page=page,
    )


def effort_card(
    *,
    current: str | None,
    levels: Sequence[str],
    model: str | None = None,
    page: int | None = None,
) -> SelectionCard:
    """The effort step of the model card: how hard the chosen model thinks
    (spec channels "Switch the model and reasoning effort from chat").

    The level is not part of the model NAME — both agents take it as their own
    field (Codex's ``turn/start``, Claude's ``--effort``) — so it is a second
    step rather than four buttons per model. A ``Keep …`` button ends the step
    without changing anything, so a model tap never forces a level choice.

    ``current`` is ``None`` when the conversation pins no level (the agent's
    own default is in effect, and no level carries the tick). ``model`` is the
    model's shown name for the header. The caller only builds this when
    ``levels`` is non-empty.
    """
    shown = current or "default"
    options = [
        ChoiceButton(
            label=_tick(level, level == current),
            value=f"effort:{level}",
            selected=level == current,
        )
        for level in dict.fromkeys(levels)
        if callback_fits(f"effort:{level}")
    ]
    options.append(ChoiceButton(label=f"Keep {shown}", value=f"effort:{KEEP_EFFORT}"))
    header = f"Model: {model}\n" if model else ""
    return _paginate(
        kind="effort",
        title="Effort",
        header=f"{header}Current effort: {shown}\nTap a level (or send /model <level>):",
        options=options,
        current_value=f"effort:{current}" if current else None,
        current_label=shown,
        page=page,
    )


def collection_card(*, choices: Sequence[str], page: int | None = None) -> SelectionCard:
    """Pick which collection a pending `/kb` document lands in (spec channels
    "Save a sent document into a collection").

    Unlike a model there is no "current" choice to tick — every save is a fresh
    decision, never a toggle a card must show as already in effect. A single-collection
    vault still renders one button rather than acting on it unasked: "Save a sent
    document into a collection" requires the owner confirm, and a lone collection is not
    an exemption from that.
    """
    options = [
        ChoiceButton(label=name, value=f"collection:{name}")
        for name in choices
        if callback_fits(f"collection:{name}")
    ]
    return _paginate(
        kind="collection",
        title="Save to which collection?",
        header="Tap a collection to save the document there:",
        options=options,
        current_value=None,
        current_label="",
        page=page,
    )


def dir_card(
    *, current: str | None, directories: Sequence[str], page: int | None = None
) -> SelectionCard:
    """Pick the working directory from the channel's allow-list (spec channels
    "Choose the working directory from chat"). A button carries the entry's
    index (``dir:<i>``), not its path: a path can outgrow the payload cap and
    the allow-list is the one place it is resolved against anyway."""

    def base(path: str) -> str:
        return os.path.basename(os.path.normpath(path)) or path

    options = [
        ChoiceButton(
            label=_tick(base(path), path == current), value=f"dir:{i}", selected=path == current
        )
        for i, path in enumerate(directories)
    ]
    options.append(
        ChoiceButton(
            label=_tick("Default", current is None), value="dir:default", selected=current is None
        )
    )
    shown = current or "default"
    current_value = (
        "dir:default"
        if current is None
        else next((f"dir:{i}" for i, path in enumerate(directories) if path == current), None)
    )
    return _paginate(
        kind="dir",
        title="Directory",
        header=f"Current directory: {shown}\nTap one to start a fresh conversation there:",
        options=options,
        current_value=current_value,
        current_label=base(shown),
        page=page,
    )


def resume_card(
    *,
    header: str,
    entries: Sequence[tuple[str, str]],
    active: str | None,
    page: int | None = None,
) -> SelectionCard:
    """Pick an earlier conversation of this chat thread to reopen (spec channels
    "Resume an earlier conversation from chat"). ``entries`` is
    ``(conversation id, title)``, newest first; ``header`` is the listing."""
    options = []
    for n, (conversation_id, title) in enumerate(entries, start=1):
        label = f"{n}. {title}"
        if len(label) > _LABEL_MAX:
            label = label[: _LABEL_MAX - 1].rstrip() + "…"
        value = f"resume:{conversation_id}"
        if callback_fits(value):
            selected = conversation_id == active
            options.append(
                ChoiceButton(label=_tick(label, selected), value=value, selected=selected)
            )
    return _paginate(
        kind="resume",
        title="Resume",
        header=header,
        options=options,
        current_value=f"resume:{active}" if active else None,
        current_label="the current one",
        page=page,
    )


def command_card(*, title: str, text: str) -> SelectionCard:
    """A `/status` or `/help` card: ``text`` under ``title`` with the five
    ``cmd:`` actions — a tap runs exactly the command it names."""
    buttons = [ChoiceButton(label=label, value=f"cmd:{name}") for label, name in COMMAND_ACTIONS]
    return SelectionCard(title=title, text=text, buttons=buttons)
