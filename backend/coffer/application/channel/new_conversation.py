"""`/new [agent]` — a fresh conversation on the chat's settings (spec channels
"Answer the conversation commands from any paired chat", "Switch the agent with
/new" and "Keep a chat's settings across its conversations").

``/new`` keeps the thread's sticky agent, model, effort and directory — the
conversation opener applies them. ``/new <agent>`` switches the agent first,
named the way a person sees it (display name or resource-style name, see
``command_text.resolve_agent``) and only among the agents the channel's scope
admits (spec channels "Limit the agents a channel may drive to its scope").
Switching the agent drops the sticky model and effort — a model of one agent
is not a model of another — and keeps the directory. The answer is one line —
agent · model · directory — as a card with Agent, Model and Dir buttons; the
Agent button opens the agent card, whose tap does what `/new <agent>` does.

In a SeaTalk group's main chat nothing is opened: ``/new <agent>`` sets the
group's default agent and bare ``/new`` says what the defaults are (spec
channels "Set a group's defaults from its main chat").

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.channel.agent_routing import routable_choices
from coffer.application.channel.command_cards import agent_card, new_card
from coffer.application.channel.command_text import (
    GROUP_DEFAULT_SUFFIX,
    agent_display,
    resolve_agent,
    settings_line,
    unknown_agent,
)
from coffer.application.channel.conversation_ops import (
    explain_conversation_error,
    open_conversation,
)
from coffer.application.channel.selection_cards import SelectionCard
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["apply_agent", "cmd_new", "current_agent_card", "open_fresh"]


async def cmd_new(ctx: CommandContext, text: str) -> None:
    typed = " ".join(text.split()[1:])
    if typed:
        key = resolve_agent(ctx.binding, ctx.commands._agents, typed)
        if key is None:
            await ctx.say(unknown_agent(ctx.binding, ctx.commands._agents, typed))
            return
        await apply_agent(ctx, key)
        return
    if ctx.group_main:
        line = await settings_line(ctx.commands, await ctx.settings())
        await ctx.say(
            f"Defaults for new threads in this group: {line}\n"
            "Send /new <agent>, /model … or /dir … here to change them."
        )
        return
    await _open_and_announce(ctx)


async def apply_agent(ctx: CommandContext, key: str) -> None:
    """Make ``key`` the thread's sticky agent and open a fresh conversation on
    it — what `/new <agent>` does, shared with the agent card's tap."""
    current = (await ctx.settings()).agent
    changed = key != current
    # A model/effort of one agent means nothing to another; the directory
    # is the agent's workplace and follows regardless.
    cleared = {"model": None, "effort": None} if changed else {}
    await ctx.commands._threads.set_preferences(
        ctx.resource_id, ctx.chat_id, ctx.conversation_thread_id, agent=key, **cleared
    )
    if ctx.group_main:
        name = agent_display(ctx.commands._agents, key)
        await ctx.say(f"🔀 Agent set to {name}{GROUP_DEFAULT_SUFFIX}.")
        return
    await _open_and_announce(ctx)


async def current_agent_card(ctx: CommandContext, *, page: int | None = None) -> SelectionCard:
    """The agent card on what is in effect now: the agents this channel may drive."""
    settings = await ctx.settings()
    choices = routable_choices(ctx.binding, ctx.commands._agents)
    return agent_card(current=settings.agent, choices=choices, page=page)


async def _open_and_announce(ctx: CommandContext) -> None:
    """Open the fresh conversation and answer with the one-line `/new` card."""
    if await open_fresh(ctx):
        line = await settings_line(ctx.commands, await ctx.settings())
        await ctx.show_or_say(new_card(line=line), f"🆕 New conversation · {line}")


async def open_fresh(ctx: CommandContext) -> bool:
    """Open a fresh conversation for the thread on its sticky settings;
    ``False`` after saying why it could not be opened."""
    try:
        await open_conversation(
            ctx.commands._conversations,
            ctx.commands._threads,
            ctx.binding,
            ctx.peer,
            ctx.conversation_thread_id,
            chat_kind=ctx.chat_kind,
        )
    except CofferError as e:
        await ctx.say(explain_conversation_error(e))
        return False
    return True
