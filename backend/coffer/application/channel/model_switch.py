"""`/model` — the model, one command (spec channels "Switch the model from
chat").

``/model`` alone is a card of the agent's paginated catalogue; a tap sets the
model. Typed forms: ``/model <name>`` sets the model, ``/model default`` clears
it. A lone word is a model name.

The model is parametric — the SAME conversation runs its next turn on it — and
is remembered on the thread, so a fresh conversation opens on it too
(spec channels "Keep a chat's agent, model and directory across its conversations"). A model
name is matched against the catalogue's ids and shown names; anything else is
passed through verbatim, since the agent's CLI owns that namespace. In a SeaTalk
group's main chat only the group's defaults row is written (spec channels "Set
a group's defaults from its main chat").
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from coffer.application.channel.command_text import (
    model_display,
)
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.selection_cards import SelectionCard, model_card
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = [
    "apply_model",
    "cmd_model",
    "current_model_card",
    "say_model",
]


async def cmd_model(ctx: CommandContext, text: str) -> None:
    words = text.split()[1:]
    if not words:
        await _show(ctx)
        return
    if len(words) == 1 and words[0].lower() == "default":
        await _clear(ctx)
        return
    await apply_model(ctx, await _match_model(ctx, " ".join(words)))


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
    """Write ``values`` (``model``) to the conversation and the thread."""
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


async def apply_model(ctx: CommandContext, model: str) -> bool:
    """Set the model. Shared by the typed form and a card tap."""
    if not await _set(ctx, model=model):
        return False
    await say_model(ctx)
    return True


async def say_model(ctx: CommandContext) -> None:
    """``Model: Claude Sonnet 5.5 — from your next message``."""
    settings = await ctx.settings()
    model = settings.model
    shown = await model_display(ctx.commands, settings.agent, model) if model else "Default model"
    await ctx.say(f"Model: {shown}{_where(ctx)}")


async def _clear(ctx: CommandContext) -> None:
    if await _set(ctx, model=None):
        await ctx.say(f"Model: the agent's default{_where(ctx)}")


async def _show(ctx: CommandContext) -> None:
    """Bare `/model`: the model card, else the settings in text."""
    settings = await ctx.settings()
    labels = await ctx.commands._model_suggestions.model_labels(settings.agent)
    card = model_card(current=settings.model, picks=list(labels), labels=labels)
    if await ctx.show(card):
        return
    shown = await model_display(ctx.commands, settings.agent, settings.model)
    lines = [f"Model: {shown}"]
    if labels:
        lines.append("Available: " + ", ".join(label or i for i, label in labels.items()))
    lines.append("Send /model <name> or /model default.")
    await ctx.say("\n".join(lines))


async def current_model_card(ctx: CommandContext, *, page: int | None = None) -> SelectionCard:
    settings = await ctx.settings()
    labels = await ctx.commands._model_suggestions.model_labels(settings.agent)
    return model_card(
        current=settings.model,
        picks=list(labels),
        labels=labels,
        page=page,
    )
