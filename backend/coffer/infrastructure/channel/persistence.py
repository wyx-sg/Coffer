"""Channel pairings as vault documents (spec vault-storage).

Which chats on a platform belong to a channel's owner is the person's, and it
travels: ``state/channel-peers/<channel name>.json``::

    {"channel_uid": "<uid>", "format_version": 1,
     "peers": [{"chat_id": "...", "sender_id": "...", "display_name": "...",
                "paired_at": "<iso>"}]}

``peers`` keeps pairing order, so "the first sender this channel knew" is the
first entry. The document follows its channel: moved when the channel is
renamed and deleted with it, in the channel's own commit.

The thread tables live in ``thread_persistence`` and the outbox in
``outbox_persistence`` (this file's size budget); both are re-exported here so
``persistence`` stays the one import that registers every channel table.
Per Contract 5 this module must not import from any other kind module.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.application.channel.store_ports import ChannelPeer
from coffer.infrastructure.vault.state_documents import StateDocuments

#: ``state/channel-peers/``.
AREA = "channel-peers"


def _time(raw: Any) -> datetime:
    if isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            value = None
        if value is not None:
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.fromtimestamp(0, tz=UTC)


def _peer(uid: str, raw: Any) -> ChannelPeer | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("chat_id"), str):
        return None
    sender = raw.get("sender_id")
    return ChannelPeer(
        resource_uid=uid,
        chat_id=raw["chat_id"],
        display_name=str(raw.get("display_name") or ""),
        paired_at=_time(raw.get("paired_at")),
        sender_id=sender if isinstance(sender, str) else "",
    )


def _entry(peer: ChannelPeer) -> dict[str, Any]:
    return {
        "chat_id": peer.chat_id,
        "sender_id": peer.sender_id,
        "display_name": peer.display_name,
        "paired_at": peer.paired_at.astimezone(UTC).isoformat(),
    }


class ChannelPeerRepo:
    """``ChannelPeerRepoPort`` over ``state/channel-peers/``.

    A channel may be paired to several chats — its DM and every group or
    thread it was added to — one entry per chat. ``upsert`` re-pairs one chat
    without disturbing any other. Every read either names its chat
    (``get_by_chat``) or says which of several it wants (``owner_peer``,
    ``list_by_resource``): a read that names neither is how a private
    notification ended up in a group chat.
    """

    def __init__(
        self,
        *,
        name_of: Callable[[str], str | None] = lambda _uid: None,
        home: Path | None = None,
    ) -> None:
        self._name_of = name_of
        self.documents = StateDocuments(AREA, "channel_uid", home=home)

    def _peers(self, uid: str) -> list[ChannelPeer]:
        raw = (self.documents.get(uid) or {}).get("peers")
        if not isinstance(raw, list):
            return []
        return [p for p in (_peer(uid, r) for r in raw) if p is not None]

    def _save(self, uid: str, peers: list[ChannelPeer], summary: str) -> None:
        if not peers:
            self.documents.remove(uid, summary=summary)
            return
        name = self._name_of(uid) or uid
        self.documents.put(uid, name, {"peers": [_entry(p) for p in peers]}, summary=summary)

    async def owner_peer(self, resource_uid: str) -> ChannelPeer | None:
        """The earliest-paired chat; ``chat_id`` breaks a tie, so the answer is
        the same on every call and on every machine holding the document."""
        peers = sorted(self._peers(resource_uid), key=lambda p: (p.paired_at, p.chat_id))
        return peers[0] if peers else None

    async def get_by_chat(self, resource_uid: str, chat_id: str) -> ChannelPeer | None:
        return next((p for p in self._peers(resource_uid) if p.chat_id == chat_id), None)

    async def list_by_resource(self, resource_uid: str) -> list[ChannelPeer]:
        return self._peers(resource_uid)

    async def owner_sender_id(self, resource_uid: str) -> str | None:
        return next((p.sender_id for p in self._peers(resource_uid) if p.sender_id), None)

    async def upsert(self, peer: ChannelPeer) -> None:
        await self.upsert_replacing(peer, ())

    async def upsert_replacing(self, peer: ChannelPeer, unpair: Sequence[str]) -> None:
        """One commit: the un-pairs and the save land together."""
        drop = {peer.chat_id, *unpair}
        peers = [p for p in self._peers(peer.resource_uid) if p.chat_id not in drop]
        self._save(peer.resource_uid, [*peers, peer], f"Paired chat {peer.chat_id}")

    async def delete_by_chat(self, resource_uid: str, chat_id: str) -> None:
        """Un-pair one chat. A no-op when it is already gone — two machines
        un-pairing the same chat is agreement, not a failure."""
        peers = self._peers(resource_uid)
        kept = [p for p in peers if p.chat_id != chat_id]
        if len(kept) != len(peers):
            self._save(resource_uid, kept, f"Un-paired chat {chat_id}")


# Re-exported at the end so the models above are defined first; importing this
# module registers every channel table on ``Base.metadata``.
from coffer.infrastructure.channel.outbox_persistence import (  # noqa: E402
    ChannelOutboxModel,
    ChannelOutboxRepo,
)
from coffer.infrastructure.channel.thread_persistence import (  # noqa: E402
    ChannelThreadConversationModel,
    ChannelThreadConversationRepo,
    ChannelThreadHistoryModel,
)

__all__ = [
    "AREA",
    "ChannelOutboxModel",
    "ChannelOutboxRepo",
    "ChannelPeerRepo",
    "ChannelThreadConversationModel",
    "ChannelThreadConversationRepo",
    "ChannelThreadHistoryModel",
]
