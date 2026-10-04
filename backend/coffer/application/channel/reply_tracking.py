"""Remembering what a turn's reply was delivered as, so it can be withdrawn (spec
channels "Withdraw a bot reply on the owner's command").

A reply is more than one platform message: a long answer is cut into parts, the
files it carries and a details card are messages of their own. ``ReplyTracker``
collects the ids of every message one turn's reply produced and files them under
one ``reply_id`` once the reply is out, which is what ``/del`` and the 🗑 button
resolve. In a group the reply's last text message carries that button.

Only ids and times are kept — never what the reply said.

Application layer only: no infrastructure import here.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ReplyLedgerPort, ReplyRecord
from coffer.domain.channel.envelopes import ChannelCapabilities, ChoiceButton, SentMessage

__all__ = [
    "LEDGER_RETENTION",
    "WITHDRAW_KIND",
    "ReplyTracker",
    "SendReply",
    "trash_button",
]

_logger = logging.getLogger(__name__)

#: The callback namespace of the 🗑 button: ``del:<reply id>``.
WITHDRAW_KIND = "del"

#: How long a reply stays in the ledger: past the longest platform window
#: (SeaTalk's seven days) plus a day of margin, nothing can be withdrawn anyway.
LEDGER_RETENTION = timedelta(days=8)

#: Sends the reply's text into the turn's chat with ``buttons`` (possibly none).
SendReply = Callable[[str, Sequence[ChoiceButton]], Awaitable[SentMessage | None]]


def trash_button(reply_id: str) -> ChoiceButton:
    """The 🗑 button of a group reply."""
    return ChoiceButton(label="🗑", value=f"{WITHDRAW_KIND}:{reply_id}")


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

    def buttons(self) -> list[ChoiceButton]:
        """The 🗑 button a group reply carries, where the transport has buttons and
        can withdraw at all; none in a direct chat (the owner is alone there and has
        ``/del``)."""
        caps = self.capabilities
        if self.chat_kind == "group" and caps.supports_buttons and caps.withdraw_window_hours > 0:
            return [trash_button(self.reply_id)]
        return []

    def note(self, sent: SentMessage | None) -> None:
        """A message of the reply went out: remember it. A transport that cannot
        withdraw has nothing worth remembering."""
        if sent is not None and self.capabilities.withdraw_window_hours > 0:
            self.ids.extend(sent.all_ids)

    def note_file(self, sent: SentMessage | None) -> None:
        """An uploaded file of the reply. Only a transport that REMOVES messages can
        take a file back (a rewritten card cannot stand in for a file)."""
        if self.capabilities.withdraw_removes:
            self.note(sent)

    async def send(self, text: str) -> None:
        """Send ``text`` as part of the reply (the group's 🗑 button riding on it)."""
        self.note(await self.send_reply(text, self.buttons()))

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
