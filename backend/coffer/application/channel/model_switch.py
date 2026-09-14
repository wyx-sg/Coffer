"""The `/model` switch — report or set the next-turn model, same conversation. Split out of
``commands.py`` purely for that file's size budget, exactly like
``document_save.py``: free functions taking the owning ``ChannelCommands`` as
their first argument, reading its ports the same way.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from coffer.application.channel.agent_routing import effective_agent
from coffer.application.channel.card_delivery import deliver_card
from coffer.application.channel.conversation_ops import (
    ensure_conversation,
    explain_conversation_error,
)
from coffer.application.channel.ports import ChannelBinding, ChannelPeer
from coffer.application.channel.selection_cards import model_card
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands, SafeSend


async def cmd_model(
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
    if len(parts) < 2:
        # Show the current model. Coffer-managed CLI agents own their own
        # model namespace (the builtin model-registry agent is retired),
        # so we just report what will be passed through to the agent's CLI.
        cfg = await commands._conversations.get_agent_config(conversation_id)
        current = cfg.model or "(CLI default)"
        if binding.adapter.capabilities.supports_buttons:
            row = await commands._threads.get(binding.resource_id, peer.chat_id, thread_id)
            key = effective_agent(binding, row.preferred_agent if row is not None else None)
            picks = await commands._model_suggestions.suggest(key)
            card = model_card(current=cfg.model, picks=picks)
            # Same fallback as /agent: a refused card degrades to text.
            if await deliver_card(binding, peer, card, chat_kind=chat_kind, thread_id=thread_id):
                return
        await send(
            binding,
            peer.chat_id,
            f"Model: {current}\n(passed through to the agent's CLI)",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    await apply_model(
        commands, binding, peer, parts[1], send, chat_kind=chat_kind, thread_id=thread_id
    )


async def apply_model(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    name: str,
    send: SafeSend,
    *,
    chat_kind: str = "direct",
    thread_id: str = "",
) -> None:
    """The parametric switch: set the next-turn model on the peer's
    conversation. Shared by the text ``/model <name>`` path and a card tap.

    Pure passthrough: ANY name reaches the CLI verbatim, whose namespace we
    do not own, so a bad one surfaces as its own error next turn. Nothing is
    refused here — a channel curates no models."""
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
    await commands._conversations.set_agent_config(conversation_id, replace(cfg, model=name))
    await send(
        binding,
        peer.chat_id,
        f"🧠 Model set to '{name}' for the next turn.",
        chat_kind=chat_kind,
        thread_id=thread_id,
    )


# -- card tap → the same switch (owner gate enforced by the processor) ---------
