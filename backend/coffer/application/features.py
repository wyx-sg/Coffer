"""Which experimental features are on, on this machine, right now.

A feature's state is resolved per read, in this order (spec
experimental-features "Decide a feature's state per machine"):

1. a pin from ``COFFER_FEATURES``, fixed for the daemon's lifetime;
2. the machine's own setting, kept in ``~/.coffer/daemon-config.json``;
3. the channel default — off on ``stable``, on on ``dev``.

The settings are loaded once and held in memory, so a gate costs one dict
lookup; :meth:`FeatureService.set` writes the config file BEFORE it changes the
held value, so a request that was answered is a switch that was kept. Every
subscriber hears a change the moment it takes effect — that is how a switch
reaches the surfaces that react to it without a restart.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from coffer.domain.features import (
    Channel,
    FeaturePinned,
    FeatureSource,
    channel_default,
    feature_keys,
    get_feature,
)

_logger = logging.getLogger(__name__)


class FeatureSettingsPort(Protocol):
    """Where a machine's own feature settings are kept."""

    def read(self) -> dict[str, bool]:
        """Every stored setting, keyed by feature key."""
        ...

    def write(self, key: str, enabled: bool) -> None:
        """Persist one setting. Raises if it could not be kept."""
        ...


@dataclass(frozen=True)
class FeatureState:
    key: str
    enabled: bool
    source: FeatureSource


#: Called with ``(key, enabled)`` after a feature's state changed. May be a
#: plain function or a coroutine function.
FeatureSubscriber = Callable[[str, bool], Awaitable[None] | None]


class FeatureService:
    def __init__(
        self,
        *,
        channel: Channel,
        settings: FeatureSettingsPort,
        pins: Mapping[str, bool] | None = None,
    ) -> None:
        self._channel: Channel = channel
        self._settings_port = settings
        known = set(feature_keys())
        self._pins = {k: v for k, v in (pins or {}).items() if k in known}
        self._settings = {k: v for k, v in settings.read().items() if k in known}
        self._subscribers: list[FeatureSubscriber] = []
        # One switch at a time, from its write to the last subscriber's
        # answer: two switches of ``memory`` interleaved would run the hook's
        # withdraw and restore against each other, and the agents would end up
        # carrying whichever finished last rather than what the switch says.
        self._switching = asyncio.Lock()

    @property
    def channel(self) -> Channel:
        return self._channel

    def state(self, key: str) -> FeatureState:
        """The resolved state of ``key``; raise ``FeatureUnknown`` for an unregistered key."""
        get_feature(key)
        if key in self._pins:
            return FeatureState(key, self._pins[key], "pin")
        if key in self._settings:
            return FeatureState(key, self._settings[key], "setting")
        return FeatureState(key, channel_default(self._channel), "channel")

    def is_enabled(self, key: str) -> bool:
        return self.state(key).enabled

    def list(self) -> list[FeatureState]:
        """Every registered feature, in registry order."""
        return [self.state(key) for key in feature_keys()]

    def enabled_map(self) -> dict[str, bool]:
        return {s.key: s.enabled for s in self.list()}

    def subscribe(self, callback: FeatureSubscriber) -> None:
        self._subscribers.append(callback)

    async def set(self, key: str, enabled: bool) -> FeatureState:
        """Switch ``key`` on or off on this machine.

        Refuses a pinned feature with ``FeaturePinned``. The setting is written
        first; the held state changes only once it is kept, and subscribers
        hear only a change of the resolved state. Switches are serialized, each
        one through its subscribers, so a subscriber never runs beside another
        switch's; a subscriber must therefore never switch a feature itself.
        """
        async with self._switching:
            before = self.state(key)
            if before.source == "pin":
                raise FeaturePinned(key)
            self._settings_port.write(key, enabled)
            self._settings[key] = enabled
            after = self.state(key)
            if after.enabled != before.enabled:
                await self._notify(key, after.enabled)
            return after

    async def _notify(self, key: str, enabled: bool) -> None:
        # One subscriber's failure must not keep the others from hearing: the
        # switch itself is already kept, so the rest must still react to it.
        for callback in list(self._subscribers):
            try:
                result = callback(key, enabled)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                _logger.exception("features.subscriber_failed", extra={"feature": key})
