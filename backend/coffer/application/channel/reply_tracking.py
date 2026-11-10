"""Remembering what a turn's reply was delivered as, so it can be withdrawn (spec
channels "Withdraw a bot reply on the owner's command").

A reply is more than one platform message: a long answer is cut into parts, and
the files it carries are messages of their own. ``ReplyTracker``
collects the ids of every message one turn's reply produced and files them under
one ``reply_id`` once the reply is out, which is what ``/del`` resolves. A reply
is plain text with no buttons, so only a transport that can delete a message
(Telegram) has anything worth filing.

Only ids and times are kept — never what the reply said.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ReplyLedgerPort, ReplyRecord
from coffer.domain.channel.envelopes import ChannelCapabilities, SentMessage

__all__ = [
    "LEDGER_RETENTION",
    "ReplyTracker",
    "SendReply",
]

_logger = logging.getLogger(__name__)

#: How long a reply stays in the ledger: past the longest platform window
#: (Telegram's 48 hours) plus a margin, nothing can be withdrawn anyway.
LEDGER_RETENTION = timedelta(days=3)

#: Sends the reply's text into the turn's chat, as plain text.
SendReply = Callable[[str], Awaitable[SentMessage | None]]


@dataclass
class ReplyTracker:
    """One turn's reply, as the platform messages it became."""

    ledger: ReplyLedgerPort
    resource_uid: str
    chat_id: str
    thread_id: str
    chat_kind: str
    capabilities: ChannelCapabilities
    send_reply: SendReply
    reply_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ids: list[str] = field(default_factory=list)

    @classmethod
    def for_turn(
        cls,
        ledger: ReplyLedgerPort,
        binding: ChannelBinding,
        chat_id: str,
        thread_id: str,
        chat_kind: str,
        send_reply: SendReply,
    ) -> ReplyTracker:
        """The tracker of one turn's reply into ``chat_id`` through ``binding``."""
        return cls(
            ledger=ledger,
            resource_uid=binding.resource.uid,
            chat_id=chat_id,
            thread_id=thread_id,
            chat_kind=chat_kind,
            capabilities=binding.adapter.capabilities,
            send_reply=send_reply,
        )

    def note(self, sent: SentMessage | None) -> None:
        """A message of the reply went out — text or file: remember it. A
        transport that cannot withdraw has nothing worth remembering."""
        if sent is not None and self.capabilities.withdraw_window_hours > 0:
            self.ids.extend(sent.all_ids)

    async def send(self, text: str) -> None:
        """Send ``text`` as part of the reply, as plain text."""
        self.note(await self.send_reply(text))

    async def commit(self) -> None:
        """File what the reply turned out to be. Best-effort: a ledger that fails
        costs the owner the ability to withdraw this one reply, never the reply."""
        if not self.ids:
            return
        now = datetime.now(tz=UTC)
        try:
            await self.ledger.add(
                ReplyRecord(
                    reply_id=self.reply_id,
                    resource_uid=self.resource_uid,
                    chat_id=self.chat_id,
                    thread_id=self.thread_id,
                    chat_kind=self.chat_kind,
                    message_ids=tuple(dict.fromkeys(self.ids)),
                    sent_at=now,
                )
            )
            await self.ledger.prune(now - LEDGER_RETENTION)
        except Exception:
            _logger.warning("channel.reply_ledger.failed", exc_info=True)
