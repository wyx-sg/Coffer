"""`/status` and `/help` (spec channels "Report the chat's state as a status
card" and "List the commands with /help").

`/status` names things, never ids: the conversation's title (or a parallel
thread's mark), then one line with the agent, model and directory by
the names a person reads, and whether a turn is running, how many messages wait,
or how many a stop left on hold, then the chat's parallel threads (spec channels
"Open parallel conversations beside a direct chat"), the open ones only; in a
closed thread its state reads ``Closed``, then the scheduled tasks waiting in
the conversation, each with a Cancel button. `/status` works only in a direct
chat. Its card carries only what acts on what it shows: Stop while a turn
runs, Continue and Discard while messages are on hold, then Model and Dir; a
transport without buttons, or one that refuses the card, gets the same body as
text.

`/help` is text — one line per command — with no buttons: a list to read, not
a menu to tap (the platform's own command menu is that, where it has one).

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.channel.command_cards import STATUS_ACTIONS, command_card
from coffer.application.channel.command_text import settings_line
from coffer.application.channel.held_queue import held_buttons, held_state
from coffer.application.channel.parallel_threads import thread_lines
from coffer.application.channel.status_tasks import task_lines
from coffer.domain.channel.commands import help_text
from coffer.domain.channel.envelopes import ChoiceButton

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["cmd_help", "cmd_status"]


async def cmd_help(ctx: CommandContext, _text: str = "") -> None:
    """The roster as text, one line per command."""
    await ctx.say(help_text(group=ctx.chat_kind == "group"))


def _state(running: bool, queued: int, held: int) -> str:
    """``Running · 2 waiting``, ``Running``, ``2 waiting``, ``⏸ 2 on hold``
    (also after ``Running`` while the stopped turn winds down) or ``Idle``."""
    parts = ["Running"] if running else []
    if held:
        parts.append(held_state(held))
    elif queued:
        parts.append(f"{queued} waiting")
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
    turns = ctx.commands._turns
    queued = len(turns.pending(bound)) if bound is not None else 0
    held = turns.held(bound) if bound is not None else 0
    # A closed parallel thread runs nothing more (see "Open parallel
    # conversations beside a direct chat"), so its state is just that.
    closed = row is not None and row.parallel_closed
    lines = [
        title,
        await settings_line(ctx.commands, settings),
        "Closed" if closed else _state(running, queued, held),
    ]
    lines += await thread_lines(ctx)
    # What waits to run here (spec channels "List and cancel a chat's
    # scheduled tasks from /status").
    scheduled, cancels = await task_lines(ctx)
    lines += scheduled
    body = "\n".join(lines)
    lead = [ChoiceButton(label="Stop", value="cmd:stop")] if running else []
    if held and bound is not None:
        lead += held_buttons(bound)
    lead += cancels
    card = command_card(title="Status", text=body, actions=STATUS_ACTIONS, lead=lead)
    await ctx.answer(card, f"Status\n{body}")
