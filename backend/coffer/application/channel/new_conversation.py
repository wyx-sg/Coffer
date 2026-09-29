"""`/new [agent]` — a fresh conversation on the chat's settings (spec channels
"Answer the conversation commands from any paired chat", "Switch the agent with
/new" and "Keep a chat's settings across its conversations").

``/new`` keeps the thread's sticky agent, model, effort and directory — the
conversation opener applies them. ``/new <agent>`` switches the agent first,
named the way a person sees it (display name or resource-style name, see
``command_text.resolve_agent``) and only among the agents the channel's scope
admits (spec channels "Limit the agents a channel may drive to its scope").
Switching the agent drops the sticky model and effort — a model of one agent
is not a model of another — and keeps the directory.

In a SeaTalk group's main chat nothing is opened: ``/new <agent>`` sets the
group's default agent and bare ``/new`` says what the defaults are (spec
channels "Set a group's defaults from its main chat").

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["cmd_new", "open_fresh"]


async def cmd_new(ctx: CommandContext, text: str) -> None:
    typed = " ".join(text.split()[1:])
    if typed:
        key = resolve_agent(ctx.binding, ctx.commands._agents, typed)
        if key is None:
            await ctx.say(unknown_agent(ctx.binding, ctx.commands._agents, typed))
            return
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
    elif ctx.group_main:
        line = await settings_line(ctx.commands, await ctx.settings())
        await ctx.say(
            f"Defaults for new threads in this group: {line}\n"
            "Send /new <agent>, /model … or /dir … here to change them."
        )
        return
    if await open_fresh(ctx):
        line = await settings_line(ctx.commands, await ctx.settings())
        await ctx.say(f"🆕 New conversation · {line}")


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
