"""Hold SeaTalk's inbound WebSocket open, and supervise it.

The only way SeaTalk inbound arrives (spec channels/seatalk "Receive every
event over one outbound websocket connection"): one *connection* per SeaTalk
channel. It needs no public URL, no signing secret, no listener and no tunnel —
the register handshake authenticates the socket, and events arrive on it as the
platform's event envelopes.

**The SDK runs in another process.** SeaTalk's SDK is operator-supplied code
from a directory any same-user agent can write to, and this daemon can read the
master key, so the SDK never enters it: each connection attempt is one
``coffer-seatalk-bridge`` process (``seatalk_bridge_process``) that imports the
SDK, holds the socket and writes protocol lines back (``seatalk_bridge``). The
bridge acks each event as soon as it has written it out; this side only reads
lines and schedules ingest, so a slow turn never holds an ack back.

**Nothing reconnects for us.** Supervision is entirely ours: start a bridge,
read it until it ends, and on any failure back off and try again — exponential
from 1s capped at 30s. A *kick* is the exception and backs off a flat 60s:
SeaTalk allows one live connection per app, so a kick means another process
(another machine, an older daemon) has taken this bot over, and racing it would
just trade the connection back and forth. Each state change is logged once,
never per attempt. The supervision loop itself runs under the daemon's task
supervisor, which restarts it should it ever crash. ``state()`` is what the
status surface reads and must not flatter: ``connected`` only while the socket
is up, and ``sdk_missing``/``rejected``/``error`` carry the text of what went
wrong.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from coffer.application.runtime.supervisor import spawn, spawn_restarting
from coffer.infrastructure.channel.seatalk_bridge import protocol as wire
from coffer.infrastructure.channel.seatalk_bridge.protocol import BridgeConfig
from coffer.infrastructure.channel.seatalk_bridge_process import (
    BridgeLauncher,
    BridgeLink,
    spawn_bridge,
)
from coffer.infrastructure.channel.seatalk_sdk import (
    SeaTalkSdkMissingError,
    missing_message,
    sdk_dir,
)
from coffer.infrastructure.channel.seatalk_ws_errors import is_kick, is_refusal

_logger = logging.getLogger(__name__)

_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0
# A kick is not a fault to retry quickly — it is another process holding the
# app's single connection. Back off long enough not to fight it.
_KICK_BACKOFF_SECONDS = 60.0
# A connection that stayed up this long was healthy: its end is SeaTalk's
# routine close, not a fault, so the ladder starts again from the bottom. One
# that dies sooner is flapping and keeps climbing.
_HEALTHY_AFTER_SECONDS = 30.0
# What the bridge may report in a ``notice``; anything else is logged generically.
_NOTICES = frozenset({"event_without_data", "event_bridge_failed"})

# ``(channel_uid, envelope) -> None`` — ChannelService.ingest_event in
# production, which does the unknown-channel and adapter-down checks and hands
# the envelope to the adapter's one ingest seam.
IngestFn = Callable[[str, dict[str, Any]], Awaitable[None]]


class BridgeFailureError(Exception):
    """The bridge reported that the connection ended with an exception."""

    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class


def _describe(error: BaseException) -> str:
    if isinstance(error, BridgeFailureError):
        return f"{error.error_class}: {error}"
    return f"{type(error).__name__}: {error}"


class SeaTalkWebSocketConnector:
    """One supervised SeaTalk WebSocket connection for one channel."""

    def __init__(
        self,
        name: str,
        app_id: str,
        app_secret: str,
        *,
        ingest: IngestFn,
        bridge: BridgeLauncher = spawn_bridge,
        sdk_directory: Callable[[], Path] = sdk_dir,
        backoff_initial: float = _BACKOFF_INITIAL_SECONDS,
        backoff_max: float = _BACKOFF_MAX_SECONDS,
        kick_backoff: float = _KICK_BACKOFF_SECONDS,
        healthy_after: float = _HEALTHY_AFTER_SECONDS,
    ) -> None:
        self._name = name
        self._app_id = app_id
        self._app_secret = app_secret
        self._ingest = ingest
        self._bridge = bridge
        self._sdk_directory = sdk_directory
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._kick_backoff = kick_backoff
        self._healthy_after = healthy_after
        # Monotonic time the current connection registered; None until it does.
        self._connected_since: float | None = None
        self._task: asyncio.Task[None] | None = None
        self._link: BridgeLink | None = None
        self._stopping = asyncio.Event()
        self._kicked = False
        self._kick_reason = "no reason given"
        # ``state()`` is read from request handlers; every field it and the
        # kick bookkeeping touch goes through this lock.
        self._lock = threading.Lock()
        self._state = "connecting"
        self._error: str | None = None
        self._ingest_tasks: set[asyncio.Task[None]] = set()
        # The latest ingest per chat (group_id or DM employee_code); see _schedule_ingest.
        self._chat_tails: dict[str, asyncio.Task[None]] = {}
        # Observable by tests and by the backoff assertions: how long the
        # supervisor actually slept before each retry.
        self.backoffs: list[float] = []

    # -- state -------------------------------------------------------------

    def state(self) -> tuple[str, str | None]:
        """``(state, last error text)`` — one of
        ``connecting | connected | kicked | sdk_missing | rejected | error``:
        ``rejected`` is SeaTalk refusing the app's credentials, ``error`` any
        other failed attempt (the network, a dropped socket)."""
        with self._lock:
            return self._state, self._error

    @property
    def supervising(self) -> bool:
        """Whether the supervision loop is alive (not whether the socket is)."""
        return self._task is not None and not self._task.done()

    def _set_state(self, state: str, error: str | None = None) -> None:
        with self._lock:
            if (state, error) == (self._state, self._error):
                return
            self._state, self._error = state, error
        # One line per transition: a 30s reconnect ladder would otherwise fill
        # the log with the same sentence.
        _logger.info(
            "channel.websocket.state",
            extra={"channel": self._name, "state": state, "detail": error or ""},
        )

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Begin supervising. Returns as soon as the loop is scheduled."""
        if self.supervising:
            return
        self._stopping.clear()
        self._set_state("connecting", None)
        self._task = spawn_restarting(self._supervise, name=f"seatalk-ws:{self._name}")

    async def stop(self) -> None:
        """Stop supervising and take the connection down.

        Closing the bridge's stdin is what makes it close the SDK client and
        exit; the bridge link waits for that (bounded, then terminates it), so
        no bridge process outlives the channel.
        """
        self._stopping.set()
        link = self._link
        if link is not None:
            with contextlib.suppress(Exception):
                await link.close()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        for pending in list(self._ingest_tasks):
            pending.cancel()

    # -- supervision -------------------------------------------------------

    async def _supervise(self) -> None:
        delay = self._backoff_initial
        while not self._stopping.is_set():
            kicked = False
            try:
                kicked = await self._one_connection()
            except asyncio.CancelledError:
                raise
            except SeaTalkSdkMissingError as e:
                # Not a fault to hide: the channel is configured for a transport
                # whose client the operator has not supplied yet. Keep retrying
                # on the ladder so dropping the SDK in needs no daemon restart.
                self._set_state("sdk_missing", str(e))
            except Exception as e:
                # A kick arrives BOTH ways: the bridge reports ``kick`` and then
                # the connection ends with ``KickError``. The backoff decision
                # belongs here, where the connection has actually ended.
                error_class = e.error_class if isinstance(e, BridgeFailureError) else None
                kicked = is_kick(error_class) or self._was_kicked()
                if kicked:
                    self._set_state("kicked", self._kick_detail(e))
                elif is_refusal(error_class):
                    # Still retried on the ladder: a secret replaced under the
                    # same ref, or an app re-enabled on the platform, recovers
                    # with no restart.
                    self._set_state("rejected", _describe(e))
                else:
                    self._set_state("error", _describe(e))
            if self._stopping.is_set():
                return
            if self._was_healthy():
                # Without this the ladder only ever grew: a few DNS failures
                # pushed it to the cap and every later routine close waited
                # the full 30 s before reconnecting.
                delay = self._backoff_initial
            wait = self._kick_backoff if kicked else delay
            # A kick is a standing condition, not a fault ladder: it keeps its
            # flat wait and leaves the exponential one where it was.
            delay = self._backoff_initial if kicked else min(delay * 2, self._backoff_max)
            self.backoffs.append(wait)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=wait)

    async def _one_connection(self) -> bool:
        """Run one bridge until its connection ends. Returns True when it was kicked."""
        self._connected_since = None
        self._clear_kick()
        directory = self._sdk_directory()
        config = BridgeConfig(self._app_id, self._app_secret, str(directory))
        link = await self._bridge(config)
        self._link = link
        try:
            ended = await self._pump(link, directory)
        finally:
            self._link = None
            with contextlib.suppress(Exception):
                await link.close()
        if ended is None:
            if self._stopping.is_set():
                return False
            raise RuntimeError(
                f"the SeaTalk bridge exited without reporting why ({link.exit_detail()})"
            )
        if ended.get("outcome") == wire.OUTCOME_FAILED:
            raise BridgeFailureError(
                str(ended.get("error_class") or "Exception"), str(ended.get("error") or "")
            )
        # A connection that ended without an error still means the socket is gone.
        kicked = self._was_kicked()
        if kicked:
            self._set_state("kicked", self._kick_detail(None))
        elif self._stopping.is_set():
            pass
        elif self._was_healthy():
            # SeaTalk closes long-lived connections on its own every few
            # minutes; reconnecting is the whole of the response, so this is
            # not reported as an error.
            _logger.info("channel.websocket.closed_by_peer", extra={"channel": self._name})
            self._set_state("connecting", None)
        else:
            self._set_state("error", "the SeaTalk connection closed")
        return kicked

    async def _pump(self, link: BridgeLink, directory: Path) -> dict[str, Any] | None:
        """Act on the bridge's messages; return its ``ended`` line, or None at EOF."""
        while (message := await link.receive()) is not None:
            kind = message.get("type")
            if kind == wire.ENDED:
                return message
            if kind == wire.SDK_MISSING:
                raise SeaTalkSdkMissingError(missing_message(directory))
            if kind == wire.LOADED:
                self._set_state("connecting", None)
            elif kind == wire.CONNECTED:
                self._connected_since = time.monotonic()
                self._set_state("connected", None)
            elif kind == wire.EVENT:
                data = message.get("data")
                if isinstance(data, dict):
                    self._schedule_ingest(data)
            elif kind == wire.KICK:
                self._mark_kicked(str(message.get("reason") or "") or "no reason given")
            elif kind == wire.INVALID_FRAME:
                # Size and parse error only: the payload may carry message text.
                _logger.warning(
                    "channel.websocket.invalid_frame",
                    extra={
                        "channel": self._name,
                        "bytes": message.get("bytes"),
                        "detail": str(message.get("detail") or ""),
                    },
                )
            elif kind == wire.NOTICE:
                code = str(message.get("code") or "")
                event = (
                    f"channel.websocket.{code}"
                    if code in _NOTICES
                    else "channel.websocket.bridge_notice"
                )
                _logger.warning(
                    event, extra={"channel": self._name, "detail": str(message.get("detail") or "")}
                )
        return None

    def _was_healthy(self) -> bool:
        """Whether the connection that just ended stayed up past the threshold."""
        since = self._connected_since
        return since is not None and time.monotonic() - since >= self._healthy_after

    # -- kick bookkeeping ----------------------------------------------------

    def _mark_kicked(self, reason: str) -> None:
        with self._lock:
            self._kicked = True
            self._kick_reason = reason

    def _clear_kick(self) -> None:
        with self._lock:
            self._kicked = False

    def _was_kicked(self) -> bool:
        with self._lock:
            return self._kicked

    def _kick_detail(self, error: BaseException | None) -> str:
        with self._lock:
            recorded = self._kick_reason
        reason = str(error) if error is not None and str(error) else recorded
        return (
            "another process holds this bot's single SeaTalk connection "
            f"and took it over ({reason}); retrying slowly so the two do not "
            "trade it back and forth"
        )

    # -- ingest --------------------------------------------------------------

    def _schedule_ingest(self, envelope: dict[str, Any]) -> None:
        # spec channels/seatalk "Hand a chat's events to the channel in arrival
        # order": ingest awaits vary (a forwarded record downloads files), so each
        # event waits for its chat's previous one. Different chats stay concurrent.
        event = envelope["event"] if isinstance(envelope.get("event"), dict) else {}
        key = str(event.get("group_id") or event.get("employee_code") or "")
        deliver = self._deliver(envelope, self._chat_tails.get(key))
        task = spawn(deliver, name=f"seatalk-ingest:{self._name}")
        self._ingest_tasks.add(task)
        task.add_done_callback(self._reap_ingest)
        if key:
            self._chat_tails[key] = task

    async def _deliver(self, envelope: dict[str, Any], after: asyncio.Task[None] | None) -> None:
        if after is not None:
            # ``wait`` rather than ``await``: the predecessor's failure is its own
            # reaper's to log, and cancelling us must not cancel it.
            await asyncio.wait({after})
        await self._ingest(self._name, envelope)

    def _reap_ingest(self, task: asyncio.Task[None]) -> None:
        self._ingest_tasks.discard(task)
        for key in [k for k, tail in self._chat_tails.items() if tail is task]:
            del self._chat_tails[key]  # the chat has gone idle
        if not task.cancelled() and task.exception() is not None:
            # Never silent: a failed ingest is a message the owner sent that went
            # nowhere. The supervisor's crash line carries the traceback.
            _logger.error("channel.websocket.ingest_failed", extra={"channel": self._name})
