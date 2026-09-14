"""`/save`: land a chat attachment in a knowledge collection (spec knowledge
FR-036 — the phone and the Knowledge page are two ends of one entrance).

Free functions beside ``commands.py``, split out purely for that file's size
budget, exactly like ``card_delivery.py`` was: they take the owning
``ChannelCommands`` as their first argument and read its ports
(``_threads``/``_collections``/``_ingest``) the same way ``card_delivery``
already reads ``_agents``/``_conversations``/``_model_suggestions``.
"""

from __future__ import annotations

import logging
import pathlib
from asyncio import to_thread
from typing import TYPE_CHECKING, Any

from coffer.application.channel.agent_routing import effective_agent
from coffer.application.channel.ports import ChannelBinding, ChannelPeer
from coffer.application.channel.selection_cards import collection_card

if TYPE_CHECKING:
    from coffer.application.channel.commands import ChannelCommands, SafeSend

_logger = logging.getLogger(__name__)


async def cmd_save(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    text: str,
    session: Any,
    send: SafeSend,
    *,
    chat_kind: str = "direct",
    thread_id: str = "",
) -> None:
    """Save the pending document — the one most recently sent in this
    chat/thread — into a collection. `/save` is a plain text command (never a
    caption: an attachment's caption is a normal message, not a command,
    exactly like every other slash word — see ``inbound.py``), so it always
    follows the document as its own message, optionally naming the collection.

    The collection is confirmed, never guessed (FR-036): a name that is both
    known and visible to this thread's agent is used outright — the owner
    already confirmed it by typing it — anything else (no name, or one that
    doesn't resolve) falls back to a selection card so the tap itself is the
    confirmation.
    """
    # Deferred to break the module cycle: ``card_delivery`` calls
    # ``apply_save_collection`` below (a card tap is a confirmed choice), so
    # this module cannot import it back at load time.
    from coffer.application.channel.card_delivery import deliver_card

    pending = session.pending_document
    if pending is None:
        await send(
            binding,
            peer.chat_id,
            "⚠️ No document to save — send one, then /save.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    row = await commands._threads.get(binding.resource_id, peer.chat_id, thread_id)
    agent_key = effective_agent(binding, row.preferred_agent if row is not None else None)
    parts = text.split(maxsplit=1)
    named = parts[1].strip() if len(parts) > 1 else ""
    if named:
        visible = await commands._collections.visible_collections(agent_key)
        if named in visible:
            await apply_save_collection(
                commands,
                binding,
                peer,
                named,
                session,
                send,
                chat_kind=chat_kind,
                thread_id=thread_id,
            )
            return
        # Said up front, as its own message — a card shown right after must
        # never leave the reason for it unexplained (it otherwise looks like a
        # confirmation card for nothing in particular).
        await send(
            binding,
            peer.chat_id,
            f"Unknown collection '{named}'.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
    visible = await commands._collections.visible_collections(agent_key)
    if not visible:
        await send(
            binding,
            peer.chat_id,
            "No collections yet — create one on the Knowledge page first.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    card = collection_card(choices=visible)
    if binding.adapter.capabilities.supports_buttons and await deliver_card(
        binding, peer, card, chat_kind=chat_kind, thread_id=thread_id
    ):
        return
    listing = "\n".join(f"• {name}" for name in visible)
    await send(
        binding,
        peer.chat_id,
        f"Which collection? Reply /save <name>:\n{listing}",
        chat_kind=chat_kind,
        thread_id=thread_id,
    )


async def apply_save_collection(
    commands: ChannelCommands,
    binding: ChannelBinding,
    peer: ChannelPeer,
    collection: str,
    session: Any,
    send: SafeSend,
    *,
    chat_kind: str = "direct",
    thread_id: str = "",
) -> None:
    """Ingest the pending document into ``collection``. Shared by the text
    ``/save <name>`` path (a name the owner already confirmed by typing an
    existing one) and a collection-card tap (confirmed by the tap itself).

    The pending document is consumed either way, success or failure: a
    conversion failure leaves the collection exactly as it was (the ingest
    service's own guarantee — nothing is papered over here), and retrying the
    same bytes against the same failure is never useful, so the owner is told
    to send the document again rather than the card silently offering another
    collection for a file that will fail there too.
    """
    pending = session.pending_document
    if pending is None:
        await send(
            binding,
            peer.chat_id,
            "⚠️ Nothing pending to save anymore — send the document again.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    session.pending_document = None
    try:
        data = await to_thread(pathlib.Path(pending.path).read_bytes)
    except OSError:
        await send(
            binding,
            peer.chat_id,
            f"⚠️ Couldn't read '{pending.filename}' anymore — send it again.",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    row = await commands._threads.get(binding.resource_id, peer.chat_id, thread_id)
    agent_key = effective_agent(binding, row.preferred_agent if row is not None else None)
    try:
        doc = await commands._ingest.ingest(
            collection=collection,
            filename=pending.filename,
            data=data,
            actor="user",
            agent=agent_key,
        )
    except Exception as e:
        # The ingest service's own exceptions (UnsupportedDocument,
        # UploadTooLarge, an unknown/unauthorized collection) are all
        # one-line-message-carrying by design — that message IS the reason,
        # never a stack trace. Logged here (with the trace) for the daemon
        # log; the chat only ever sees the former.
        _logger.warning(
            "channel.save.failed",
            extra={"channel": binding.name, "collection": collection},
            exc_info=True,
        )
        await send(
            binding,
            peer.chat_id,
            f"⚠️ Couldn't save '{pending.filename}': {e}",
            chat_kind=chat_kind,
            thread_id=thread_id,
        )
        return
    await send(
        binding,
        peer.chat_id,
        f"📄 Saved '{doc.title}' to {collection} → {doc.path}",
        chat_kind=chat_kind,
        thread_id=thread_id,
    )


__all__ = ["apply_save_collection", "cmd_save"]
