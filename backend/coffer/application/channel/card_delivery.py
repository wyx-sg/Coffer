"""A card's life in the chat after it is sent: route a tap, keep it honest.

Why the tap half exists: a card offers choices (``model:``, ``effort:``,
``dir:``, ``resume:``, ``collection:``) and actions (``cmd:<name>``, which runs
exactly what typing ``/<name>`` would). Each tap is owner-gated by the
processor and routed here to the same function the typed command calls (spec
channels "Offer choices and actions as owner-gated cards").

Why the rewrite half exists: tapping a card used to post a confirmation and
leave the card itself untouched — still showing the old choice ticked and still
offering the option the user had just taken. SeaTalk's Update Message and
Telegram's ``editMessageText`` both let the card be rewritten in place, so it
is; the model card's tap goes further and rewrites the card into its effort
step (spec channels "Switch the model and reasoning effort from chat").

Why the page half exists: the same rewrite turns a bounded card into a browsable
one. A Prev/Next tap re-renders the SAME message at another window of the same
list — the one thing it must never do is change what is in effect, so it is
routed apart from a choice before any switch code is reached.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from coffer.application.channel import document_save, model_switch
from coffer.application.channel.command_context import deliver_card
from coffer.application.channel.dir_switch import apply_dir, current_dir_card
from coffer.application.channel.resume_switch import apply_resume, current_resume_card
from coffer.application.channel.selection_cards import (
    KEEP_EFFORT,
    SelectionCard,
    collection_card,
    is_page_turn,
    parse_page_turn,
)
from coffer.domain.channel.commands import command_name

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = [
    "card_as_text",
    "deliver_card",
    "dispatch_card_tap",
    "refresh_selection_card",
    "turn_card_page",
]

_logger = logging.getLogger(__name__)

#: The command that summons a fresh card of each kind.
_COMMAND_FOR = {"collection": "kb", "effort": "model"}


async def dispatch_card_tap(ctx: CommandContext, data: str) -> None:
    """Route one owner-gated tap: a page turn, an action, or a choice.

    The page question is asked FIRST and answered exhaustively: a navigation
    value never reaches a switch, and a value that merely looks like
    navigation (``page:`` with a kind or index we do not render) is dropped.
    """
    turn = parse_page_turn(data)
    if turn is not None:
        await turn_card_page(ctx, *turn)
        return
    if is_page_turn(data):
        return
    kind, _, value = data.partition(":")
    if not value:
        return
    if kind == "cmd":
        # Exactly what typing it would do — a name not on the roster is ignored.
        if command_name(f"/{value}") is not None:
            await ctx.commands.run(ctx, f"/{value}")
        return
    if kind == "collection":
        # A save is one-shot, not a toggle: nothing to re-tick.
        await document_save.apply_save_collection(ctx, value)
        return
    if kind == "model":
        await model_switch.apply_model(ctx, value)
        if await model_switch.after_model_tap(ctx):
            return
    elif kind == "effort" and value == KEEP_EFFORT:
        settings = await ctx.settings()
        await ctx.say(f"🎚 Effort kept at {settings.effort or 'default'}.")
        kind = "model"
    elif kind == "effort":
        await model_switch.apply_effort(ctx, value)
    elif kind == "dir":
        directories = ctx.binding.directories
        if value == "default":
            await apply_dir(ctx, None)
        elif value.isdigit() and int(value) < len(directories):
            await apply_dir(ctx, directories[int(value)])
        else:
            await ctx.say("That directory is no longer allowed — send /dir for the list.")
            return
    elif kind == "resume":
        await apply_resume(ctx, value)
    else:
        return
    await refresh_selection_card(ctx, kind)


async def refresh_selection_card(ctx: CommandContext, kind: str) -> None:
    """Rewrite the tapped card so its tick sits on the new choice.

    The card is rebuilt with no page given, which lands it on the page holding
    the choice now in effect — the page the tap came from.

    Best-effort by design. The switch already happened and was confirmed in
    chat, so a transport that cannot update a card — or an update that fails
    because the card aged past SeaTalk's 7-day window, or the platform
    rate-limited us — must not turn a successful switch into a visible error.
    """
    caps = ctx.binding.adapter.capabilities
    if not (ctx.card_message_id and caps.supports_buttons and caps.supports_card_update):
        return
    try:
        card = await _current_card(ctx, kind)
        if card is None or not card.buttons:
            return
        await ctx.binding.adapter.update_card(
            ctx.chat_id,
            ctx.card_message_id,
            card.text,
            card.buttons,
            title=card.title,
            chat_kind=ctx.chat_kind,
        )
    except Exception:
        _logger.warning(
            "channel.card.refresh_failed",
            extra={"channel": ctx.binding.resource.name},
            exc_info=True,
        )


async def turn_card_page(ctx: CommandContext, kind: str, page: int) -> None:
    """Show another page of the same card, changing nothing else.

    The card is rebuilt from what is CURRENTLY in effect — a page turn reads
    state and never writes it. Unlike a refresh it is not cosmetic, so its
    failures degrade rather than drop: a card that cannot be rewritten in place
    is posted fresh, and a fresh card that is refused goes out as text.
    """
    try:
        card = await _current_card(ctx, kind, page=page)
    except Exception:
        _logger.warning(
            "channel.card.page_failed", extra={"channel": ctx.binding.resource.name}, exc_info=True
        )
        card = None
    if card is None or not card.buttons:
        command = _COMMAND_FOR.get(kind, kind)
        await ctx.say(f"Could not turn the page — send /{command} for a fresh card.")
        return
    caps = ctx.binding.adapter.capabilities
    if ctx.card_message_id and caps.supports_card_update:
        try:
            await ctx.binding.adapter.update_card(
                ctx.chat_id,
                ctx.card_message_id,
                card.text,
                card.buttons,
                title=card.title,
                chat_kind=ctx.chat_kind,
            )
            return
        except Exception:
            _logger.warning(
                "channel.card.page_update_failed",
                extra={"channel": ctx.binding.resource.name, "card": card.title, "page": card.page},
                exc_info=True,
            )
    if await ctx.show(card):
        return
    await ctx.say(card_as_text(card))


def card_as_text(card: SelectionCard) -> str:
    """The card written out for a transport that will not take it as a card.

    Navigation is dropped — there is nothing to tap on a text message — so the
    page's own choices are what survives, under the same body that names what
    is currently in effect. A choice whose button shows a name rather than the
    value it carries (a model's "Fable 1M") also gets that value, since the value
    is what the command takes.
    """
    lines = []
    for b in card.buttons:
        if is_page_turn(b.value):
            continue
        arg = b.value.split(":", 1)[-1]
        name = b.label.removesuffix(" ✓")
        lines.append(f"• {b.label}" if name == arg else f"• {b.label} — {arg}")
    return "\n".join([card.title, card.text, *lines])


async def _current_card(
    ctx: CommandContext, kind: str, *, page: int | None = None
) -> SelectionCard | None:
    """Re-read what is now in effect and render that card.

    Deliberately re-reads rather than assuming the tapped value took: the switch
    is what the card must reflect, and only the store knows whether it landed.
    ``page`` is ``None`` for "the page holding the current choice".
    """
    if kind == "collection":
        # Nothing agent-specific to ask — the same whole-catalogue question
        # `/kb` itself asks (spec channels "Save a sent document into a collection").
        known = await ctx.commands._collections.collection_names()
        return collection_card(choices=known, page=page) if known else None
    if kind == "model":
        return await model_switch.current_model_card(ctx, page=page)
    if kind == "effort":
        return await model_switch.current_effort_card(ctx, page=page)
    if kind == "dir":
        return await current_dir_card(ctx, page=page)
    if kind == "resume":
        return await current_resume_card(ctx, page=page)
    return None
