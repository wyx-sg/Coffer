"""The messages a `/stop` left on hold, and the two buttons that settle them
(spec channels "Continue or discard the messages a stop held").

A stop pauses the conversation's pending queue (spec chat "Pause the pending
queue on interrupt"): what was queued behind the stopped turn waits rather than
running on. Sending anything resumes it, as before; the stopped line and the
`/status` card also offer Continue (run them, in order) and Discard (throw them
away), so a stop never leaves the owner with no way to drop what they had
queued.

A button carries the conversation's id (``held:go:<id>``, ``held:drop:<id>``):
after `/new` the held queue still belongs to the conversation that was stopped,
not the one the chat is bound to now. A tap is honoured only for a conversation
of this chat thread's own history, so a forged or stale button cannot reach
another chat's queue.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.channel.selection_cards import callback_fits
from coffer.domain.channel.envelopes import ChoiceButton

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["HELD_KIND", "apply_held", "held_buttons", "held_state"]

#: The tap kind of the Continue and Discard buttons.
HELD_KIND = "held"
_CONTINUE = "go"
_DISCARD = "drop"
#: How far back the thread's history is searched for the tapped conversation.
_HISTORY_LIMIT = 100


def held_buttons(conversation_id: str) -> list[ChoiceButton]:
    """Continue and Discard for ``conversation_id``'s held messages."""
    buttons = [
        ChoiceButton(label="▶ Continue", value=f"{HELD_KIND}:{_CONTINUE}:{conversation_id}"),
        ChoiceButton(label="Discard", value=f"{HELD_KIND}:{_DISCARD}:{conversation_id}"),
    ]
    return [b for b in buttons if callback_fits(b.value)]


def held_state(count: int) -> str:
    """``⏸ 2 on hold`` — the `/status` word for messages a stop held."""
    return f"⏸ {count} on hold"


def _messages(count: int) -> str:
    return f"{count} queued message" + ("" if count == 1 else "s")


async def apply_held(ctx: CommandContext, value: str) -> None:
    """A tap on Continue or Discard (``value`` is ``go:<id>`` or ``drop:<id>``)."""
    action, _, conversation_id = value.partition(":")
    if action not in (_CONTINUE, _DISCARD) or not conversation_id:
        return
    history = await ctx.commands._threads.history(
        ctx.resource_uid, ctx.chat_id, ctx.conversation_thread_id, limit=_HISTORY_LIMIT
    )
    turns = ctx.commands._turns
    if conversation_id not in history or not turns.held(conversation_id):
        await ctx.say("Nothing is on hold any more.")
        return
    if action == _CONTINUE:
        count = await turns.resume_held(conversation_id)
        await ctx.say(f"▶ Continuing {_messages(count)}.")
    else:
        count = turns.drop_held(conversation_id)
        await ctx.say(f"🗑 Discarded {_messages(count)}.")
