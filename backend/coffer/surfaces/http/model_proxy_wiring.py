"""Composition of the local model proxy (ADR api-key-providers-are-reached-
through-a-separate-local-model-proxy; spec daemon "Supervise the model proxy
from the daemon").

The proxy is a sibling process started from the daemon's own binary; the
daemon supervises it, re-attaches to a running one across its own restarts,
and pushes it the state it serves — built from the connections, the agents and
their local tokens — after every reconcile pass (which every resource write
brings forward) and whenever a token changes. The daemon stopping does NOT stop
the proxy: agents' in-flight streams outlive a daemon upgrade.

``COFFER_MODEL_PROXY=off`` keeps the supervisor from spawning anything — the
test suite sets it, because nearly every integration test boots the app.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import coffer
from coffer.application.provider.proxy_state import build_proxy_state
from coffer.application.provider.proxy_tokens import ProxyTokenService
from coffer.application.provider.service import ProviderService
from coffer.application.reconcile.reconciler import Reconciler
from coffer.application.runtime.supervisor import spawn
from coffer.domain.model_proxy.state import ProxyState, proxy_root
from coffer.infrastructure.daemon.config import effective_proxy_port
from coffer.infrastructure.model_proxy.supervisor import ProxySupervisor
from coffer.infrastructure.vault.home import coffer_home
from coffer.surfaces.http.proxy_dependencies import ProxyFacade, set_proxy_facade

_logger = logging.getLogger(__name__)

#: Set to ``off`` to leave the proxy unsupervised (never spawned).
AUTOSTART_ENV = "COFFER_MODEL_PROXY"


def proxy_root_now() -> str:
    """The proxy's loopback root at the port configured right now."""
    return proxy_root(effective_proxy_port())


@dataclass
class ModelProxyWiring:
    tokens: ProxyTokenService
    supervisor: ProxySupervisor
    task: asyncio.Task[None] | None = None
    _pending: set[asyncio.Task[None]] = dataclasses.field(default_factory=set)

    def schedule_refresh(self) -> None:
        """Re-push the proxy's state soon, from synchronous code."""
        try:
            task = spawn(self._refresh(), name="model-proxy-refresh")
        except RuntimeError:
            return
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _refresh(self) -> None:
        try:
            await self.supervisor.refresh()
        except Exception:
            _logger.warning("model_proxy.refresh_failed", exc_info=True)

    async def stop(self) -> None:
        """Stop supervising. The proxy process keeps running."""
        if self.task is not None and not self.task.done():
            self.task.cancel()
        for task in list(self._pending):
            task.cancel()
        await self.supervisor.stop()


def _status(supervisor: ProxySupervisor) -> Callable[[], dict[str, Any]]:
    def status() -> dict[str, Any]:
        data = dataclasses.asdict(supervisor.status())
        data.pop("started_at", None)
        return data

    return status


def wire_model_proxy(
    provider_svc: ProviderService,
    secret_store: Any,
    reconciler: Reconciler,
    *,
    coffer_dir: pathlib.Path | None = None,
    enabled: Callable[[], bool] = lambda: True,
) -> ModelProxyWiring:
    """Build the supervisor, publish the management facade, and start
    supervising unless ``COFFER_MODEL_PROXY=off``.

    ``enabled`` is whether the ``models`` feature is on right now: while it is
    off the proxy is pushed an empty state, so it serves no agent and no
    connection (spec experimental-features "Close every surface of a
    switched-off feature"); the connections and tokens it held are untouched.
    """
    tokens = ProxyTokenService(secret_store)

    async def state() -> ProxyState:
        if not enabled():
            return ProxyState()
        return await build_proxy_state(provider_svc, tokens)

    supervisor = ProxySupervisor(
        state,
        port=effective_proxy_port(),
        coffer_dir=coffer_dir or coffer_home(),
        version=coffer.__version__,
    )
    wiring = ModelProxyWiring(tokens=tokens, supervisor=supervisor)

    async def agent_exists(agent_uid: str) -> bool:
        return any(a.uid == agent_uid for a in await provider_svc._agents.list())

    set_proxy_facade(
        ProxyFacade(
            tokens=tokens,
            status=_status(supervisor),
            refresh=wiring._refresh,
            agent_exists=agent_exists,
            state=state,
        )
    )
    reconciler.add_pass_listener(lambda _report: wiring.schedule_refresh())
    if os.environ.get(AUTOSTART_ENV, "").lower() != "off":
        wiring.task = spawn(supervisor.start(), name="model-proxy-start")
    return wiring


__all__ = ["AUTOSTART_ENV", "ModelProxyWiring", "proxy_root_now", "wire_model_proxy"]
