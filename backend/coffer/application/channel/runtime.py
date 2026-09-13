"""ChannelRuntime — reconcile adapter tasks with the resource table.

The RetentionWorker pattern, applied to lifecycle: every tick, diff the
enabled channel resources against the running adapters and converge.
Enable, disable, config edits, and delete all take effect within a tick;
REST/CLI/UI never start or stop adapters directly, so reported status is
always what is actually running.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.channel.inbound import ChannelBinding, InboundProcessor
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import (
    AdapterCallbacks,
    ChannelAdapter,
)
from coffer.application.channel.runtime_supervision import (
    FAILURE_RETRY_SECONDS,
    Desired,
    Latch,
    reconcile_listener,
    reconcile_tunnels,
    reconcile_websockets,
)
from coffer.application.channel.supervision_ports import (
    ListenerControllerPort,
    TunnelControllerPort,
    WebSocketControllerPort,
)
from coffer.domain.channel.config import parse_channel_config

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 2.0

AdapterFactory = Callable[[str, dict[str, object]], Awaitable[ChannelAdapter]]


@dataclass
class _Running:
    adapter: ChannelAdapter
    config_hash: str


class ChannelRuntime:
    def __init__(
        self,
        *,
        resources: ResourceService,
        adapter_factory: AdapterFactory,
        processor: InboundProcessor,
        pairing: PairingManager,
        listener: ListenerControllerPort | None = None,
        tunnel: TunnelControllerPort | None = None,
        websockets: WebSocketControllerPort | None = None,
        materialize: Callable[[dict[str, str]], Awaitable[dict[str, str]]] | None = None,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._resources = resources
        self._factory = adapter_factory
        self._processor = processor
        self._pairing = pairing
        self._listener = listener
        self._tunnel = tunnel
        self._websockets = websockets
        self._materialize = materialize
        self._interval = interval_seconds
        self._running: dict[str, _Running] = {}
        self._failed_at: dict[str, float] = {}
        self._listener_latch: Latch[dict[str, str]] = Latch()
        self._tunnel_latch: Latch[dict[str, str]] = Latch()
        self._websocket_latch: Latch[dict[str, tuple[str, str]]] = Latch()
        self._stop = asyncio.Event()

    # -- introspection (used by ChannelService) ---------------------------

    def is_running(self, name: str) -> bool:
        return name in self._running

    def adapter(self, name: str) -> ChannelAdapter | None:
        entry = self._running.get(name)
        return entry.adapter if entry is not None else None

    @property
    def listener_port(self) -> int:
        return self._listener.port if self._listener is not None else 0

    @property
    def listener_running(self) -> bool:
        return self._listener is not None and self._listener.running()

    def tunnel_running(self, name: str) -> bool:
        return self._tunnel is not None and self._tunnel.running(name)

    def websocket_state(self, name: str) -> tuple[str, str | None] | None:
        """``(state, last error)`` of this channel's SeaTalk WebSocket, or None.

        None covers every case where the question does not apply: a webhook
        channel, a Telegram channel, a disabled one, or a daemon wired without a
        websocket controller at all.
        """
        if self._websockets is None:
            return None
        return self._websockets.state(name)

    # -- lifecycle -----------------------------------------------------------

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._stop.set()

    async def run(self) -> None:
        """Reconcile until stop() is called."""
        while not self._stop.is_set():
            await self.reconcile_once()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)

    async def dispose(self) -> None:
        """Stop every adapter and the listener (daemon shutdown / final)."""
        self.stop()
        for name in list(self._running):
            await self._stop_adapter(name)
        if self._listener is not None:
            with contextlib.suppress(Exception):
                await self._listener.ensure_stopped()
        self._listener_latch.forget()
        if self._tunnel is not None:
            with contextlib.suppress(Exception):
                await self._tunnel.dispose()
        self._tunnel_latch.forget()
        if self._websockets is not None:
            with contextlib.suppress(Exception):
                await self._websockets.dispose()
        self._websocket_latch.forget()
        self._processor.shutdown()

    async def evict(self, name: str) -> None:
        """Resource deleted: stop the adapter and drop pairing state now."""
        await self._stop_adapter(name)
        self._pairing.clear(name)
        if self._tunnel is not None:
            with contextlib.suppress(Exception):
                await self._tunnel.ensure_stopped(name)
        if self._websockets is not None:
            with contextlib.suppress(Exception):
                await self._websockets.ensure_stopped(name)
        desired = await self._enabled_channels()
        # The eviction hook can run while the row is still visible (it fires
        # before/inside the delete), so the table would otherwise tell the
        # reconcilers to start back up everything we just stopped. The channel
        # being evicted is not wanted, whatever the table still says.
        desired.pop(name, None)
        await self._reconcile_listener(desired)
        await self._reconcile_tunnels(desired)
        await self._reconcile_websockets(desired)

    # -- reconciliation ----------------------------------------------------

    async def reconcile_once(self) -> None:
        try:
            desired = await self._enabled_channels()
            for name in list(self._running):
                # Re-fetch per iteration: evict() can pop entries while a
                # prior _stop_adapter await is in flight.
                entry = self._running.get(name)
                if entry is None:
                    continue
                resource = desired.get(name)
                if resource is None or self._hash(resource[1]) != entry.config_hash:
                    await self._stop_adapter(name)
            for name, (resource_id, config) in desired.items():
                if self._stop.is_set():
                    return
                if name not in self._running and self._may_retry(name):
                    await self._start_adapter(name, resource_id, config)
            await self._reconcile_listener(desired)
            await self._reconcile_tunnels(desired)
            await self._reconcile_websockets(desired)
        except Exception:
            # The reconciler must outlive any single bad tick.
            _logger.exception("channel.runtime.tick_failed")

    async def _enabled_channels(self) -> Desired:
        # A channel carries no activation scope (ADR per-agent-resource-scope): enabled means it
        # runs here, on the one machine the daemon is on. The machine-affinity
        # gate this once had went away with continuous sync (ADR vault-export-import).
        rows = await self._resources.list(kind="channel")
        return {r.name: (r.id, dict(r.config)) for r in rows if r.enabled}

    def _may_retry(self, name: str) -> bool:
        failed = self._failed_at.get(name)
        return failed is None or (time.monotonic() - failed) >= FAILURE_RETRY_SECONDS

    async def _start_adapter(self, name: str, resource_id: int, config: dict[str, object]) -> None:
        adapter: ChannelAdapter | None = None
        try:
            parsed = parse_channel_config(config)
            adapter = await self._factory(name, config)
            await adapter.start(
                AdapterCallbacks(
                    on_message=self._processor.on_message,
                    on_callback=self._processor.on_callback,
                    # Non-message events about the bot's own standing in a chat
                    # (removed from a group, group turned external): wired here
                    # so a transport that emits them reaches the processor, and
                    # simply unused by one that does not.
                    on_lifecycle=self._processor.on_lifecycle,
                    on_stop=self._processor.on_stop,
                )
            )
        except Exception:
            self._failed_at[name] = time.monotonic()
            _logger.exception("channel.adapter.start_failed", extra={"channel": name})
            if adapter is not None:
                # Close whatever the factory built (httpx client, tasks) so
                # the 30s retry ladder doesn't leak one client per attempt.
                with contextlib.suppress(Exception):
                    await adapter.stop()
            return
        if self._stop.is_set():
            # dispose() ran while we were starting — don't leave a live
            # adapter behind that nothing will ever stop.
            with contextlib.suppress(Exception):
                await adapter.stop()
            return
        self._failed_at.pop(name, None)
        self._processor.bind(
            ChannelBinding(
                name=name,
                resource_id=resource_id,
                channel_type=parsed.channel_type,
                default_agent=parsed.default_agent,
                default_agent_config=parsed.default_agent_config,
                adapter=adapter,
                require_mention=parsed.require_mention,
                ignore_other_mentions=parsed.ignore_other_mentions,
            )
        )
        self._running[name] = _Running(adapter=adapter, config_hash=self._hash(config))
        _logger.info("channel.adapter.started", extra={"channel": name})

    async def _stop_adapter(self, name: str) -> None:
        entry = self._running.pop(name, None)
        self._processor.unbind(name)
        if entry is not None:
            with contextlib.suppress(Exception):
                await entry.adapter.stop()
            _logger.info("channel.adapter.stopped", extra={"channel": name})

    async def _reconcile_listener(self, desired: Desired) -> None:
        if self._listener is None or self._stop.is_set():
            return
        await reconcile_listener(self._listener, self._materialize, desired, self._listener_latch)

    async def _reconcile_tunnels(self, desired: Desired) -> None:
        if self._tunnel is None or self._stop.is_set():
            return
        await reconcile_tunnels(self._tunnel, self._materialize, desired, self._tunnel_latch)

    async def _reconcile_websockets(self, desired: Desired) -> None:
        if self._websockets is None or self._stop.is_set():
            return
        await reconcile_websockets(
            self._websockets, self._materialize, desired, self._websocket_latch
        )

    @staticmethod
    def _hash(config: dict[str, object]) -> str:
        return json.dumps(config, sort_keys=True, default=str)
