"""The `/effort` switch — report or set the next-turn reasoning level, same
conversation.

`/model`'s sibling in every way that matters, and split out of ``commands.py``
for the same reason (that file's size budget): free functions taking the owning
``ChannelCommands`` as their first argument, reading its ports the same way.

WHY IT IS A SECOND COMMAND rather than an argument to `/model`. The level is not
part of the model name — both managed agents take it as their own field, Codex
on ``turn/start`` and Claude Code as the CLI's ``--effort`` — so a combined
``/model opus:xhigh`` would invent a syntax neither agent uses and would make
the two impossible to change independently. The web surface reached the same
answer: a picker beside the model picker, not inside it.

WHY THERE IS NO CLEARING FORM. Exactly as `/model` has none: this is raw
passthrough, and a reserved word meaning "unset" would be a level name Coffer
had made up in a namespace it does not own. The way back to the agent's own
default from a chat is `/new`, which opens a fresh conversation carrying no
overrides at all.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from coffer.application.channel.agent_routing import effective_agent
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.selection_cards import effort_card
from coffer.application.channel.store_ports import ChannelPeer
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands, SafeSend

#: What `/effort` says for an agent whose models take no such setting. Naming
#: the model matters: the levels belong to the model in effect, so "this agent
#: has none" is only true of the one the conversation is actually on.
NO_LEVELS = (
    "This conversation's model takes no reasoning-effort setting, so there is nothing to choose."
)


async def cmd_effort(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    text: str,
    send: SafeSend,
    *,
    chat_kind: str = "direct",
    thread_id: str = "",
) -> None:
    try:
        conversation_id = await ensure_conversation(
            commands._conversations, commands._threads, binding, peer, thread_id
        )
    except CofferError as e:
        await send(
            binding,
            peer.chat_id,
            explain_conversation_error(e),
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    parts = text.split()
    if len(parts) >= 2:
        await apply_effort(
            commands, binding, peer, parts[1], send, chat_kind=chat_kind, thread_id=thread_id
        )
        return
    # Report what is in effect. The levels are asked for against the model this
    # conversation is actually on, so the answer describes the choice the user
    # would be making rather than the agent in the abstract.
    cfg = await commands._conversations.get_agent_config(conversation_id)
    row = await commands._threads.get(binding.resource.id, peer.chat_id, thread_id)
    key = effective_agent(binding, row.preferred_agent if row is not None else None)
    levels = await commands._model_suggestions.efforts(key, cfg.model)
    # Deferred to break the module cycle: ``card_delivery`` calls
    # ``apply_effort`` below (a card tap is a confirmed choice), so this module
    # cannot import it back at load time — same shape as ``document_save``.
    from coffer.application.channel.card_delivery import deliver_card

    if levels and binding.adapter.capabilities.supports_buttons:
        card = effort_card(current=cfg.effort, levels=levels)
        # Same fallback as /agent and /model: a refused card degrades to text.
        if await deliver_card(binding, peer, card, chat_kind=chat_kind, thread_id=thread_id):
            return
    if not levels:
        await send(binding, peer.chat_id, NO_LEVELS, chat_kind=chat_kind, thread_id=thread_id)
        return
    current = cfg.effort or "(agent default)"
    await send(
        binding,
        peer.chat_id,
        f"Effort: {current}\nAvailable: {', '.join(levels)}",
        chat_kind=chat_kind,
        thread_id=thread_id,
    )


async def apply_effort(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    level: str,
    send: SafeSend,
    *,
    chat_kind: str = "direct",
    thread_id: str = "",
) -> None:
    """Set the next-turn reasoning level on the peer's conversation. Shared by
    the text ``/effort <level>`` path and a card tap.

    Pure passthrough, like ``apply_model``: ANY level reaches the agent
    verbatim, whose namespace we do not own, so a level this account cannot run
    fails where every other unusable choice fails — at the CLI, next turn.
    """
    try:
        conversation_id = await ensure_conversation(
            commands._conversations, commands._threads, binding, peer, thread_id
        )
    except CofferError as e:
        await send(
            binding,
            peer.chat_id,
            explain_conversation_error(e),
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    cfg = await commands._conversations.get_agent_config(conversation_id)
    await commands._conversations.set_agent_config(conversation_id, replace(cfg, effort=level))
    await send(
        binding,
        peer.chat_id,
        f"🎚 Effort set to '{level}' for the next turn.",
        chat_kind=chat_kind,
        thread_id=thread_id,
    )


__all__ = ["NO_LEVELS", "apply_effort", "cmd_effort"]
