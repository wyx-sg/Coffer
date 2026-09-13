"""Hold SeaTalk's inbound WebSocket open, and supervise it.

The third inbound-supervision sibling next to ``listener_spawn`` (one callback
child for the whole daemon) and ``tunnel_spawn`` (one cloudflared child per
channel): one *connection* per websocket-delivery channel, held inside this
process. It needs no public URL, no signing secret, no listener and no tunnel —
the register handshake authenticates the socket, and events arrive on it in
exactly the shape the webhook POSTs carry.

Two things make this unlike the other two.

**The SDK is synchronous and thread-based.** ``connect()`` blocks on a register
handshake; ``listen()`` blocks for the life of the connection. Neither may touch
the event loop, so every blocking call goes through ``asyncio.to_thread`` and
``listen()`` runs on a thread we own and join. Inbound events cross back with
``loop.call_soon_threadsafe``, which schedules the ingest coroutine and returns
at once, because the SDK's dispatcher calls our handler *inline on the listen
thread* and acks the event itself the moment the handler returns. So the handler
never waits for the turn, never acks (the dispatcher already did), and never
raises — an exception there would lose the ack AND propagate out of ``listen()``,
dropping the connection over one bad frame.

**The SDK does not reconnect.** Supervision is entirely ours: connect, listen,
and on any failure back off and try again — exponential from 1s capped at 30s.
A *kick* is the exception and backs off a flat 60s: SeaTalk allows one live
connection per app, so a kick means another process (another machine, an older
daemon) has taken this bot over, and racing it would just trade the connection
back and forth. Each state change is logged once, never per attempt.

``state()`` is what the status surface reads and it must not flatter: ``connected``
only while the socket is actually up, and ``sdk_missing``/``error`` carry the
text of what went wrong so the owner can act on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any

from coffer.infrastructure.channel.seatalk_sdk import SeaTalkSdkMissingError, load_sdk

_logger = logging.getLogger(__name__)

_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0
# A kick is not a fault to retry quickly — it is another process holding the
# app's single connection. Back off long enough not to fight it.
_KICK_BACKOFF_SECONDS = 60.0
_JOIN_TIMEOUT_SECONDS = 5.0

# ``(channel_name, envelope) -> None`` — ChannelService.ingest_event in
# production, which does the unknown-channel and adapter-down checks and hands
# the envelope to the same adapter seam the webhook route uses.
IngestFn = Callable[[str, dict[str, Any]], Awaitable[None]]
SdkLoader = Callable[[], ModuleType]


def _is_kick(error: BaseException) -> bool:
    """Whether this exception is the SDK's ``KickError``.

    Matched by class name rather than ``isinstance``: the SDK is imported
    dynamically from an operator-supplied directory, so its error classes are
    not importable at module scope here and its internal module layout is not
    part of any contract we can pin.
    """
    return type(error).__name__ == "KickError"


class SeaTalkWebSocketConnector:
    """One supervised SeaTalk WebSocket connection for one channel."""

    def __init__(
        self,
        name: str,
        app_id: str,
        app_secret: str,
        *,
        ingest: IngestFn,
        loader: SdkLoader = load_sdk,
        backoff_initial: float = _BACKOFF_INITIAL_SECONDS,
        backoff_max: float = _BACKOFF_MAX_SECONDS,
        kick_backoff: float = _KICK_BACKOFF_SECONDS,
        join_timeout: float = _JOIN_TIMEOUT_SECONDS,
    ) -> None:
        self._name = name
        self._app_id = app_id
        self._app_secret = app_secret
        self._ingest = ingest
        self._loader = loader
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._kick_backoff = kick_backoff
        self._join_timeout = join_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        self._thread: threading.Thread | None = None
        self._client: Any = None
        self._stopping = asyncio.Event()
        self._kicked = False
        self._kick_reason = "no reason given"
        self._lock = threading.Lock()
        self._state = "connecting"
        self._error: str | None = None
        self._ingest_tasks: set[asyncio.Task[None]] = set()
        # Observable by tests and by the backoff assertions: how long the
        # supervisor actually slept before each retry.
        self.backoffs: list[float] = []

    # -- state -------------------------------------------------------------

    def state(self) -> tuple[str, str | None]:
        """``(state, last error text)`` — one of
        ``connecting | connected | kicked | sdk_missing | error``."""
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
        self._loop = asyncio.get_running_loop()
        self._stopping.clear()
        self._set_state("connecting", None)
        self._task = asyncio.create_task(self._supervise(), name=f"seatalk-ws:{self._name}")

    async def stop(self) -> None:
        """Stop supervising and take the connection down.

        Closing the client is what unblocks the listening thread; only then is
        joining it meaningful. The join is bounded — a thread wedged inside the
        SDK must not hold up daemon shutdown — and a thread that outlives it is
        reported rather than ignored.
        """
        self._stopping.set()
        await self._close_client()
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            await asyncio.to_thread(thread.join, self._join_timeout)
            if thread.is_alive():  # pragma: no cover - wedged SDK only
                _logger.warning(
                    "channel.websocket.listen_thread_did_not_stop",
                    extra={"channel": self._name},
                )
        for pending in list(self._ingest_tasks):
            pending.cancel()

    async def _close_client(self) -> None:
        client, self._client = self._client, None
        if client is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.to_thread(client.close)

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
                # A kick arrives BOTH ways: the dispatcher calls ``on_kick`` and
                # then raises ``KickError`` out of ``listen()``. The backoff
                # decision belongs here, where the connection has actually ended.
                kicked = _is_kick(e) or self._kicked
                if kicked:
                    self._set_state("kicked", self._kick_detail(e))
                else:
                    self._set_state("error", f"{type(e).__name__}: {e}")
            if self._stopping.is_set():
                return
            wait = self._kick_backoff if kicked else delay
            # A kick is a standing condition, not a fault ladder: it keeps its
            # flat wait and leaves the exponential one where it was.
            delay = self._backoff_initial if kicked else min(delay * 2, self._backoff_max)
            self.backoffs.append(wait)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=wait)

    async def _one_connection(self) -> bool:
        """Hold one connection until it ends. Returns True when it was kicked."""
        sdk = await asyncio.to_thread(self._loader)
        dispatcher = _require(sdk, "EventDispatcher")()
        dispatcher.on_event(self._on_event)
        dispatcher.on_kick(self._on_kick)
        # The SDK ships both of these defaulted to handlers that ``print()``:
        # the envelope one dumps every frame's full JSON, message bodies and
        # all, and the invalid-frame one prints the raw payload. The daemon's
        # stdout is its log file, so leaving them in place would write every
        # private message the owner receives into ~/.coffer/logs. Silence the
        # envelope trace outright and report a bad frame without its contents.
        dispatcher.on_envelope(None)
        dispatcher.on_invalid_frame(self._on_invalid_frame)
        self._kicked = False
        self._set_state("connecting", None)
        client = _require(sdk, "Client")(self._app_id, self._app_secret, dispatcher=dispatcher)
        await asyncio.to_thread(client.connect)
        self._client = client
        self._set_state("connected", None)
        error = await self._listen(client)
        self._client = None
        with contextlib.suppress(Exception):
            await asyncio.to_thread(client.close)
        if error is not None:
            raise error
        # ``listen()`` returning without an error still means the socket is gone.
        if self._kicked:
            self._set_state("kicked", self._kick_detail(None))
        elif not self._stopping.is_set():
            self._set_state("error", "the SeaTalk connection closed")
        return self._kicked

    def _kick_detail(self, error: BaseException | None) -> str:
        reason = str(error) if error is not None and str(error) else self._kick_reason
        return (
            "another process holds this bot's single SeaTalk connection "
            f"and took it over ({reason}); retrying slowly so the two do not "
            "trade it back and forth"
        )

    async def _listen(self, client: Any) -> BaseException | None:
        """Run the SDK's blocking ``listen()`` on a thread we own and join.

        The thread hands its outcome back through a future resolved with
        ``call_soon_threadsafe``, so the supervisor awaits the connection's whole
        lifetime without a thread parked on ``join``.
        """
        loop = asyncio.get_running_loop()
        finished: asyncio.Future[BaseException | None] = loop.create_future()

        def _resolve(error: BaseException | None) -> None:
            if not finished.done():
                finished.set_result(error)

        def _run() -> None:
            outcome: BaseException | None = None
            try:
                client.listen()
            except BaseException as e:
                outcome = e
            finally:
                with contextlib.suppress(RuntimeError):  # loop already closed
                    loop.call_soon_threadsafe(_resolve, outcome)

        thread = threading.Thread(target=_run, name=f"seatalk-ws-listen:{self._name}", daemon=True)
        self._thread = thread
        thread.start()
        try:
            return await finished
        finally:
            # ``_run`` resolves the future in its ``finally``, so the thread is
            # on its way out; joining makes that observable instead of assumed.
            await asyncio.to_thread(thread.join, self._join_timeout)

    # -- inbound bridge (called on the SDK's thread) ------------------------

    def _on_event(self, event: Any) -> None:
        """Hand one event's raw dict to the asyncio side and return at once.

        This must not raise, ever. The SDK's dispatcher calls this inline and
        acks the event only once it returns, so an exception escaping here would
        both lose the ack (SeaTalk redelivers) and propagate out of ``listen()``,
        tearing the connection down over one malformed frame. Everything is
        caught and logged instead.
        """
        try:
            data = getattr(event, "data", None)
            if not isinstance(data, dict):
                _logger.warning(
                    "channel.websocket.event_without_data",
                    extra={"channel": self._name, "event": type(event).__name__},
                )
                return
            loop = self._loop
            if loop is None:  # pragma: no cover - start() always sets it
                return
            with contextlib.suppress(RuntimeError):  # the loop is gone; so are we
                loop.call_soon_threadsafe(self._schedule_ingest, dict(data))
        except Exception:
            _logger.exception(
                "channel.websocket.event_bridge_failed", extra={"channel": self._name}
            )

    def _on_invalid_frame(self, payload: bytes, error: Exception) -> None:
        """Note a frame the SDK could not parse, without logging its contents.

        The payload is whatever SeaTalk sent and may carry message text, so only
        its size and the parse error are recorded — enough to tell a protocol
        change from a one-off, nothing more.
        """
        _logger.warning(
            "channel.websocket.invalid_frame",
            extra={"channel": self._name, "bytes": len(payload), "detail": str(error)},
        )

    def _on_kick(self, envelope: Any) -> None:
        """Record why we were kicked; the dispatcher raises ``KickError`` next.

        Only bookkeeping: the supervision loop owns the state transition and the
        60s backoff, because that is where the connection has ended.
        """
        self._kicked = True
        message = str(getattr(envelope, "message", "") or "")
        self._kick_reason = message or "no reason given"

    def _schedule_ingest(self, envelope: dict[str, Any]) -> None:
        task = asyncio.create_task(self._deliver(envelope))
        self._ingest_tasks.add(task)
        task.add_done_callback(self._reap_ingest)

    async def _deliver(self, envelope: dict[str, Any]) -> None:
        await self._ingest(self._name, envelope)

    def _reap_ingest(self, task: asyncio.Task[None]) -> None:
        self._ingest_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # Never silent: an ingest that failed means a message the owner sent
            # went nowhere.
            _logger.error(
                "channel.websocket.ingest_failed",
                exc_info=task.exception(),
                extra={"channel": self._name},
            )


def _require(sdk: ModuleType, attribute: str) -> Any:
    value = getattr(sdk, attribute, None)
    if value is None:
        raise RuntimeError(
            f"the SeaTalk SDK at {sdk.__file__} exposes no {attribute!r}; "
            f"this is not the seatalk_oapi_sdk package Coffer expects"
        )
    return value
