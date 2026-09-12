"""The three inbound-supervision reconcilers ``ChannelRuntime`` drives.

A channel's inbound side may need a child or a connection that is not the
adapter itself: one callback listener for the whole daemon (webhook delivery),
one cloudflared tunnel per channel that has a connector token, and one SeaTalk
WebSocket per channel on websocket delivery. All three follow the same
discipline, which is why they live together:

1. derive the wanted set from the enabled channels,
2. stop whatever is no longer wanted, even in an otherwise steady state,
3. touch the credential store ONLY when the wanted set changed or the thing
   died — a steady state that polled the store every tick would have macOS
   answering with authorization prompts,
4. latch a failure for 30 seconds instead of retrying hot.

``Latch`` is that memory, and each reconciler is a plain function over it.
``ChannelRuntime`` keeps thin methods that hold the guards tied to its own state
(no controller wired, shutting down) and owns the latches.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.channel.supervision_ports import (
    ListenerControllerPort,
    TunnelControllerPort,
    WebSocketControllerPort,
)

_logger = logging.getLogger(__name__)

# How long a failure is latched before the next attempt. Shared with the adapter
# start ladder in ``ChannelRuntime`` so one answer covers every retry here.
FAILURE_RETRY_SECONDS = 30.0

# ``{channel name: (resource id, config)}`` for every enabled channel.
Desired = dict[str, tuple[int, dict[str, object]]]
MaterializeFn = Callable[[dict[str, str]], Awaitable[dict[str, str]]]


def delivery_of(config: dict[str, object]) -> str:
    """A SeaTalk channel's event-delivery method, defaulting to webhook.

    The absent key means webhook — which is what every channel configured before
    the field existed is — so this reads a raw config dict the way the domain
    model would, without paying for validation on every tick.
    """
    return str(config.get("delivery") or "webhook")


@dataclass
class Latch[T]:
    """What one reconciler remembers between ticks.

    ``refs`` is the wanted set it last converged to (``None`` before the first
    pass and after a dispose, which forces a fresh convergence); ``failed_at``
    is when it last failed, which holds the next attempt off for 30 seconds.
    """

    refs: T | None = None
    failed_at: float | None = None

    def cooling(self, *, wanted: bool) -> bool:
        """Whether a wanted-but-failed reconcile is still inside its retry wait."""
        return (
            wanted
            and self.failed_at is not None
            and (time.monotonic() - self.failed_at) < FAILURE_RETRY_SECONDS
        )

    def failed(self) -> None:
        self.failed_at = time.monotonic()

    def converged(self, refs: T) -> None:
        self.failed_at = None
        self.refs = refs

    def forget(self) -> None:
        self.refs = None


async def reconcile_listener(
    listener: ListenerControllerPort,
    materialize: MaterializeFn | None,
    desired: Desired,
    latch: Latch[dict[str, str]],
) -> None:
    """Run the callback listener exactly while a webhook channel wants it."""
    refs: dict[str, str] = {}
    if materialize is not None:
        for name, (_rid, config) in desired.items():
            # FR-071: only WEBHOOK delivery needs the listener. A deployment whose
            # only SeaTalk channel is websocket must leave it stopped — not
            # needing an inbound HTTP surface is the whole point of that
            # transport, and a listener nothing posts to is a port open for
            # nothing.
            if config.get("channel_type") == "seatalk" and delivery_of(config) == "webhook":
                refs[name] = str(config.get("signing_secret_ref", ""))
    if refs == latch.refs and (not refs or listener.running()):
        return
    if latch.cooling(wanted=bool(refs)):
        return
    secrets: dict[str, str] = {}
    for name, ref in refs.items():
        assert materialize is not None  # refs is empty otherwise
        try:
            secrets[name] = (await materialize({"secret": ref}))["secret"]
        except Exception:
            latch.failed()
            _logger.exception("channel.listener.secret_failed", extra={"channel": name})
            return
    try:
        if secrets:
            await listener.ensure_running(secrets)
        else:
            await listener.ensure_stopped()
    except Exception:
        latch.failed()
        _logger.exception("channel.listener.reconcile_failed")
        return
    latch.converged(refs)


async def reconcile_tunnels(
    tunnel: TunnelControllerPort,
    materialize: MaterializeFn | None,
    desired: Desired,
    latch: Latch[dict[str, str]],
) -> None:
    """Keep one cloudflared child per channel that records a connector token."""
    refs: dict[str, str] = {}
    if materialize is not None:
        for name, (_rid, config) in desired.items():
            if config.get("channel_type") == "seatalk":
                ref = str(config.get("tunnel_token_ref") or "")
                if ref:
                    refs[name] = ref
    # Always stop tunnels for channels no longer managed (disabled, deleted, or
    # token-ref cleared), even when the rest is a steady state.
    for name in tunnel.active() - set(refs):
        with contextlib.suppress(Exception):
            await tunnel.ensure_stopped(name)
    if refs == latch.refs and all(tunnel.running(n) for n in refs):
        return
    if latch.cooling(wanted=bool(refs)):
        return
    tokens: dict[str, str] = {}
    for name, ref in refs.items():
        assert materialize is not None  # refs is empty otherwise
        try:
            tokens[name] = (await materialize({"token": ref}))["token"]
        except Exception:
            latch.failed()
            _logger.exception("channel.tunnel.secret_failed", extra={"channel": name})
            return
    try:
        for name, token in tokens.items():
            await tunnel.ensure_running(name, token)
    except Exception:
        # cloudflared missing / spawn failure — retry on the 30s ladder.
        latch.failed()
        _logger.exception("channel.tunnel.reconcile_failed")
        return
    latch.converged(refs)


async def reconcile_websockets(
    websockets: WebSocketControllerPort,
    materialize: MaterializeFn | None,
    desired: Desired,
    latch: Latch[dict[str, tuple[str, str]]],
) -> None:
    """Hold one SeaTalk WebSocket per websocket-delivery channel (FR-071).

    The tunnel reconciler's shape with the app's own credentials in place of a
    connector token: the register handshake authenticates with ``app_id`` and the
    materialized app secret, which is exactly why this transport needs no signing
    secret and no public URL.
    """
    refs: dict[str, tuple[str, str]] = {}
    if materialize is not None:
        for name, (_rid, config) in desired.items():
            if config.get("channel_type") != "seatalk" or delivery_of(config) != "websocket":
                continue
            app_id = str(config.get("app_id") or "")
            secret_ref = str(config.get("app_secret_ref") or "")
            if app_id and secret_ref:
                refs[name] = (app_id, secret_ref)
    # Always drop connections for channels no longer wanted (disabled, deleted,
    # or switched back to webhook), even in a steady state.
    for name in websockets.active() - set(refs):
        with contextlib.suppress(Exception):
            await websockets.ensure_stopped(name)
    if refs == latch.refs and all(websockets.running(n) for n in refs):
        return
    if latch.cooling(wanted=bool(refs)):
        return
    credentials: dict[str, tuple[str, str]] = {}
    for name, (app_id, secret_ref) in refs.items():
        assert materialize is not None  # refs is empty otherwise
        try:
            secret = (await materialize({"secret": secret_ref}))["secret"]
        except Exception:
            latch.failed()
            _logger.exception("channel.websocket.secret_failed", extra={"channel": name})
            return
        credentials[name] = (app_id, secret)
    try:
        for name, (app_id, secret) in credentials.items():
            await websockets.ensure_running(name, app_id, secret)
    except Exception:
        latch.failed()
        _logger.exception("channel.websocket.reconcile_failed")
        return
    latch.converged(refs)
