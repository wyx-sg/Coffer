"""Taking a bot reply back: ``/del`` and the 🗑 button (spec channels "Withdraw a
bot reply on the owner's command").

A reply in a group cannot be unsaid by the platform on its own, so the owner can
withdraw it: Telegram deletes the messages, SeaTalk (which has no delete)
rewrites each card into a neutral "Withdrawn" card. Both reach the same
``ReplyWithdrawal.withdraw``, which also owns the platform's window — past it
nothing can be done, and the owner is told so privately rather than in the chat.

Owner-only by construction: a typed command passes the same owner gate as every
command, and a button tap passes the card gate that refuses a non-owner before it
reaches here. Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.channel.ephemeral import safe_send
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import (
    ChannelPeerRepoPort,
    ReplyLedgerPort,
    ReplyRecord,
)
from coffer.domain.audit import AuditEventType

if TYPE_CHECKING:
    from coffer.application.channel.command_context import CommandContext

__all__ = ["ReplyWithdrawal", "cmd_del"]

_logger = logging.getLogger(__name__)


def _window_words(hours: float) -> str:
    return f"{round(hours / 24)} days" if hours >= 48 and hours % 24 == 0 else f"{hours:g} hours"


class ReplyWithdrawal:
    """Withdraws replies the ledger remembers, and tells the owner what it cannot."""

    def __init__(
        self,
        *,
        ledger: ReplyLedgerPort,
        audit: AuditService,
        peers: ChannelPeerRepoPort,
    ) -> None:
        self._ledger = ledger
        self._audit = audit
        self._peers = peers

    async def withdraw(self, binding: ChannelBinding, record: ReplyRecord, *, via: str) -> bool:
        """Withdraw every message of ``record``; ``True`` when it all went.

        Past the platform's window, or when the platform refuses some messages, the
        owner is told in their direct chat (never in the group, where it would
        itself be noise) and the messages that could not be taken stay on record.
        """
        caps = binding.adapter.capabilities
        window = timedelta(hours=caps.withdraw_window_hours)
        if caps.withdraw_window_hours <= 0:
            await self._tell_owner(binding, "🗑 This chat cannot withdraw bot replies.")
            return False
        if datetime.now(tz=UTC) - record.sent_at > window:
            await self._ledger.remove(record.reply_id)
            await self._tell_owner(
                binding,
                f"🗑 That reply is past the {_window_words(caps.withdraw_window_hours)} "
                "this platform allows, so it can no longer be withdrawn.",
            )
            return False
        failed: list[str] = []
        for message_id in record.message_ids:
            try:
                await binding.adapter.withdraw_message(
                    record.chat_id, message_id, chat_kind=record.chat_kind
                )
            except Exception:
                _logger.warning(
                    "channel.withdraw.failed",
                    extra={"channel": binding.resource.name},
                    exc_info=True,
                )
                failed.append(message_id)
        done = len(record.message_ids) - len(failed)
        if done:
            await self._audit.record(
                AuditEventType.CHANNEL_REPLY_WITHDRAWN.value,
                resource=binding.resource,
                actor="owner",
                details={"chat_id": record.chat_id, "messages": done, "via": via},
            )
        await self._ledger.remove(record.reply_id)
        if failed:
            await self._ledger.add(
                ReplyRecord(
                    reply_id=record.reply_id,
                    resource_uid=record.resource_uid,
                    chat_id=record.chat_id,
                    thread_id=record.thread_id,
                    chat_kind=record.chat_kind,
                    message_ids=tuple(failed),
                    sent_at=record.sent_at,
                )
            )
            await self._tell_owner(
                binding,
                f"⚠️ Could not withdraw {len(failed)} of {len(record.message_ids)} "
                "message(s) of that reply — the platform refused.",
            )
        return not failed

    async def tap(self, ctx: CommandContext, reply_id: str) -> None:
        """The 🗑 button under a reply. The card gate has already proved the tapper
        the owner; a reply this chat does not hold is ignored, and one the ledger has
        forgotten (past every window) is told privately."""
        record = await self._ledger.get(reply_id)
        if record is None:
            await self._tell_owner(
                ctx.binding, "🗑 That reply can no longer be withdrawn — it is past the window."
            )
            return
        if record.resource_uid != ctx.resource_uid or record.chat_id != ctx.chat_id:
            return
        await self.withdraw(ctx.binding, record, via="button")

    async def _tell_owner(self, binding: ChannelBinding, text: str) -> None:
        """Say ``text`` in the owner's direct chat."""
        owner = await self._peers.owner_peer(binding.resource.uid)
        if owner is None:
            return
        await safe_send(binding, owner.chat_id, text, chat_kind="direct")


async def cmd_del(ctx: CommandContext, text: str) -> None:
    """``/del``: withdraw the reply the command quotes, else the latest one in this
    chat or thread. Silent on success — the reply disappearing is the answer."""
    del text
    ledger = ctx.commands.replies
    if ctx.quoted_message_id:
        record = await ledger.find_by_message(ctx.resource_uid, ctx.chat_id, ctx.quoted_message_id)
        if record is None:
            await ctx.say("That is not a reply I can withdraw.")
            return
    else:
        # A group's main chat roots a thread per message, so "this thread" would
        # never hold a reply: it looks across the whole chat.
        thread = None if ctx.group_main or not ctx.thread_id else ctx.thread_id
        record = await ledger.latest(ctx.resource_uid, ctx.chat_id, thread)
        if record is None:
            await ctx.say("There is no reply of mine to withdraw here.")
            return
    await ctx.commands.withdrawal.withdraw(ctx.binding, record, via="command")
    caps = ctx.binding.adapter.capabilities
    if caps.withdraw_removes and ctx.command_message_id:
        # The owner's own ``/del`` goes too, where the platform lets the bot remove it.
        with contextlib.suppress(Exception):
            await ctx.binding.adapter.delete_message(ctx.chat_id, ctx.command_message_id)
