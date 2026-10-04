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
import dataclasses
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.channel.inbound import InboundProcessor
from coffer.application.channel.pairing import PairingManager
from coffer.application.channel.ports import AdapterCallbacks, ChannelAdapter
from coffer.application.channel.runtime_binding import make_binding
from coffer.application.channel.runtime_supervision import (
    FAILURE_RETRY_SECONDS,
    Desired,
    Latch,
    MaterializeFn,
    reconcile_websockets,
    secret_stamps,
)
from coffer.application.channel.supervision_ports import WebSocketControllerPort
from coffer.application.channel.wanted import Gate, Routing
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.resource import Resource
from coffer.domain.secret_errors import SecretBindingPending, SecretBindingRejected

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 2.0

#: ``(channel uid, config) -> adapter``: the adapter is named by the channel's
#: uid, which is what its inbound messages carry in ``channel`` and what every
#: map below is keyed by, so a rename touches none of them.
AdapterFactory = Callable[[str, dict[str, object]], Awaitable[ChannelAdapter]]

#: ``secret ref -> an opaque stamp that changes when the stored value does``
#: (``None`` when the ref holds nothing). Rotating a secret keeps its ref, so
#: neither the config nor the ref says the value moved; this does.
SecretRevision = Callable[[str], str | None]


@dataclass
class _Running:
    adapter: ChannelAdapter
    config_hash: str
    #: The channel's name when this adapter was bound; a rename re-binds the
    #: row, not the adapter.
    name: str


class ChannelRuntime:
    def __init__(
        self,
        *,
        resources: ResourceService,
        adapter_factory: AdapterFactory,
        processor: InboundProcessor,
        pairing: PairingManager,
        websockets: WebSocketControllerPort | None = None,
        materialize: MaterializeFn | None = None,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
        machine_id: Callable[[], Awaitable[str]] | None = None,
        secret_revision: SecretRevision | None = None,
    ) -> None:
        self._resources = resources
        self._factory = adapter_factory
        self._processor = processor
        self._pairing = pairing
        self._websockets = websockets
        self._materialize = materialize
        self._secret_revision = secret_revision
        self._interval = interval_seconds
        # Which channels are this machine's to run — enabled, bound here, and
        # able to drive their own default agent. Three gates, one predicate,
        # kept out of the lifecycle loop (see ``wanted.py``).
        self._gate = Gate(machine_id_provider=machine_id)
        self._running: dict[str, _Running] = {}
        self._failed_at: dict[str, float] = {}
        # Why a channel's adapter did not start when the cause is its secret
        # waiting on (or refused by) the owner's approval in the Coffer app:
        # ``pending`` | ``refused``. Absent once the adapter starts, the channel
        # is no longer wanted, or the start failed for any other reason.
        self._withheld: dict[str, str] = {}
        self._websocket_latches: dict[str, Latch[tuple[str, str, str]]] = {}
        # Serialises a reconcile pass with an explicit ``restart``: both stop and
        # start adapters, and two of them interleaved would start one twice.
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()

    # -- introspection (used by ChannelService) ---------------------------

    def is_running(self, channel_uid: str) -> bool:
        return channel_uid in self._running

    def secret_withheld(self, channel_uid: str) -> str | None:
        """``pending`` or ``refused`` while the channel's secret binding is the
        reason its adapter is not running, else ``None``."""
        return self._withheld.get(channel_uid)

    def adapter(self, channel_uid: str) -> ChannelAdapter | None:
        entry = self._running.get(channel_uid)
        return entry.adapter if entry is not None else None

    def websocket_state(self, channel_uid: str) -> tuple[str, str | None] | None:
        """``(state, last error)`` of this channel's SeaTalk WebSocket, or None.

        None covers every case where the question does not apply: a Telegram
        channel, a disabled one, or a daemon wired without a
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
        """Stop every adapter and websocket connection (daemon shutdown / final)."""
        self.stop()
        for channel_uid in list(self._running):
            await self._stop_adapter(channel_uid)
        if self._websockets is not None:
            with contextlib.suppress(Exception):
                await self._websockets.dispose()
        self._websocket_latches.clear()
        self._processor.shutdown()

    async def evict(self, resource: Resource) -> None:
        """Resource deleted: stop the adapter and drop pairing state now.

        Takes the row, which is what the kind's ``on_delete`` hook is handed.
        The adapter, the pairing code and the websocket connection are all keyed
        by the channel's uid."""
        await self._stop_adapter(resource.uid)
        self._pairing.clear(resource.uid)
        if self._websockets is not None:
            with contextlib.suppress(Exception):
                await self._websockets.ensure_stopped(resource.uid)
        desired = await self._enabled_channels()
        # The eviction hook can run while the row is still visible (it fires
        # before/inside the delete), so the table would otherwise tell the
        # reconciler to start back up what we just stopped. The channel
        # being evicted is not wanted, whatever the table still says.
        desired.pop(resource.uid, None)
        await self._reconcile_websockets(desired)

    # -- reconciliation ----------------------------------------------------

    async def restart(self, channel_uid: str) -> bool:
        """Stop the channel's adapter and websocket and start them afresh now.

        The one way to make a running channel read its secret again and dial the
        platform anew without waiting for a config change: the adapter reads its
        secret when it is built, and the reconciler only rebuilds on a changed
        binding. Forgets the failure ladder too, so a channel waiting out its 30
        seconds is retried at once. Returns whether the channel is running
        afterwards (a disabled or not-here channel simply stays stopped).
        """
        async with self._lock:
            await self._stop_adapter(channel_uid)
            self._failed_at.pop(channel_uid, None)
            self._websocket_latches.pop(channel_uid, None)
            if self._websockets is not None:
                with contextlib.suppress(Exception):
                    await self._websockets.ensure_stopped(channel_uid)
            await self._reconcile()
        return channel_uid in self._running

    async def reconcile_once(self) -> None:
        async with self._lock:
            await self._reconcile()

    async def _reconcile(self) -> None:
        try:
            desired = await self._enabled_channels()
            for channel_uid in set(self._withheld) - set(desired):
                del self._withheld[channel_uid]
            for channel_uid in list(self._running):
                # Re-fetch per iteration: evict() can pop entries while a
                # prior _stop_adapter await is in flight.
                entry = self._running.get(channel_uid)
                if entry is None:
                    continue
                resource = desired.get(channel_uid)
                if (
                    resource is None
                    or self._binding_hash(channel_uid, resource) != entry.config_hash
                ):
                    await self._stop_adapter(channel_uid)
                elif resource.name != entry.name:
                    # A rename: the adapter keeps running, the row it reports is
                    # the new one.
                    self._rename(channel_uid, entry, resource)
            for channel_uid, resource in desired.items():
                if self._stop.is_set():
                    return
                if channel_uid not in self._running and self._may_retry(channel_uid):
                    await self._start_adapter(
                        channel_uid, resource, self._gate.routing[channel_uid]
                    )
            await self._reconcile_websockets(desired)
        except Exception:
            # The reconciler must outlive any single bad tick.
            _logger.exception("channel.runtime.tick_failed")

    def _rename(self, channel_uid: str, entry: _Running, resource: Resource) -> None:
        binding = self._processor.binding(channel_uid)
        if binding is not None:
            self._processor.bind(dataclasses.replace(binding, resource=resource))
        self._running[channel_uid] = dataclasses.replace(entry, name=resource.name)

    async def local_machine_id(self) -> str | None:
        """This machine's id, or ``None`` when no provider is wired.

        Public because the management surface answers "is this channel bound
        here?" with the same value the gate uses — two answers to that question,
        derived two ways, is how a surface comes to report a channel as running
        that nothing ever started.
        """
        return await self._gate.machine_id()

    async def _enabled_channels(self) -> Desired:
        """The channels this machine should run (see ``wanted``)."""
        return await self._gate.wanted(self._resources)

    def _may_retry(self, channel_uid: str) -> bool:
        failed = self._failed_at.get(channel_uid)
        return failed is None or (time.monotonic() - failed) >= FAILURE_RETRY_SECONDS

    async def _start_adapter(self, channel_uid: str, resource: Resource, routing: Routing) -> None:
        """Start one channel's adapter and bind it.

        ``routing`` is handed in rather than looked up: the gate decided this
        channel was startable and what it routes to in the same pass, so the
        two arrive together and there is no window in which one is a tick older
        than the other."""
        adapter: ChannelAdapter | None = None
        config = resource.config
        try:
            parsed = parse_channel_config(config)
            adapter = await self._factory(channel_uid, config)
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
        except Exception as exc:
            self._failed_at[channel_uid] = time.monotonic()
            if isinstance(exc, SecretBindingPending):
                # Not a fault: the secret awaits (or was refused) approval; the
                # next retry finds the approval if it came meanwhile.
                state = "refused" if isinstance(exc, SecretBindingRejected) else "pending"
                self._withheld[channel_uid] = state
                _logger.warning(
                    "channel.adapter.secret_withheld",
                    extra={"channel": resource.name, "state": state},
                )
            else:
                self._withheld.pop(channel_uid, None)
                _logger.exception("channel.adapter.start_failed", extra={"channel": resource.name})
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
        self._failed_at.pop(channel_uid, None)
        self._withheld.pop(channel_uid, None)
        self._processor.bind(make_binding(resource, parsed, routing, adapter))
        self._running[channel_uid] = _Running(
            adapter=adapter,
            config_hash=self._binding_hash(channel_uid, resource),
            name=resource.name,
        )
        _logger.info("channel.adapter.started", extra={"channel": resource.name})

    async def _stop_adapter(self, channel_uid: str) -> None:
        entry = self._running.pop(channel_uid, None)
        self._processor.unbind(channel_uid)
        if entry is not None:
            with contextlib.suppress(Exception):
                await entry.adapter.stop()
            _logger.info("channel.adapter.stopped", extra={"channel": entry.name})

    async def _reconcile_websockets(self, desired: Desired) -> None:
        if self._websockets is None or self._stop.is_set():
            return
        await reconcile_websockets(
            self._websockets,
            self._materialize,
            desired,
            self._websocket_latches,
            secret_revision=self._secret_revision,
        )

    def _binding_hash(self, channel_uid: str, resource: Resource) -> str:
        """What a running channel is compared against to decide whether to
        rebuild it. The routing is part of it, not just config: the routing
        rides the binding, so a scope edit must rebind the channel the same way
        a config edit does — otherwise `/new <agent>` would keep accepting the old set
        until the daemon restarted. Renaming the AGENT a channel drives now
        changes neither (the row holds its uid), which is the point."""
        routing = self._gate.routing.get(channel_uid)
        return json.dumps(
            {
                "config": resource.config,
                "routing": routing.to_json() if routing else None,
                # A rotated secret keeps its ref, so the config above does not
                # move; the adapter read the value once when it was built.
                "secrets": secret_stamps(resource.config, self._secret_revision),
            },
            sort_keys=True,
            default=str,
        )
