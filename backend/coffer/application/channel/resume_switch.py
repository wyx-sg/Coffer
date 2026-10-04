"""`/resume [n]` — reopen an earlier conversation of this chat thread (spec
channels "Resume an earlier conversation from chat").

The list is the thread's own history (``channel_thread_history``), newest
first, at most 20: nothing opened on the web or in another chat is offered,
and a tap is checked against the same history before anything is rebound, so
a forged or stale button can never reach another chat's conversation. A
conversation deleted since is skipped. `/resume n` and a tap rebind the thread
to the chosen conversation; its next message continues it.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coffer.application.channel.command_text import age, agent_display
from coffer.application.channel.selection_cards import SelectionCard, resume_card
from coffer.domain.chat.errors import ConversationNotFound

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = [
    "NOTHING_TO_RESUME",
    "apply_resume",
    "cmd_resume",
    "current_resume_card",
]

#: How many earlier conversations are offered.
HISTORY_LIMIT = 20
NOTHING_TO_RESUME = "Nothing to resume — this chat has no earlier conversation yet."


async def _entries(ctx: CommandContext) -> tuple[list[Any], str | None]:
    """The thread's conversations still in existence, newest first, and the
    one it is bound to now."""
    threads = ctx.commands._threads
    ids = await threads.history(
        ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id, limit=HISTORY_LIMIT
    )
    found = []
    for conversation_id in ids:
        try:
            found.append(await ctx.commands._conversations.get_conversation(conversation_id))
        except ConversationNotFound:
            continue
    row = await threads.get(ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id)
    return found, row.active_conversation_id if row is not None else None


def _title(conversation: Any) -> str:
    return str(conversation.title or "").strip() or "Untitled"


def _listing(
    ctx: CommandContext, found: list[Any], active: str | None, *, buttons: bool = True
) -> str:
    lines = ["Send /resume <n> or tap one:" if buttons else "Send /resume <n> to reopen one:"]
    for n, conv in enumerate(found, start=1):
        agent = agent_display(ctx.commands._agents, conv.agent_key)
        tick = " ✓" if str(conv.id) == active else ""
        lines.append(f"{n} · {_title(conv)} — {agent} · {age(conv.updated_at)}{tick}")
    return "\n".join(lines)


async def cmd_resume(ctx: CommandContext, text: str) -> None:
    found, active = await _entries(ctx)
    if not found or (len(found) == 1 and str(found[0].id) == active):
        await ctx.say(NOTHING_TO_RESUME)
        return
    words = text.split()[1:]
    if words:
        index = int(words[0]) if words[0].isdigit() else 0
        if not 1 <= index <= len(found):
            await ctx.say(f"No conversation #{words[0]} — send /resume to see the list.")
            return
        await _rebind(ctx, found[index - 1])
        return
    listing = _listing(ctx, found, active)
    text = "Resume a conversation\n" + _listing(ctx, found, active, buttons=False)
    await ctx.show_or_say(_card(found, active, listing), text)


def _card(
    found: list[Any], active: str | None, listing: str, page: int | None = None
) -> SelectionCard:
    entries = [(str(conv.id), _title(conv)) for conv in found]
    return resume_card(header=listing, entries=entries, active=active, page=page)


async def current_resume_card(ctx: CommandContext, *, page: int | None = None) -> SelectionCard:
    found, active = await _entries(ctx)
    return _card(found, active, _listing(ctx, found, active), page)


async def apply_resume(ctx: CommandContext, conversation_id: str) -> None:
    """A tap on ``resume:<id>`` — honoured only for a conversation of THIS
    thread's history."""
    found, _active = await _entries(ctx)
    match = next((conv for conv in found if str(conv.id) == conversation_id), None)
    if match is None:
        await ctx.say("That conversation is not one of this chat's — send /resume for the list.")
        return
    await _rebind(ctx, match)


async def _rebind(ctx: CommandContext, conversation: Any) -> None:
    await ctx.commands._threads.set_active_conversation(
        ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id, str(conversation.id)
    )
    agent = agent_display(ctx.commands._agents, conversation.agent_key)
    await ctx.say(f"↩️ Resumed \u201c{_title(conversation)}\u201d with {agent}.")
