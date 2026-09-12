"""Own one supervised SeaTalk WebSocket connection per channel.

The controller half of ``seatalk_ws`` (split only to keep each file inside the
400-line limit): ``SeaTalkWebSocketConnector`` holds and supervises one socket,
and this decides which channels have one. It is the websocket sibling of
``TunnelController`` in ``tunnel_spawn`` — same shape, so ``ChannelRuntime``
reconciles both the same way.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

from coffer.infrastructure.channel.seatalk_ws import IngestFn, SeaTalkWebSocketConnector

_logger = logging.getLogger(__name__)


@dataclass
class _Entry:
    connector: SeaTalkWebSocketConnector
    app_id: str
    app_secret: str


class SeaTalkWebSocketController:
    """Owns one connector per websocket-delivery channel.

    Satisfies ``WebSocketControllerPort``, mirroring ``TunnelController``: the
    reconciler asks for the set it wants and this converges. ``running(name)``
    reports that a *supervisor* is alive for the channel — not that the socket
    is up, which is what ``state(name)`` is for; a connector stuck on
    ``sdk_missing`` is still running (and still retrying), and the reconciler
    must not respawn it every tick.
    """

    def __init__(
        self,
        *,
        ingest: IngestFn,
        connector_factory: Callable[..., SeaTalkWebSocketConnector] | None = None,
    ) -> None:
        self._ingest = ingest
        self._factory = connector_factory or SeaTalkWebSocketConnector
        self._entries: dict[str, _Entry] = {}

    def running(self, name: str) -> bool:
        entry = self._entries.get(name)
        return entry is not None and entry.connector.supervising

    def active(self) -> set[str]:
        return set(self._entries)

    def state(self, name: str) -> tuple[str, str | None] | None:
        entry = self._entries.get(name)
        return entry.connector.state() if entry is not None else None

    async def ensure_running(self, name: str, app_id: str, app_secret: str) -> None:
        existing = self._entries.get(name)
        if (
            existing is not None
            and existing.connector.supervising
            and (existing.app_id, existing.app_secret) == (app_id, app_secret)
        ):
            return
        await self.ensure_stopped(name)
        connector = self._factory(name, app_id, app_secret, ingest=self._ingest)
        await connector.start()
        self._entries[name] = _Entry(connector=connector, app_id=app_id, app_secret=app_secret)
        _logger.info("channel.websocket.started", extra={"channel": name})

    async def ensure_stopped(self, name: str) -> None:
        entry = self._entries.pop(name, None)
        if entry is None:
            return
        with contextlib.suppress(Exception):
            await entry.connector.stop()
        _logger.info("channel.websocket.stopped", extra={"channel": name})

    async def dispose(self) -> None:
        for name in list(self._entries):
            await self.ensure_stopped(name)
