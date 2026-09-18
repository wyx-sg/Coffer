"""How a SeaTalk channel receives events, and whether that path works.

``ChannelService`` answers everything a surface asks *about* a channel — its
pairing code, its status, a notification to push. This module answers the one
question that is not about the channel but about the road into it: which
transport SeaTalk uses for this bot, what public URL it points at, and whether
that road is actually open end to end.

It is a sibling ops module in the house style (``resource_scope_ops`` and
friends): free functions over the resource row, given the collaborators they
need, so the service stays the surface's entry point and the transport detail
lives beside ``callback_probe``, which it calls.

The two functions are kept together because they must never disagree: one
REPORTS the public callback URL the owner registers with SeaTalk, the other
PROBES it. A probe that asked a different URL than the one on the card would
answer a question nobody asked.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from coffer.application.channel.callback_probe import CallbackTestResult, probe_seatalk_callback
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.channel.runtime import ChannelRuntime

MaterializeFn = Callable[[dict[str, str]], Awaitable[dict[str, str]]]

_logger = logging.getLogger(__name__)


def callback_path(resource: Resource) -> str:
    """The listener path this channel answers on — its **uid**, not its name.

    This is half of a URL that is not Coffer's to change quietly: the owner
    pastes it into SeaTalk's Developer Portal by hand, and SeaTalk POSTs to
    whatever it was told once and never asks again. While the last segment was
    the channel's NAME, renaming a channel silently severed inbound delivery —
    the listener stopped answering that path, SeaTalk kept posting to it, and
    nothing in Coffer said a word. An externally registered URL is the single
    worst place to spell a label the owner is invited to change, so it spells
    the one thing about the channel that cannot change (ADR
    resource-identity-is-an-immutable-uid).

    The cost of the switch is one-time and visible: this path is what
    ``public_callback_url`` is built from, which the channel's status carries,
    the detail page shows with a copy button, and ``coffer channel status``
    prints as ``register:``. Upgrading changes the value, so the owner
    re-registers it once on the Portal — reading the new one from the same
    place they read the old one.

    It is also the key the listener's signing-secret map uses
    (``runtime_supervision``), so the two cannot drift apart.
    """
    return f"/seatalk/{resource.uid}"


@dataclass(frozen=True)
class CallbackInfo:
    """How this SeaTalk channel receives events, and whether that is working.

    spec channels/seatalk FR-004: the block covers both delivery methods, and
    every field that belongs to the other one reports its absent value rather
    than a plausible-looking lie. On websocket delivery there is no port, no
    path, no public URL, no listener and no tunnel — ``websocket_state`` carries
    the whole truth instead.
    """

    port: int
    path: str
    listener_running: bool
    # "webhook" | "websocket" — which of the two transports this channel uses.
    delivery: str = "webhook"
    public_base_url: str | None = None
    public_callback_url: str | None = None
    # Whether Coffer manages a cloudflared tunnel for this channel (a token is
    # configured) and whether that tunnel process is currently alive.
    tunnel_managed: bool = False
    tunnel_running: bool = False
    # connecting | connected | kicked | sdk_missing | error — None on webhook
    # delivery, and on a websocket channel that is not running at all.
    websocket_state: str | None = None
    # The last thing that went wrong on the connection, verbatim, because the
    # two failures that matter (no SDK, another process holds the connection)
    # are only actionable if the owner can read them.
    websocket_error: str | None = None


def callback_info(resource: Resource, *, runtime: ChannelRuntime) -> CallbackInfo:
    """The inbound-transport block for a SeaTalk channel (spec channels/seatalk FR-004)."""
    if str(resource.config.get("delivery") or "webhook") == "websocket":
        state = runtime.websocket_state(resource.uid)
        return CallbackInfo(
            # Nothing listens, nothing is tunnelled and no URL exists on this
            # path; reporting the listener's port here would invite the owner
            # to go looking for ingress that is not part of the design.
            port=0,
            path="",
            listener_running=False,
            delivery="websocket",
            websocket_state=state[0] if state is not None else None,
            websocket_error=state[1] if state is not None else None,
        )
    path = callback_path(resource)
    base = resource.config.get("public_base_url")
    base = base if isinstance(base, str) and base else None
    token_ref = resource.config.get("tunnel_token_ref")
    tunnel_managed = bool(isinstance(token_ref, str) and token_ref)
    return CallbackInfo(
        port=runtime.listener_port,
        path=path,
        listener_running=runtime.listener_running,
        delivery="webhook",
        public_base_url=base,
        public_callback_url=f"{base}{path}" if base else None,
        tunnel_managed=tunnel_managed,
        tunnel_running=runtime.tunnel_running(resource.uid),
    )


async def test_callback(
    resource: Resource,
    *,
    materialize: MaterializeFn | None,
    http: httpx.AsyncClient | None,
) -> CallbackTestResult:
    """Probe the channel's public callback URL end to end (SeaTalk only).

    Confirms public URL → tunnel → loopback listener → signature → handshake.
    Does not confirm the signing secret matches SeaTalk's (we sign and
    verify with the same stored secret) — that only shows on a real event.
    """
    config = resource.config
    if str(config.get("channel_type", "")) != "seatalk":
        return CallbackTestResult(ok=False, detail="callback test applies to SeaTalk channels only")
    if str(config.get("delivery") or "webhook") == "websocket":
        # There is nothing to probe: the bot dials out, so no public URL, no
        # listener and no tunnel exist on this path. The channel's websocket
        # state is the health answer here.
        return CallbackTestResult(
            ok=False,
            detail=(
                "this channel receives events over WebSocket, so there is no public "
                "callback URL to probe — check the connection state instead"
            ),
        )
    base = config.get("public_base_url")
    if not (isinstance(base, str) and base):
        return CallbackTestResult(
            ok=False, detail="set the channel's public callback URL (base URL) first"
        )
    signing_ref = str(config.get("signing_secret_ref", ""))
    if materialize is None or http is None or not signing_ref:
        return CallbackTestResult(ok=False, detail="callback testing is not available")
    try:
        signing_secret = (await materialize({"s": signing_ref}))["s"]
    except Exception:
        _logger.exception("channel.callback_test.secret_failed", extra={"channel": resource.name})
        return CallbackTestResult(ok=False, detail="could not load the channel's signing secret")
    return await probe_seatalk_callback(
        client=http,
        # The same path ``callback_info`` reports, composed by the same
        # function: a probe that asked a different URL than the one the owner
        # registered would answer a question nobody asked.
        url=f"{base}{callback_path(resource)}",
        signing_secret=signing_secret,
    )
