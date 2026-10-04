"""The inbound-supervision reconciler ``ChannelRuntime`` drives.

A SeaTalk channel's inbound side is one websocket connection that is not the
adapter itself (spec channels/seatalk "Receive every event over one outbound
websocket connection"). Its reconciler follows this discipline:

1. derive the wanted set from the enabled channels,
2. stop whatever is no longer wanted, even in an otherwise steady state,
3. touch the secret store ONLY when the wanted set changed or the thing
   died — a steady state that polled the store every tick would have macOS
   answering with authorization prompts,
4. latch a failure for 30 seconds instead of retrying hot.

``Latch`` is that memory, one per channel, and the reconciler is a plain function
over them. ``ChannelRuntime`` keeps a thin method that holds the guards tied to
its own state (no controller wired, shutting down) and owns the latches.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.channel.supervision_ports import WebSocketControllerPort
from coffer.domain.resource import Resource
from coffer.domain.secrets import SecretDestination, channel_destination

_logger = logging.getLogger(__name__)

# How long a failure is latched before the next attempt. Shared with the adapter
# start ladder in ``ChannelRuntime`` so one answer covers every retry here.
FAILURE_RETRY_SECONDS = 30.0

# ``{channel uid: resource row}`` for every channel this machine should run.
# The row itself rather than the two fields the reconcilers used to be handed:
# they read its ``config``, the runtime also needs its ``id`` and its ``uid``,
# and a tuple that exists only to carry a subset of a row is a place for the
# subset to fall behind the row.
Desired = dict[str, Resource]
#: ``(refs, destination) -> secrets``: the guarded resolver's async path. The
#: destination names the channel and the app the secret is sent as, so the
#: boundary can hold a secret nobody approved for it.
MaterializeFn = Callable[[dict[str, str], SecretDestination], Awaitable[dict[str, str]]]


#: What the reconciler below keys its controller by: the channel's **uid**,
#: never its name. The SeaTalk WebSocket holds a register handshake per key,
#: and a label the owner may rename is the wrong thing to hold across it. The
#: channel's NAME still goes in the log lines, because that is what the owner
#: calls it.


_SECRET_REF_FIELDS = ("bot_token_ref", "app_secret_ref")


def secret_stamps(
    config: dict[str, object], revision: Callable[[str], str | None] | None
) -> dict[str, str | None]:
    """The revision of each secret a channel's config points at."""
    if revision is None:
        return {}
    refs = (config.get(field) for field in _SECRET_REF_FIELDS)
    return {ref: revision(ref) for ref in refs if isinstance(ref, str) and ref}


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


async def reconcile_websockets(
    websockets: WebSocketControllerPort,
    materialize: MaterializeFn | None,
    desired: Desired,
    latches: dict[str, Latch[tuple[str, str, str]]],
    *,
    secret_revision: Callable[[str], str | None] | None = None,
) -> None:
    """Hold one SeaTalk WebSocket per enabled SeaTalk channel (spec channels/seatalk
    "Receive every event over one outbound websocket connection").

    The register handshake authenticates with ``app_id`` and the materialized
    app secret, which is exactly why this transport needs no signing secret and
    no public URL.

    Each channel has its own latch (``latches``, keyed by uid): a channel whose
    secret cannot be read, or whose connection will not start, waits out its own
    30 seconds without holding up the others.
    """
    refs: dict[str, tuple[str, str, str]] = {}
    names: dict[str, str] = {}
    if materialize is not None:
        for resource in desired.values():
            config = resource.config
            if config.get("channel_type") != "seatalk":
                continue
            app_id = str(config.get("app_id") or "")
            secret_ref = str(config.get("app_secret_ref") or "")
            if app_id and secret_ref:
                # The third part is the stored secret's revision: rotating a
                # secret keeps its ref, and without it a rotated secret would
                # look like a steady state and never be read again.
                stamp = secret_revision(secret_ref) if secret_revision is not None else None
                refs[resource.uid] = (app_id, secret_ref, stamp or "")
                names[resource.uid] = resource.name
    # Always drop connections for channels no longer wanted (disabled or
    # deleted), even in a steady state.
    for uid in websockets.active() - set(refs):
        with contextlib.suppress(Exception):
            await websockets.ensure_stopped(uid)
    for uid in set(latches) - set(refs):
        del latches[uid]
    for uid, key in refs.items():
        app_id, secret_ref, _ = key
        latch = latches.setdefault(uid, Latch())
        if latch.refs == key and websockets.running(uid):
            continue
        if latch.cooling(wanted=True):
            continue
        assert materialize is not None  # refs is empty otherwise
        destination = channel_destination(uid, names[uid], "seatalk", app_id)
        try:
            secret = (await materialize({"secret": secret_ref}, destination))["secret"]
        except Exception:
            latch.failed()
            _logger.exception("channel.websocket.secret_failed", extra={"channel_uid": uid})
            continue
        try:
            await websockets.ensure_running(uid, app_id, secret)
        except Exception:
            latch.failed()
            _logger.exception("channel.websocket.reconcile_failed", extra={"channel_uid": uid})
            continue
        latch.converged(key)
