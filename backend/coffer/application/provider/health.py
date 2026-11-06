"""Each connection's health, kept without anyone opening it (spec
provider-switching "Know each connection's health without opening it").

:class:`ProviderHealthService` is the one writer of the per-connection verdict
(``domain.provider.health``). It is fed from four places:

- the **sweep** — every enabled connection, once at boot and then every
  :data:`SWEEP_SECONDS`, by the same model-list call the detail page makes. It
  lists models only: no request a sweep makes spends a token;
- an **edit** — a connection written (a new URL, a replaced key, switched on)
  is checked again at once, so a fixed key clears its error without waiting
  for the next sweep; a deleted one's verdict is forgotten;
- the **detail page** — its open-time probe and its Test report what they saw
  (``record_listing``);
- **real requests** — what the local model proxy relayed for the agents
  (``observe``, fed by the usage ingest), so a key revoked mid-session shows
  as soon as an agent's call is refused.

A newer verdict replaces an older one; one from before the kept verdict is
dropped (a usage file ingested late does not undo a fresh check). A stored key
whose destination is not approved yet is never sent: that connection is
skipped, and the secret approvals already say what waits.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from coffer.application.provider.ports import ModelList
from coffer.application.runtime.supervisor import spawn
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import Protocol as Wire
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.health import (
    HealthSource,
    ProviderHealth,
    from_listing,
    latest_per_connection,
)
from coffer.domain.reconcile import Changed
from coffer.domain.resource import Resource
from coffer.domain.secret_errors import SecretBindingPending, SecretBindingRejected
from coffer.domain.usage.records import UsageRecord

_log = logging.getLogger(__name__)

#: How often every enabled connection is checked with nothing prompting it.
SWEEP_SECONDS = 30 * 60
#: A burst of writes to one connection (an edit is several) costs one check.
RECHECK_SETTLE_SECONDS = 1.0

KIND = "provider"


class HealthStore(Protocol):
    async def upsert(self, uid: str, health: ProviderHealth) -> None: ...

    async def get(self, uid: str) -> ProviderHealth | None: ...

    async def list_all(self) -> dict[str, ProviderHealth]: ...

    async def forget(self, uid: str) -> None: ...


class ConnectionsPort(Protocol):
    async def list(self) -> list[Resource]: ...

    async def get(self, uid: str) -> Resource: ...


#: Lists a saved connection's models: ``(protocol, base_url, secret_ref)``.
Lister = Callable[[str, str | None, str | None], Awaitable[ModelList]]
#: Raises unless the connection's stored key may go to its URL.
Authorize = Callable[[Resource, ProviderConfig], Awaitable[None]]


def _now() -> datetime:
    return datetime.now(UTC)


class ProviderHealthService:
    def __init__(
        self,
        *,
        store: HealthStore,
        connections: ConnectionsPort,
        list_models: Lister,
        authorize: Authorize,
        clock: Callable[[], datetime] = _now,
        background: bool = True,
    ) -> None:
        self._store = store
        self._connections = connections
        self._list = list_models
        self._authorize = authorize
        self._clock = clock
        #: False leaves out the checks nobody asked for (the sweep, the
        #: re-check after an edit); a test suite pins it off.
        self._background = background
        self._stop = asyncio.Event()
        self._rechecks: dict[str, asyncio.Task[None]] = {}
        #: Told a connection's status moved (the event stream, the attention watcher).
        self.on_change: Callable[[str], None] | None = None

    # --- reads ---------------------------------------------------------------

    async def all(self) -> dict[str, ProviderHealth]:
        return await self._store.list_all()

    async def get(self, uid: str) -> ProviderHealth | None:
        return await self._store.get(uid)

    # --- writes --------------------------------------------------------------

    async def record(self, uid: str, health: ProviderHealth) -> None:
        """Keep ``health`` unless what is kept is newer; announce a moved status."""
        kept = await self._store.get(uid)
        if kept is not None and kept.checked_at > health.checked_at:
            return
        if kept is not None and kept.status is health.status:
            health = replace(health, since=kept.started)
        await self._store.upsert(uid, health)
        if (kept is None or kept.status is not health.status) and self.on_change is not None:
            self.on_change(uid)

    async def record_listing(self, uid: str, result: ModelList) -> None:
        """What the detail page's own listing of a saved connection found."""
        await self.record(
            uid, from_listing(reachable=result.reachable, message=result.message, at=self._clock())
        )

    async def observe(self, records: Sequence[UsageRecord]) -> None:
        """What the agents' real requests said about their connections."""
        for uid, health in latest_per_connection(list(records)).items():
            try:
                await self.record(uid, health)
            except Exception:
                _log.warning("provider_health.observe_failed", exc_info=True)

    # --- checks --------------------------------------------------------------

    async def check(self, uid: str) -> ProviderHealth | None:
        """List ``uid``'s models now and keep the verdict. ``None`` when nothing
        was checked: the connection is retired, or its key waits for approval."""
        resource = await self._connections.get(uid)
        return await self._check(resource)

    async def _check(self, resource: Resource) -> ProviderHealth | None:
        cfg = ProviderConfig.model_validate(resource.config)
        if cfg.protocol is Wire.OLLAMA:
            return None
        try:
            await self._authorize(resource, cfg)
        except (SecretBindingPending, SecretBindingRejected):
            # The key may not go there yet; the approval is listed elsewhere.
            return None
        result = await self._list(cfg.protocol.value, cfg.base_url, cfg.secret_ref)
        health = from_listing(
            reachable=result.reachable,
            message=result.message,
            at=self._clock(),
            source=HealthSource.CHECK,
        )
        await self.record(resource.uid, health)
        return health

    async def check_all(self) -> None:
        """Check every enabled connection, one after another."""
        for resource in await self._connections.list():
            if not resource.enabled:
                continue
            try:
                await self._check(resource)
            except Exception:
                _log.warning("provider_health.check_failed", extra={"uid": resource.uid})

    # --- edits ---------------------------------------------------------------

    def on_changed(self, changed: Changed) -> None:
        """A resource write (a ``HintSink``): re-check an edited connection,
        forget a deleted one."""
        if changed.kind != KIND:
            return
        uid = changed.uid
        previous = self._rechecks.pop(uid, None)
        if previous is not None:
            previous.cancel()
        if changed.op == "delete":
            self._rechecks[uid] = spawn(self._forget(uid), name="provider-health-forget")
        elif self._background:
            self._rechecks[uid] = spawn(self._recheck(uid), name="provider-health-recheck")

    async def _forget(self, uid: str) -> None:
        try:
            await self._store.forget(uid)
        finally:
            self._rechecks.pop(uid, None)

    async def _recheck(self, uid: str) -> None:
        try:
            await asyncio.sleep(RECHECK_SETTLE_SECONDS)
            resource = await self._connections.get(uid)
            if resource.enabled:
                await self._check(resource)
        except (ResourceNotFound, asyncio.CancelledError):
            pass
        except Exception:
            _log.warning("provider_health.recheck_failed", extra={"uid": uid})
        finally:
            if self._rechecks.get(uid) is asyncio.current_task():
                self._rechecks.pop(uid, None)

    # --- loop ----------------------------------------------------------------

    async def run(self, interval: float = SWEEP_SECONDS) -> None:
        """Sweep now, then every ``interval`` seconds until :meth:`stop`."""
        if not self._background:
            return
        self._stop.clear()
        while not self._stop.is_set():
            try:
                await self.check_all()
            except Exception:
                _log.exception("provider_health.sweep_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=interval)

    def stop(self) -> None:
        self._stop.set()
        for task in list(self._rechecks.values()):
            task.cancel()
        self._rechecks.clear()


__all__ = [
    "RECHECK_SETTLE_SECONDS",
    "SWEEP_SECONDS",
    "ConnectionsPort",
    "HealthStore",
    "ProviderHealthService",
]
