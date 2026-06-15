"""ChannelService — pairing codes, status, notify, event ingest.

The REST routes and CLI talk to this; adapter lifecycle belongs to
ChannelRuntime and message flow to InboundProcessor.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from coffer.application.audit_service import AuditService
from coffer.application.channel.callback_probe import CallbackTestResult, probe_seatalk_callback
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

MaterializeFn = Callable[[dict[str, str]], Awaitable[dict[str, str]]]

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallbackInfo:
    port: int
    path: str
    listener_running: bool
    public_base_url: str | None = None
    public_callback_url: str | None = None
    # Whether Coffer manages a cloudflared tunnel for this channel (a token is
    # configured) and whether that tunnel process is currently alive.
    tunnel_managed: bool = False
    tunnel_running: bool = False


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
        materialize: MaterializeFn | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._resources = resources
        self._peers = peers
        self._pairing = pairing
        self._runtime = runtime
        self._audit = audit
        # Injected by the composition root for the callback self-test: resolve
        # the signing secret and make the outbound probe. Absent in unit tests
        # that don't exercise test_callback.
        self._materialize = materialize
        self._http = http_client
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
            path = f"/seatalk/{name}"
            base = resource.config.get("public_base_url")
            base = base if isinstance(base, str) and base else None
            token_ref = resource.config.get("tunnel_token_ref")
            tunnel_managed = bool(isinstance(token_ref, str) and token_ref)
            callback = CallbackInfo(
                port=self._runtime.listener_port,
                path=path,
                listener_running=self._runtime.listener_running,
                public_base_url=base,
                public_callback_url=f"{base}{path}" if base else None,
                tunnel_managed=tunnel_managed,
                tunnel_running=self._runtime.tunnel_running(name),
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

    async def test_callback(self, name: str) -> CallbackTestResult:
        """Probe the channel's public callback URL end to end (SeaTalk only).

        Confirms public URL → tunnel → loopback listener → signature → handshake.
        Does not confirm the signing secret matches SeaTalk's (we sign and
        verify with the same stored secret) — that only shows on a real event.
        """
        resource = await self._channel(name)
        config = resource.config
        if str(config.get("channel_type", "")) != "seatalk":
            return CallbackTestResult(
                ok=False, detail="callback test applies to SeaTalk channels only"
            )
        base = config.get("public_base_url")
        if not (isinstance(base, str) and base):
            return CallbackTestResult(
                ok=False, detail="set the channel's public callback URL (base URL) first"
            )
        signing_ref = str(config.get("signing_secret_ref", ""))
        if self._materialize is None or self._http is None or not signing_ref:
            return CallbackTestResult(ok=False, detail="callback testing is not available")
        try:
            signing_secret = (await self._materialize({"s": signing_ref}))["s"]
        except Exception:
            _logger.exception("channel.callback_test.secret_failed", extra={"channel": name})
            return CallbackTestResult(
                ok=False, detail="could not load the channel's signing secret"
            )
        return await probe_seatalk_callback(
            client=self._http,
            url=f"{base}/seatalk/{name}",
            signing_secret=signing_secret,
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
