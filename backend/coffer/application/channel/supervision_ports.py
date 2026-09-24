"""Port for the inbound plumbing a SeaTalk channel needs beside its adapter.

One supervised thing, which is not the transport adapter itself: one SeaTalk
websocket connection per channel, the only way SeaTalk inbound arrives (spec
channels/seatalk "Receive every event over one outbound websocket
connection"). ``ChannelRuntime`` reconciles it (see ``runtime_supervision``),
which is why its port sits here rather than among the message-flow ports in
``ports``.
"""

from __future__ import annotations

from typing import Protocol


class WebSocketControllerPort(Protocol):
    """Lifecycle of per-channel SeaTalk WebSocket connections (spec channels/seatalk
    "Receive every event over one outbound websocket connection").

    One supervised connection per enabled SeaTalk channel, held in-process
    rather than in a child. The credentials are the app's own
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
