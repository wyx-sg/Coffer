"""A card's life in the chat after it is sent: route a tap, keep it honest.

Why the tap half exists: a card offers choices (``model:``, ``effort:``,
``dir:``, ``resume:``, ``agent:``) and actions (``cmd:<name>``, which runs
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

from coffer.application.channel import model_switch, new_conversation
from coffer.application.channel.agent_routing import routable_choices
from coffer.application.channel.command_cards import PICK_AGENT
from coffer.application.channel.command_context import deliver_card
from coffer.application.channel.details_card import DETAILS_KINDS, apply_details_tap
from coffer.application.channel.dir_switch import apply_dir, current_dir_card
from coffer.application.channel.reply_tracking import WITHDRAW_KIND
from coffer.application.channel.resume_switch import apply_resume, current_resume_card
from coffer.application.channel.selection_cards import (
    KEEP_EFFORT,
    SelectionCard,
    is_page_turn,
    parse_page_turn,
)
from coffer.domain.channel.commands import DM_ONLY_NOTICE, command_name

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
#: The choice kinds that belong to the direct-chat commands.
_DM_ONLY_CHOICES = frozenset({"model", "effort", "dir", "resume"})
_COMMAND_FOR = {"effort": "model", "agent": "new"}


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
    if ctx.chat_kind == "group" and kind in _DM_ONLY_CHOICES:
        # A card of a direct-chat command still on screen in a group (spec
        # channels "Answer the conversation commands from any paired chat").
        await ctx.say(DM_ONLY_NOTICE)
        return
    if kind == WITHDRAW_KIND:
        # The 🗑 under a reply (spec channels "Withdraw a bot reply on the owner's command").
        await ctx.commands.withdrawal.tap(ctx, value)
        return
    if kind == "cmd":
        # Exactly what typing it would do — a name not on the roster is ignored.
        if command_name(f"/{value}") is not None:
            await ctx.commands.run(ctx, f"/{value}")
        return
    if kind in DETAILS_KINDS:
        # A reply's details, behind its summary card: one-shot, nothing to re-tick.
        await apply_details_tap(ctx, kind, value)
        return
    if kind == "agent" and value == PICK_AGENT:
        # The `/new` card's Agent button: offer the agents, change nothing yet.
        card = await new_conversation.current_agent_card(ctx)
        await ctx.show_or_say(card, card_as_text(card))
        return
    if kind == "agent":
        if not any(key == value for key, _ in _agent_choices(ctx)):
            await ctx.say("That agent is no longer one this bot may use — send /new.")
            return
        await new_conversation.apply_agent(ctx, value)
    elif kind == "model":
        await model_switch.apply_model(ctx, value, announce=False)
        if await model_switch.after_model_tap(ctx):
            return
        await model_switch.say_model(ctx)
    elif kind == "effort" and value == KEEP_EFFORT:
        await model_switch.say_model(ctx)
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
    if kind == "model":
        return await model_switch.current_model_card(ctx, page=page)
    if kind == "effort":
        return await model_switch.current_effort_card(ctx, page=page)
    if kind == "dir":
        return await current_dir_card(ctx, page=page)
    if kind == "agent":
        return await new_conversation.current_agent_card(ctx, page=page)
    if kind == "resume":
        return await current_resume_card(ctx, page=page)
    return None


def _agent_choices(ctx: CommandContext) -> list[tuple[str, str]]:
    return list(routable_choices(ctx.binding, ctx.commands._agents))
