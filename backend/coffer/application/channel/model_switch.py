"""`/model` — the model and its reasoning effort, one command (spec channels
"Switch the model and reasoning effort from chat").

``/model`` alone is a two-step card: the model step (the agent's paginated
catalogue); a model tap sets it and, when that model reports levels, rewrites
the same card into the effort step (the levels plus ``Keep …``). Typed forms:
``/model <level>`` (a word of the closed :data:`EFFORT_LEVELS` vocabulary) sets
the effort only, ``/model <name> [<level>]`` the model and optionally the
effort, ``/model default`` clears both.

Both are parametric — the SAME conversation runs its next turn on them — and
both are remembered on the thread, so a fresh conversation opens on them too
(spec channels "Keep a chat's settings across its conversations"). A model
name is matched against the catalogue's ids and shown names; anything else is
passed through verbatim, since the agent's CLI owns that namespace. In a SeaTalk
group's main chat only the group's defaults row is written (spec channels "Set
a group's defaults from its main chat").
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from coffer.application.channel.command_text import (
    model_display,
)
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.selection_cards import SelectionCard, effort_card, model_card
from coffer.domain.channel.commands import EFFORT_LEVELS
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = [
    "after_model_tap",
    "apply_effort",
    "apply_model",
    "cmd_model",
    "current_effort_card",
    "current_model_card",
    "say_model",
]

_logger = logging.getLogger(__name__)


async def cmd_model(ctx: CommandContext, text: str) -> None:
    words = text.split()[1:]
    if not words:
        await _show(ctx)
        return
    if len(words) == 1 and words[0].lower() == "default":
        await _clear(ctx)
        return
    if len(words) == 1 and words[0].lower() in EFFORT_LEVELS:
        await apply_effort(ctx, words[0].lower())
        return
    level = None
    if len(words) > 1 and words[-1].lower() in EFFORT_LEVELS:
        level = words.pop().lower()
    await apply_model(ctx, await _match_model(ctx, " ".join(words)), level=level)


async def _match_model(ctx: CommandContext, typed: str) -> str:
    """The catalogue id ``typed`` names (by id or shown name, case-insensitive),
    else ``typed`` itself — passed through for the CLI to judge."""
    settings = await ctx.settings()
    labels = await ctx.commands._model_suggestions.model_labels(settings.agent)
    wanted = typed.lower()
    for model_id, label in labels.items():
        if wanted in (model_id.lower(), (label or "").lower()):
            return model_id
    return typed


async def _conversation(ctx: CommandContext) -> str | None:
    """The thread's conversation (opened if it has none), or ``None`` after
    saying why there is none."""
    try:
        return await ensure_conversation(
            ctx.commands._conversations,
            ctx.commands._threads,
            ctx.binding,
            ctx.peer,
            ctx.conversation_thread_id,
            chat_kind=ctx.chat_kind,
        )
    except CofferError as e:
        await ctx.say(explain_conversation_error(e))
        return None


async def _remember(ctx: CommandContext, **values: str | None) -> None:
    """Stick ``values`` on the thread, pinning the agent they belong to: a model
    of one agent is not a model of another, so a sticky model only rides a
    fresh conversation while its agent is the sticky one."""
    settings = await ctx.settings()
    await ctx.commands._threads.set_preferences(
        ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id, agent=settings.agent, **values
    )


async def _set(ctx: CommandContext, **values: str | None) -> bool:
    """Write ``values`` (``model``/``effort``) to the conversation and the thread."""
    conversation_id = await _conversation(ctx)
    if conversation_id is None:
        return False
    conversations = ctx.commands._conversations
    cfg = await conversations.get_agent_config(conversation_id)
    await conversations.set_agent_config(conversation_id, replace(cfg, **values))
    await _remember(ctx, **values)
    return True


def _where(_ctx: CommandContext) -> str:
    return " — from your next message"


async def apply_model(
    ctx: CommandContext, model: str, *, level: str | None = None, announce: bool = True
) -> bool:
    """Set the model (and ``level``, when given). Shared by the typed form and a
    card tap, which sets quietly when the effort step follows (``announce``)."""
    values = {"model": model} if level is None else {"model": model, "effort": level}
    if not await _set(ctx, **values):
        return False
    if announce:
        await say_model(ctx)
    return True


async def say_model(ctx: CommandContext) -> None:
    """``Model: Claude Sonnet 5.5 · effort Medium — from your next message``."""
    settings = await ctx.settings()
    model = settings.model
    level = settings.effort
    shown = await model_display(ctx.commands, settings.agent, model) if model else "Default model"
    tail = f" · effort {level.capitalize()}" if level else ""
    await ctx.say(f"Model: {shown}{tail}{_where(ctx)}")


async def apply_effort(ctx: CommandContext, level: str) -> None:
    """Set the reasoning effort only. Pure passthrough: a level the account
    cannot run fails where every unusable choice fails — at the CLI."""
    if await _set(ctx, effort=level):
        await say_model(ctx)


async def _clear(ctx: CommandContext) -> None:
    if await _set(ctx, model=None, effort=None):
        await ctx.say(f"Model and effort: the agent's defaults{_where(ctx)}")


async def _show(ctx: CommandContext) -> None:
    """Bare `/model`: the model card, else the settings in text."""
    settings = await ctx.settings()
    labels = await ctx.commands._model_suggestions.model_labels(settings.agent)
    card = model_card(
        current=settings.model, picks=list(labels), labels=labels, effort=settings.effort
    )
    if await ctx.show(card):
        return
    shown = await model_display(ctx.commands, settings.agent, settings.model)
    lines = [f"Model: {shown}", f"Effort: {settings.effort or 'default'}"]
    if labels:
        lines.append("Available: " + ", ".join(label or i for i, label in labels.items()))
    lines.append("Send /model <name> [level], /model <level> or /model default.")
    await ctx.say("\n".join(lines))


async def current_model_card(ctx: CommandContext, *, page: int | None = None) -> SelectionCard:
    settings = await ctx.settings()
    labels = await ctx.commands._model_suggestions.model_labels(settings.agent)
    return model_card(
        current=settings.model,
        picks=list(labels),
        labels=labels,
        effort=settings.effort,
        page=page,
    )


async def current_effort_card(
    ctx: CommandContext, *, page: int | None = None
) -> SelectionCard | None:
    """The effort step for the model now in effect, or ``None`` when that model
    takes no level. Asked against the model, not the agent: the levels belong
    to the model, so the step after a switch offers the new model's menu."""
    settings = await ctx.settings()
    levels = await ctx.commands._model_suggestions.efforts(settings.agent, settings.model)
    if not levels:
        return None
    shown = await model_display(ctx.commands, settings.agent, settings.model)
    return effort_card(current=settings.effort, levels=levels, model=shown, page=page)


async def after_model_tap(ctx: CommandContext) -> bool:
    """The model card's second step: rewrite the tapped card into the effort
    step (or post it fresh where a card cannot be rewritten). ``False`` when
    the model takes no level, so the caller refreshes the model card instead."""
    card = await current_effort_card(ctx)
    if card is None:
        return False
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
            return True
        except Exception:
            _logger.warning(
                "channel.card.effort_step_failed",
                extra={"channel": ctx.binding.resource.name},
                exc_info=True,
            )
    await ctx.show(card)
    return True
