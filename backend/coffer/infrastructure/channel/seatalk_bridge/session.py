"""Import SeaTalk's SDK and hold one connection with it, inside the bridge.

The SDK is synchronous and thread-based: ``connect()`` blocks on the register
handshake, ``listen()`` blocks for the life of the connection, and its
dispatcher calls our event handler INLINE on the listen thread and acks the
event the moment the handler returns. So the handler only writes the event to
stdout and returns, and never raises — an exception there would lose the ack
and propagate out of ``listen()``, dropping the connection over one bad frame.

The SDK does not reconnect, and neither does the bridge: one process is one
connection. Supervision — back-off, kick handling, state — is the daemon's.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from coffer.infrastructure.channel.seatalk_bridge.protocol import (
    CONNECTED,
    ENDED,
    EVENT,
    INVALID_FRAME,
    KICK,
    LOADED,
    NOTICE,
    OUTCOME_CLOSED,
    OUTCOME_FAILED,
    SDK_MISSING,
    SDK_PACKAGE,
    BridgeConfig,
    Emitter,
)

SdkLoader = Callable[[], ModuleType]


def import_sdk(sdk_dir: str) -> ModuleType:
    """Import ``seatalk_oapi_sdk``, with ``sdk_dir`` APPENDED to ``sys.path``.

    Appended, not prepended: a file dropped into the vendor directory must not
    be able to shadow a standard-library or bundled module of the same name.
    """
    directory = Path(sdk_dir).expanduser()
    entry = str(directory)
    if directory.is_dir() and entry not in sys.path:
        sys.path.append(entry)
    return importlib.import_module(SDK_PACKAGE)


def open_session(load: SdkLoader, config: BridgeConfig, emitter: Emitter) -> Session | None:
    """Import the SDK and build a session, or report why not and return None."""
    try:
        sdk = load()
    except ModuleNotFoundError as e:
        if e.name != SDK_PACKAGE:
            # The package is there but one of ITS imports is not: not "missing"
            # but a broken install, and the class name and text say which.
            _failed(emitter, e, prefix=f"importing {SDK_PACKAGE} failed: ")
            return None
        emitter.emit(SDK_MISSING, dir=config.sdk_dir, detail=f"{type(e).__name__}: {e}")
        return None
    except Exception as e:
        _failed(emitter, e, prefix=f"importing {SDK_PACKAGE} failed: ")
        return None
    emitter.emit(LOADED, version=str(getattr(sdk, "__version__", "") or ""))
    return Session(sdk, config, emitter)


def _failed(emitter: Emitter, error: BaseException, *, prefix: str = "") -> None:
    emitter.emit(
        ENDED,
        outcome=OUTCOME_FAILED,
        error_class=type(error).__name__,
        error=f"{prefix}{error}",
    )


def _require(sdk: ModuleType, attribute: str) -> Any:
    value = getattr(sdk, attribute, None)
    if value is None:
        raise RuntimeError(
            f"the SeaTalk SDK at {getattr(sdk, '__file__', '?')} exposes no {attribute!r}; "
            f"this is not the {SDK_PACKAGE} package Coffer expects"
        )
    return value


class Session:
    """One SeaTalk connection. ``run()`` blocks; ``close()`` ends it from any thread."""

    def __init__(self, sdk: ModuleType, config: BridgeConfig, emitter: Emitter) -> None:
        self._sdk = sdk
        self._config = config
        self._emitter = emitter
        self._lock = threading.Lock()
        self._client: Any = None
        self._closed = False

    def run(self) -> None:
        """Connect and listen until the connection ends; always emits ``ended`` last."""
        try:
            client = self._build_client()
            with self._lock:
                if self._closed:
                    self._emitter.emit(ENDED, outcome=OUTCOME_CLOSED, error_class=None, error=None)
                    return
                self._client = client
            client.connect()
            self._emitter.emit(CONNECTED)
            client.listen()
        except Exception as e:
            _failed(self._emitter, e)
        else:
            self._emitter.emit(ENDED, outcome=OUTCOME_CLOSED, error_class=None, error=None)
        finally:
            self.close()

    def close(self) -> None:
        """Close the client, which is what makes a blocked ``listen()`` return."""
        with self._lock:
            self._closed = True
            client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    def _build_client(self) -> Any:
        dispatcher = _require(self._sdk, "EventDispatcher")()
        dispatcher.on_event(self._on_event)
        dispatcher.on_kick(self._on_kick)
        # The SDK ships both of these defaulted to handlers that ``print()``:
        # the envelope one dumps every frame's full JSON, message bodies and
        # all, and the invalid-frame one prints the raw payload. The bridge's
        # stdout is already /dev/null, but silencing them keeps message bodies
        # out of every stream; a bad frame is reported without its contents.
        dispatcher.on_envelope(None)
        dispatcher.on_invalid_frame(self._on_invalid_frame)
        client_class = _require(self._sdk, "Client")
        return client_class(self._config.app_id, self._config.app_secret, dispatcher=dispatcher)

    # -- called by the SDK, on its threads ----------------------------------

    def _on_event(self, event: Any) -> None:
        """Forward one event's raw dict and return at once; never raise."""
        try:
            data = getattr(event, "data", None)
            if not isinstance(data, dict):
                self._emitter.emit(NOTICE, code="event_without_data", detail=type(event).__name__)
                return
            self._emitter.emit(EVENT, data=data)
        except Exception as e:
            with contextlib.suppress(Exception):
                self._emitter.emit(NOTICE, code="event_bridge_failed", detail=type(e).__name__)

    def _on_kick(self, envelope: Any) -> None:
        """Report why; the SDK's dispatcher raises ``KickError`` next."""
        with contextlib.suppress(Exception):
            reason = str(getattr(envelope, "message", "") or "")
            self._emitter.emit(KICK, reason=reason)

    def _on_invalid_frame(self, payload: bytes, error: Exception) -> None:
        """Note a frame the SDK could not parse — its size and the parse error only."""
        with contextlib.suppress(Exception):
            self._emitter.emit(INVALID_FRAME, bytes=len(payload), detail=str(error))
