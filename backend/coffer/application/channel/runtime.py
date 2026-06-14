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
    ListenerControllerPort,
)
from coffer.domain.channel.config import parse_channel_config

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

_logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 2.0
_FAILURE_RETRY_SECONDS = 30.0

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
        materialize: Callable[[dict[str, str]], Awaitable[dict[str, str]]] | None = None,
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        self._resources = resources
        self._factory = adapter_factory
        self._processor = processor
        self._pairing = pairing
        self._listener = listener
        self._materialize = materialize
        self._interval = interval_seconds
        self._running: dict[str, _Running] = {}
        self._failed_at: dict[str, float] = {}
        self._listener_refs: dict[str, str] | None = None
        self._listener_failed_at: float | None = None
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
        self._listener_refs = None
        self._processor.shutdown()

    async def evict(self, name: str) -> None:
        """Resource deleted: stop the adapter and drop pairing state now."""
        await self._stop_adapter(name)
        self._pairing.clear(name)
        await self._reconcile_listener(await self._enabled_channels())

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
        except Exception:
            # The reconciler must outlive any single bad tick.
            _logger.exception("channel.runtime.tick_failed")

    async def _enabled_channels(self) -> dict[str, tuple[int, dict[str, object]]]:
        rows = await self._resources.list(kind="channel")
        return {r.name: (r.id, dict(r.config)) for r in rows if r.enabled}

    def _may_retry(self, name: str) -> bool:
        failed = self._failed_at.get(name)
        return failed is None or (time.monotonic() - failed) >= _FAILURE_RETRY_SECONDS

    async def _start_adapter(self, name: str, resource_id: int, config: dict[str, object]) -> None:
        adapter: ChannelAdapter | None = None
        try:
            parsed = parse_channel_config(config)
            adapter = await self._factory(name, config)
            await adapter.start(
                AdapterCallbacks(
                    on_message=self._processor.on_message,
                    on_approval_click=self._processor.on_approval_click,
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
                workspaces={w.name: w.path for w in parsed.workspaces},
                default_workspace=parsed.default_workspace,
                adapter=adapter,
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

    async def _reconcile_listener(self, desired: dict[str, tuple[int, dict[str, object]]]) -> None:
        if self._listener is None or self._stop.is_set():
            return
        materialize = self._materialize
        refs: dict[str, str] = {}
        if materialize is not None:
            for name, (_rid, config) in desired.items():
                if config.get("channel_type") == "seatalk":
                    refs[name] = str(config.get("signing_secret_ref", ""))
        # Touch the credential store only when the desired ref-set changed (or
        # the listener died): a steady state must not poll the store every tick
        # (macOS can answer with authorization prompts).
        if refs == self._listener_refs and (not refs or self._listener.running()):
            return
        if (
            refs
            and self._listener_failed_at is not None
            and (time.monotonic() - self._listener_failed_at) < _FAILURE_RETRY_SECONDS
        ):
            return
        secrets: dict[str, str] = {}
        for name, ref in refs.items():
            assert materialize is not None  # refs is empty otherwise
            try:
                secrets[name] = (await materialize({"secret": ref}))["secret"]
            except Exception:
                self._listener_failed_at = time.monotonic()
                _logger.exception("channel.listener.secret_failed", extra={"channel": name})
                return
        try:
            if secrets:
                await self._listener.ensure_running(secrets)
            else:
                await self._listener.ensure_stopped()
        except Exception:
            self._listener_failed_at = time.monotonic()
            _logger.exception("channel.listener.reconcile_failed")
            return
        self._listener_failed_at = None
        self._listener_refs = refs

    @staticmethod
    def _hash(config: dict[str, object]) -> str:
        return json.dumps(config, sort_keys=True, default=str)
