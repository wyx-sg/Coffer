"""ChannelService — pairing codes, status, notify, event ingest.

The REST routes and CLI talk to this; adapter lifecycle belongs to
ChannelRuntime and message flow to InboundProcessor.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from coffer.application.audit_service import AuditService
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import (
    ChannelPeer,
    ChannelPeerRepoPort,
    EventIngestAdapter,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.channel.errors import ChannelNotPaired, ChannelNotRunning
from coffer.domain.resource import Resource, ResourceRef

if TYPE_CHECKING:
    from coffer.application.channel.runtime import ChannelRuntime
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallbackInfo:
    port: int
    path: str
    listener_running: bool


@dataclass(frozen=True)
class ChannelStatus:
    name: str
    channel_type: str
    enabled: bool
    running: bool
    pending_pairing: bool
    peer: ChannelPeer | None
    callback: CallbackInfo | None


class ChannelService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        peers: ChannelPeerRepoPort,
        pairing: PairingManager,
        runtime: ChannelRuntime,
        audit: AuditService,
    ) -> None:
        self._resources = resources
        self._peers = peers
        self._pairing = pairing
        self._runtime = runtime
        self._audit = audit
        self._ingest_tasks: set[asyncio.Task[None]] = set()

    async def _channel(self, name: str) -> Resource:
        return await self._resources.get(ResourceRef(kind="channel", name=name))

    async def issue_pairing_code(self, name: str, *, actor: str) -> tuple[str, datetime]:
        """Generate a pairing code for the channel (replacing any pending one)."""
        resource = await self._channel(name)
        code, expires_at = self._pairing.issue(name)
        await self._audit.record(
            AuditEventType.CHANNEL_PAIRING_ISSUED.value,
            ref=resource.ref,
            actor=actor,
            details={"expires_at": expires_at.isoformat()},
        )
        return code, expires_at

    async def status(self, name: str) -> ChannelStatus:
        resource = await self._channel(name)
        peer = await self._peers.get(resource.id)
        channel_type = str(resource.config.get("channel_type", ""))
        callback: CallbackInfo | None = None
        if channel_type == "seatalk":
            callback = CallbackInfo(
                port=self._runtime.listener_port,
                path=f"/seatalk/{name}",
                listener_running=self._runtime.listener_running,
            )
        return ChannelStatus(
            name=name,
            channel_type=channel_type,
            enabled=resource.enabled,
            running=self._runtime.is_running(name),
            pending_pairing=self._pairing.pending(name),
            peer=peer,
            callback=callback,
        )

    async def ingest_event(self, name: str, envelope: dict[str, object]) -> None:
        """Accept a verified platform event forwarded by the callback listener.

        Processing is scheduled in the background: the listener must answer
        the platform within seconds, and a command/pairing reply can involve
        rate-limited outbound API calls.
        """
        await self._channel(name)  # unknown name -> 404 before the 409
        adapter = self._runtime.adapter(name)
        if adapter is None or not isinstance(adapter, EventIngestAdapter):
            raise ChannelNotRunning(name)
        task = asyncio.create_task(adapter.handle_event(dict(envelope)))
        self._ingest_tasks.add(task)
        task.add_done_callback(self._reap_ingest_task)

    def _reap_ingest_task(self, task: asyncio.Task[None]) -> None:
        self._ingest_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _logger.error("channel.ingest.failed", exc_info=task.exception())

    async def notify(self, name: str, text: str, *, actor: str) -> None:
        """Push text to the channel's paired peer, outside any conversation."""
        resource = await self._channel(name)
        peer = await self._peers.get(resource.id)
        if peer is None:
            raise ChannelNotPaired(name)
        adapter = self._runtime.adapter(name)
        if adapter is None:
            raise ChannelNotRunning(name)
        await adapter.send_text(peer.chat_id, text)
        await self._audit.record(
            AuditEventType.CHANNEL_NOTIFY_SENT.value,
            ref=resource.ref,
            actor=actor,
            details={"chars": len(text)},
        )
