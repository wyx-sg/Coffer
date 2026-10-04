"""`/status` and `/help` — the two cards that end in the five actions (spec
channels "Report the chat's state as a status card" and "Offer the commands as
a help card").

`/status` names things, never ids: the conversation's title (or a parallel
thread's mark), then one line with the agent, model and directory by
the names a person reads, and whether a turn is running or how many wait, then
the chat's parallel threads (spec channels "Open parallel conversations beside
a direct chat"). `/status` works only in a direct chat; the help card lists
only the group commands in a group. The status card carries Stop (while a turn
runs), New, Model, Resume and Dir as ``cmd:`` buttons, the help card New, Stop,
Model, Status and Resume; a transport without buttons, or one that refuses the
card, gets the same body as text.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.channel.command_cards import (
    GROUP_HELP_ACTIONS,
    HELP_ACTIONS,
    STATUS_ACTIONS,
    command_card,
)
from coffer.application.channel.command_text import settings_line
from coffer.application.channel.parallel_threads import thread_lines
from coffer.domain.channel.commands import help_text

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["cmd_help", "cmd_status"]


async def cmd_help(ctx: CommandContext, _text: str = "") -> None:
    """The roster as text, with the five actions where the transport has buttons."""
    group = ctx.chat_kind == "group"
    body = help_text(group=group)
    actions = GROUP_HELP_ACTIONS if group else HELP_ACTIONS
    await ctx.answer(command_card(title="Commands", text=body, actions=actions), body)


def _state(running: bool, queued: int) -> str:
    """``Running · 2 waiting``, ``Running``, ``2 waiting`` or ``Idle``."""
    parts = (["Running"] if running else []) + ([f"{queued} waiting"] if queued else [])
    return " · ".join(parts) or "Idle"


async def cmd_status(ctx: CommandContext, _text: str = "") -> None:
    settings = await ctx.settings()
    row = await ctx.commands._threads.get(ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id)
    bound = row.active_conversation_id if row is not None else None
    conversation = settings.conversation
    mark = row.parallel_mark if row is not None else None
    title = mark or (str(conversation.title).strip() if conversation is not None else "")
    title = title or (
        "Untitled conversation" if conversation is not None else "No conversation yet"
    )
    running = ctx.session is not None and ctx.session.running_conversation_id is not None
    # The queue is the conversation's own (spec chat "Queue messages sent during
    # a turn") — the same one the web's pending chips show.
    queued = len(ctx.commands._turns.pending(bound)) if bound is not None else 0
    lines = [
        title,
        await settings_line(ctx.commands, settings),
        _state(running, queued),
    ]
    lines += await thread_lines(ctx)
    body = "\n".join(lines)
    actions = [a for a in STATUS_ACTIONS if running or a[1] != "stop"]
    await ctx.answer(command_card(title="Status", text=body, actions=actions), f"Status\n{body}")
