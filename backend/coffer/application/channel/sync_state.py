"""Channel pairing state as a synced area (spec 010 / ADR-043, slice 4).

Pairing identity (chat_id, sender_id, display name, preferred agent) is
platform-level, not machine-level — syncing it means rebinding a channel to
another machine needs no re-pairing. The machine-local conversation pointer
(``active_conversation_id``) never travels: conversations don't sync.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from coffer.application.channel.ports import ChannelPeer, ChannelPeerRepoPort
from coffer.application.resource_service import ResourceService

AREA = "channel-peers"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _doc_path(channel: str, chat_id: str) -> str:
    # The filename is only an address — the payload carries the true ids.
    return f"{channel}/{_UNSAFE.sub('_', chat_id) or 'chat'}"


class ChannelPeerSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(self, resources: ResourceService, peers: ChannelPeerRepoPort) -> None:
        self._resources = resources
        self._peers = peers

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        docs: list[tuple[str, dict[str, object]]] = []
        owned: list[str] = []
        for resource in await self._resources.list(kind="channel"):
            # We vouch only for channels we hold locally: their docs are
            # replaced (so unpairing propagates); docs of quarantined /
            # not-yet-imported channels stay untouched.
            owned.append(f"{resource.name}/")
            for peer in await self._peers.list_by_resource(resource.id):
                docs.append(
                    (
                        _doc_path(resource.name, peer.chat_id),
                        {
                            "channel": resource.name,
                            "chat_id": peer.chat_id,
                            "display_name": peer.display_name,
                            "sender_id": peer.sender_id,
                            "preferred_agent": peer.preferred_agent,
                            "paired_at": peer.paired_at.isoformat(),
                        },
                    )
                )
        return docs, owned

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[str]:
        errors: list[str] = []
        by_name = {r.name: r.id for r in await self._resources.list(kind="channel")}
        for path, doc in docs:
            try:
                channel = str(doc["channel"])
                chat_id = str(doc["chat_id"])
            except KeyError:
                continue  # malformed doc: skip, the owner re-exports it
            resource_id = by_name.get(channel)
            if resource_id is None:
                # Channel not present here (quarantined / not yet imported):
                # retried on the next run, like the resource docs themselves.
                continue
            try:
                existing = await self._peers.get_by_chat(resource_id, chat_id)
                raw_paired = doc.get("paired_at")
                paired_at = (
                    datetime.fromisoformat(str(raw_paired)) if raw_paired else datetime.now(tz=UTC)
                )
                raw_sender = doc.get("sender_id")
                raw_agent = doc.get("preferred_agent")
                await self._peers.upsert(
                    ChannelPeer(
                        resource_id=resource_id,
                        chat_id=chat_id,
                        display_name=str(doc.get("display_name") or ""),
                        paired_at=paired_at,
                        # Machine-local: conversations don't sync, so a pulled
                        # pairing must never clobber this machine's pointer.
                        active_conversation_id=(
                            existing.active_conversation_id if existing else None
                        ),
                        sender_id=str(raw_sender) if raw_sender else None,
                        preferred_agent=str(raw_agent) if raw_agent else None,
                    )
                )
            except Exception as e:
                errors.append(f"channel-peers/{path}: {e}")
        return errors
