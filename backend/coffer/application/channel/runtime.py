"""ChannelRuntime — reconcile adapter tasks with the resource table.

The RetentionWorker pattern, applied to lifecycle: every tick, diff the
enabled channel resources against the running adapters and converge.
Enable, disable, config edits, and delete all take effect within a tick;
REST/CLI/UI never start or stop adapters directly, so reported status is
always what is actually running.

A channel travels between machines now, so "the enabled channel resources" is
no longer the same set on every machine: the reconciler answers to the
channel's **machine binding** as well, and a channel bound elsewhere is simply
not in this machine's wanted set. That is also why rebinding needs no restart —
the binding is config, a config change is a tick, and both ends of a rebind are
reached by the same loop that already handles enable and disable.
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
from coffer.application.channel.ports import AdapterCallbacks, ChannelAdapter
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
from coffer.application.channel.wanted import Gate, Routing
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.resource import Resource

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
        machine_id: Callable[[], Awaitable[str]] | None = None,
        service_hold: Callable[[bool], None] | None = None,
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
        # Told, each tick, whether a listener is up. The daemon stands down
        # when nothing has wanted it for hours, and a listener is the case
        # that measure gets wrong — see ``_hold_the_daemon_open``. The runtime
        # is handed the function rather than reaching for the daemon's clock
        # itself: application code does not import infrastructure.
        self._service_hold = service_hold
        # Which channels are this machine's to run — enabled, bound here, and
        # able to drive their own default agent. Three gates, one predicate,
        # kept out of the lifecycle loop (see ``wanted.py``).
        self._gate = Gate(machine_id_provider=machine_id)
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

    def tunnel_running(self, channel_uid: str) -> bool:
        return self._tunnel is not None and self._tunnel.running(channel_uid)

    def websocket_state(self, channel_uid: str) -> tuple[str, str | None] | None:
        """``(state, last error)`` of this channel's SeaTalk WebSocket, or None.

        None covers every case where the question does not apply: a webhook
        channel, a Telegram channel, a disabled one, or a daemon wired without a
        websocket controller at all.
        """
        if self._websockets is None:
            return None
        return self._websockets.state(channel_uid)

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
        if self._service_hold is not None:
            self._service_hold(False)
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

    async def evict(self, resource: Resource) -> None:
        """Resource deleted: stop the adapter and drop pairing state now.

        Takes the row, which is what the kind's ``on_delete`` hook is handed:
        the adapter and the pairing codes are keyed by the channel's name, the
        supervised children by its uid, and both answers have to be the row's
        own rather than derived from each other."""
        name = resource.name
        await self._stop_adapter(name)
        self._pairing.clear(name)
        if self._tunnel is not None:
            with contextlib.suppress(Exception):
                await self._tunnel.ensure_stopped(resource.uid)
        if self._websockets is not None:
            with contextlib.suppress(Exception):
                await self._websockets.ensure_stopped(resource.uid)
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
                if resource is None or self._binding_hash(name, resource) != entry.config_hash:
                    await self._stop_adapter(name)
            for name, resource in desired.items():
                if self._stop.is_set():
                    return
                if name not in self._running and self._may_retry(name):
                    await self._start_adapter(name, resource, self._gate.routing[name])
            await self._reconcile_listener(desired)
            await self._reconcile_tunnels(desired)
            await self._reconcile_websockets(desired)
            self._hold_the_daemon_open()
        except Exception:
            # The reconciler must outlive any single bad tick.
            _logger.exception("channel.runtime.tick_failed")

    def _hold_the_daemon_open(self) -> None:
        """Keep the daemon in service for as long as a listener is up.

        A daemon stands down when nothing has wanted it for hours
        (spec daemon FR-029), and "wanted" is measured in requests that
        arrived. A channel listener is the case that measure gets wrong: its
        job is to be *reachable*, and the request that proves it was worth
        keeping is the one that arrives at nine the next morning — after a
        daemon counting only yesterday's traffic would already have gone. So
        the listener says so directly, and re-says it every tick, which is
        also how the claim is dropped when the last channel is disabled.
        """
        if self._service_hold is not None:
            self._service_hold(self.listener_running)

    async def local_machine_id(self) -> str | None:
        """This machine's id, or ``None`` when no provider is wired.

        Public because the management surface answers "is this channel bound
        here?" with the same value the gate uses — two answers to that question,
        derived two ways, is how a surface comes to report a channel as running
        that nothing ever started.
        """
        return await self._gate.machine_id()

    async def _enabled_channels(self) -> Desired:
        """The channels this machine should be running (see ``wanted``)."""
        return await self._gate.wanted(self._resources)

    def _may_retry(self, name: str) -> bool:
        failed = self._failed_at.get(name)
        return failed is None or (time.monotonic() - failed) >= FAILURE_RETRY_SECONDS

    async def _start_adapter(self, name: str, resource: Resource, routing: Routing) -> None:
        """Start one channel's adapter and bind it.

        ``routing`` is handed in rather than looked up: the gate decided this
        channel was startable and what it routes to in the same pass, so the
        two arrive together and there is no window in which one is a tick older
        than the other."""
        adapter: ChannelAdapter | None = None
        config = resource.config
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
                resource=resource,
                channel_type=parsed.channel_type,
                # The parsed config's ``default_agent`` is an agent UID; what
                # the turn platform routes on is the key the gate resolved it
                # to (``wanted.Routing``). Reading the uid straight off the
                # parsed config here is exactly the mistake the single crossing
                # exists to make impossible.
                default_agent=routing.default_agent,
                default_agent_config=parsed.default_agent_config,
                adapter=adapter,
                require_mention=parsed.require_mention,
                ignore_other_mentions=parsed.ignore_other_mentions,
                agent_scope=routing.agent_scope,
            )
        )
        self._running[name] = _Running(
            adapter=adapter, config_hash=self._binding_hash(name, resource)
        )
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

    def _binding_hash(self, name: str, resource: Resource) -> str:
        """What a running channel is compared against to decide whether to
        rebuild it. The routing is part of it, not just config: the routing
        rides the binding, so a scope edit must rebind the channel the same way
        a config edit does — otherwise `/agent` would keep offering the old set
        until the daemon restarted. Renaming the AGENT a channel drives now
        changes neither (the row holds its uid), which is the point."""
        routing = self._gate.routing.get(name)
        return json.dumps(
            {"config": resource.config, "routing": routing.to_json() if routing else None},
            sort_keys=True,
            default=str,
        )
