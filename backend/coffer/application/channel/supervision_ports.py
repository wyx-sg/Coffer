"""Ports for the inbound plumbing a channel may need beside its adapter.

Three supervised things, none of which is the transport adapter itself: the one
callback-listener child the whole daemon shares (webhook delivery), one
cloudflared tunnel per channel that records a connector token, and one SeaTalk
WebSocket per channel on websocket delivery. ``ChannelRuntime`` reconciles all
three the same way (see ``runtime_supervision``), which is why their ports sit
together here rather than among the message-flow ports in ``ports``.
"""

from __future__ import annotations

from typing import Protocol


class ListenerControllerPort(Protocol):
    """Lifecycle of the callback-listener child process."""

    @property
    def port(self) -> int: ...

    def running(self) -> bool: ...

    async def ensure_running(self, signing_secrets: dict[str, str]) -> None: ...

    async def ensure_stopped(self) -> None: ...


class TunnelControllerPort(Protocol):
    """Lifecycle of per-channel cloudflared named-tunnel child processes.

    One process per managed channel (each named tunnel has its own connector
    token). ``ensure_running`` is idempotent and respawns when the token
    changes; ``active`` reports which channels currently have a live tunnel so
    the reconciler can stop the ones no longer desired.

    Channels are identified here by **uid**, as they are in the other two
    controllers — see the note in ``runtime_supervision``.
    """

    def running(self, channel_uid: str) -> bool: ...

    def active(self) -> set[str]: ...

    async def ensure_running(self, channel_uid: str, token: str) -> None: ...

    async def ensure_stopped(self, channel_uid: str) -> None: ...

    async def dispose(self) -> None: ...


class WebSocketControllerPort(Protocol):
    """Lifecycle of per-channel SeaTalk WebSocket connections (spec channels/seatalk
    "Carry no ingress fields on websocket delivery").

    The websocket sibling of ``TunnelControllerPort``, with the same reconcile
    shape — one supervised connection per websocket-delivery channel, held
    in-process rather than in a child. The credentials are the app's own
    (``app_id`` + materialized secret): the register handshake authenticates with
    them, which is why this transport needs no signing secret and no public URL.

    ``running(uid)`` means a *supervisor* exists for the channel, not that the
    socket is up — a connection that is retrying is still running, and the
    reconciler must not respawn it every tick. ``state(uid)`` is the honest
    answer about the socket: ``(state, last error)`` where state is one of
    ``connecting | connected | kicked | sdk_missing | error``, and ``None`` when
    this channel has no connector at all.

    Channels are identified here by **uid** — see the note in
    ``runtime_supervision``.
    """

    def running(self, channel_uid: str) -> bool: ...

    def active(self) -> set[str]: ...

    def state(self, channel_uid: str) -> tuple[str, str | None] | None: ...

    async def ensure_running(self, channel_uid: str, app_id: str, app_secret: str) -> None: ...

    async def ensure_stopped(self, channel_uid: str) -> None: ...

    async def dispose(self) -> None: ...
