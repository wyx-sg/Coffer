"""`/kb`: land a chat attachment in a knowledge collection (spec channels "Save a sent
document into a collection" — the phone and the Knowledge page are two ends of one
entrance).

Free functions over a :class:`CommandContext`, reading the owning
``ChannelCommands``' ports (``_collections``/``_ingest``). `/kb` stays a
reserved word while the ``knowledge`` feature is off — it answers why nothing was
saved — but the help text and the menus offer it only while knowledge is on.
"""

from __future__ import annotations

import logging
import pathlib
from asyncio import to_thread
from typing import TYPE_CHECKING

from coffer.application.channel.selection_cards import collection_card

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

_logger = logging.getLogger(__name__)

#: What `/kb` answers while the ``knowledge`` feature is switched off (spec
#: experimental-features "Withdraw what a switched-off feature put in front of
#: agents"). The pending document is kept, so a `/kb` after switching it on
#: still has something to save.
KNOWLEDGE_OFF = (
    "⚠️ Knowledge is switched off on this machine, so nothing was saved. "
    "Switch it on in Coffer's Settings › Features."  # noqa: RUF001
)


async def _refuse_if_knowledge_off(ctx: CommandContext) -> bool:
    """Answer the notice and return True when knowledge is switched off."""
    if ctx.commands._knowledge_enabled():
        return False
    await ctx.say(KNOWLEDGE_OFF)
    return True


async def cmd_kb(ctx: CommandContext, text: str) -> None:
    """Save the pending document — the one most recently sent in this
    chat/thread — into a collection. `/kb` is a plain text command (never a
    caption: an attachment's caption is a normal message), so it always follows
    the document as its own message, optionally naming the collection.

    The collection is confirmed, never guessed (see "Save a sent document into a
    collection"): a name that is an existing collection is used outright — the owner
    already confirmed it by typing it — anything else (no name, or one that doesn't
    resolve) falls back to a selection card so the tap itself is the confirmation.
    """
    if await _refuse_if_knowledge_off(ctx):
        return
    session = ctx.session
    if session is None or session.pending_document is None:
        await ctx.say("⚠️ No document to save — send one, then /kb.")
        return
    # Asked once, and the same question either way: `/kb <name>` checks the
    # name against it, and a `/kb` with no usable name offers it as a card.
    known = await ctx.commands._collections.collection_names()
    parts = text.split(maxsplit=1)
    named = parts[1].strip() if len(parts) > 1 else ""
    if named:
        if named in known:
            await apply_save_collection(ctx, named)
            return
        # Said up front, as its own message — a card shown right after must
        # never leave the reason for it unexplained.
        await ctx.say(f"Unknown collection '{named}'.")
    if not known:
        await ctx.say("No collections yet — create one on the Knowledge page first.")
        return
    listing = "\n".join(f"• {name}" for name in known)
    await ctx.show_or_say(
        collection_card(choices=known), f"Which collection? Reply /kb <name>:\n{listing}"
    )


async def apply_save_collection(ctx: CommandContext, collection: str) -> None:
    """Ingest the pending document into ``collection``. Shared by the text
    ``/kb <name>`` path (a name the owner already confirmed by typing an
    existing one) and a collection-card tap (confirmed by the tap itself).

    The pending document is consumed either way, success or failure: a
    conversion failure leaves the collection exactly as it was (the ingest
    service's own guarantee), and retrying the same bytes against the same
    failure is never useful, so the owner is told to send the document again.

    A card tapped after knowledge was switched off saves nothing either.
    """
    if await _refuse_if_knowledge_off(ctx):
        return
    session = ctx.session
    pending = session.pending_document if session is not None else None
    if pending is None:
        await ctx.say("⚠️ Nothing pending to save anymore — send the document again.")
        return
    session.pending_document = None
    try:
        data = await to_thread(pathlib.Path(pending.path).read_bytes)
    except OSError:
        await ctx.say(f"⚠️ Couldn't read '{pending.filename}' anymore — send it again.")
        return
    try:
        doc = await ctx.commands._ingest.ingest(
            collection=collection,
            filename=pending.filename,
            data=data,
            actor="user",
        )
    except Exception as e:
        # The ingest service's own exceptions (UnsupportedDocument,
        # UploadTooLarge, an unknown collection) are all
        # one-line-message-carrying by design — that message IS the reason,
        # never a stack trace. Logged here (with the trace) for the daemon
        # log; the chat only ever sees the former.
        _logger.warning(
            "channel.save.failed",
            extra={"channel": ctx.binding.resource.name, "collection": collection},
            exc_info=True,
        )
        await ctx.say(f"⚠️ Couldn't save '{pending.filename}': {e}")
        return
    await ctx.say(f"📄 Saved \u2018{doc.title}\u2019 to {collection}.")


__all__ = ["KNOWLEDGE_OFF", "apply_save_collection", "cmd_kb"]
