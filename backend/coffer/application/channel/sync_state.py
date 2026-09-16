"""Channel pairing identity as a synced state area (spec vault-sync, spec channels).

A pairing says which chat on the platform belongs to the owner: the chat id,
the sender id the owner gate checks, and the name to show. Every one of those
is a fact about the **platform**, not about the machine holding the row — which
is why this area exists at all. Rebind a channel from the laptop to the desktop
and the desktop needs the same answers; without them the owner re-pairs from
their phone every time a channel moves, and a rebind is supposed to be one
click.

Channels travel between machines (spec channels ``## Where a channel runs``),
which is what makes the pairing worth publishing rather than re-deriving.

**What a conversation is doing never travels.** The conversation a chat is
driving, and the agent a thread has stuck to, live in
``channel_thread_conversations`` — per thread, on this machine, and not in this
area. Both name things local to one machine (a conversation row; an agent that
machine has installed), so publishing either would hand the other end an answer
it cannot use. A pairing arriving here therefore changes who the chat is, never
what it is in the middle of.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from coffer.application.channel.ports import ChannelPeer, ChannelPeerRepoPort
from coffer.application.resource_service import ResourceService

#: Directory under ``state/`` in the bundle.
AREA = "channel-peers"

#: A chat id is platform-chosen and may hold anything; a bundle path may not.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def doc_path(channel: str, chat_id: str) -> str:
    """The document's address, which is only an address.

    Sanitising is lossy on purpose — two chat ids could in principle collapse to
    one path — so the payload carries the true ids and the path is never parsed
    back into one. Deterministic, which is what keeps an unchanged vault
    producing an unchanged tree.
    """
    return f"{channel}/{_UNSAFE.sub('_', chat_id) or 'chat'}"


class ChannelPeerSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(self, resources: ResourceService, peers: ChannelPeerRepoPort) -> None:
        self._resources = resources
        self._peers = peers

    async def export_docs(self) -> list[tuple[str, dict[str, object]]]:
        docs: list[tuple[str, dict[str, object]]] = []
        for resource in await self._resources.list(kind="channel"):
            for peer in await self._peers.list_by_resource(resource.id):
                docs.append(
                    (
                        doc_path(resource.name, peer.chat_id),
                        {
                            "channel": resource.name,
                            "chat_id": peer.chat_id,
                            "display_name": peer.display_name,
                            "sender_id": peer.sender_id,
                            "paired_at": peer.paired_at.isoformat(),
                        },
                    )
                )
        return docs

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        by_name = {r.name: r.id for r in await self._resources.list(kind="channel")}
        for path, doc in docs:
            channel = str(doc.get("channel") or "")
            chat_id = str(doc.get("chat_id") or "")
            if not channel or not chat_id:
                # A document this build cannot read is not one it can apply.
                # Reported rather than silently dropped: the round holds the
                # path, so the next export cannot publish it as a deletion.
                errors.append((path, "pairing document is missing 'channel' or 'chat_id'"))
                continue
            resource_id = by_name.get(channel)
            if resource_id is None:
                # The channel itself has not landed here yet — the resource
                # documents and this area are applied path by path in one
                # round, in no guaranteed order. Held and retried, exactly as a
                # resource document that arrives before its credential is.
                errors.append((path, f"channel '{channel}' is not registered here yet"))
                continue
            try:
                await self._peers.upsert(
                    ChannelPeer(
                        resource_id=resource_id,
                        chat_id=chat_id,
                        display_name=str(doc.get("display_name") or ""),
                        paired_at=_parse_time(doc.get("paired_at")),
                        sender_id=_opt_str(doc.get("sender_id")),
                    )
                )
            except Exception as e:
                errors.append((path, str(e)))
        return errors

    async def delete_docs(self, rels: list[str]) -> None:
        """Unpairing propagates: somebody actually un-paired that chat.

        The path is not reversible into a chat id, so the peers of the named
        channel are re-addressed the same way the export addressed them and the
        one that matches goes. A path naming a channel this machine does not
        hold is nothing to do here.
        """
        wanted = set(rels)
        by_name = {r.name: r.id for r in await self._resources.list(kind="channel")}
        for rel in wanted:
            channel = rel.split("/", 1)[0]
            resource_id = by_name.get(channel)
            if resource_id is None:
                continue
            for peer in await self._peers.list_by_resource(resource_id):
                if doc_path(channel, peer.chat_id) == rel:
                    await self._peers.delete_by_chat(resource_id, peer.chat_id)


def _opt_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _parse_time(value: object) -> datetime:
    """The pairing time, or now when the document does not say.

    Never fatal: ``paired_at`` is displayed, not decided on, and refusing a
    pairing over an unparseable timestamp would cost the owner a re-pair to
    fix a date on a card.
    """
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(tz=UTC)
