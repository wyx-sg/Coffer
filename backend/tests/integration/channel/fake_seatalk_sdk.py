"""A fake ``seatalk_oapi_sdk``, because the real one cannot be in CI.

SeaTalk's official WebSocket SDK is not on public PyPI and carries no public
licence, so it is never installed here and never vendored. This fake IS the
contract Coffer codes against, written from the real package's source:

* ``Client(app_id, app_secret, ws_url=..., dispatcher=..., ...)`` with a blocking
  ``connect()`` and a blocking ``listen()``, plus ``ack(callback_id)`` and
  ``close()``. ``close()`` is what ends ``listen()`` — the real client closes the
  socket, which makes its read raise and the loop return.
* ``EventDispatcher()`` with chainable ``on_event`` / ``on_kick`` registration.
  The real dispatcher calls ``on_event(event)`` INLINE on the listen thread and
  then acks the event itself, and on a kick calls ``on_kick(envelope)`` and then
  raises ``KickError`` out of ``listen()``. This fake does both the same way, so
  a handler that blocked or raised would fail a test here exactly as it would
  strand an ack in production.
* ``Event(app_id, callback_id, data, rid, sid)`` where ``data`` is the raw event
  dict — byte-identical in shape to the webhook JSON body.
* The error classes: ``SopConnError`` and the specific ones, including
  ``KickError(message, envelope)`` and ``WebSocketClosedError(code, reason)``.

Each connection's behaviour is scripted: ``plan`` holds one callable per
``listen()`` call, so a test says "this connection delivers an event and stays
up", "this one is kicked", "this one drops".
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

_PACKAGE = "seatalk_oapi_sdk"


@dataclass
class FakeSeaTalkSdk:
    """The fake module plus everything a test wants to assert about it."""

    module: ModuleType
    # One entry per ``listen()`` call, in order; the last entry repeats once the
    # list is exhausted (so "keep dropping" needs one entry, not ten).
    plan: list[Callable[[Any], None]] = field(default_factory=list)
    connects: list[tuple[str, str]] = field(default_factory=list)
    connect_errors: list[BaseException | None] = field(default_factory=list)
    acks: list[str] = field(default_factory=list)
    closes: int = 0
    listen_threads: list[threading.Thread] = field(default_factory=list)
    # One entry per Client built, so a test can assert what the connector did
    # to the dispatcher it handed over.
    dispatchers: list[Any] = field(default_factory=list)

    @property
    def connections(self) -> int:
        return len(self.connects)


@dataclass
class FakeEvent:
    app_id: str
    callback_id: str
    data: dict[str, Any]
    rid: str = "rid-1"
    sid: str = "sid-1"


@dataclass
class FakeEnvelope:
    message: str = ""


def envelope(event_type: str = "message_from_bot_subscriber", **event: Any) -> dict[str, Any]:
    """A raw SeaTalk event envelope in the shape both transports carry."""
    return {
        "event_id": "evt-1",
        "event_type": event_type,
        "timestamp": 1771000000,
        "app_id": "app-1",
        "event": event
        or {
            "employee_code": "emp-1",
            "message": {"tag": "text", "text": {"content": "hello"}},
        },
    }


def deliver(data: dict[str, Any], *, callback_id: str = "cb-1") -> Callable[[Any], None]:
    """Dispatch one event on this connection, then hold the socket open."""

    def _run(client: Any) -> None:
        client.dispatch_event(data, callback_id=callback_id)
        client.block_until_closed()

    return _run


def hold() -> Callable[[Any], None]:
    """A healthy connection that just stays up until closed."""

    def _run(client: Any) -> None:
        client.block_until_closed()

    return _run


def drop(reason: str = "read failed") -> Callable[[Any], None]:
    """The socket dies under us: the SDK raises and does not reconnect."""

    def _run(client: Any) -> None:
        raise client.sdk.WebSocketClosedError(1006, reason)

    return _run


def kick(message: str = "another connection registered") -> Callable[[Any], None]:
    """Another process took the app's single connection over."""

    def _run(client: Any) -> None:
        client.dispatch_kick(message)

    return _run


def _printing_handler(envelope: Any) -> None:
    """Stands in for the real SDK's default envelope handler, which prints."""
    print(envelope)


def _printing_invalid_frame_handler(payload: bytes, err: Exception) -> None:
    """Stands in for the real SDK's default invalid-frame handler, which prints."""
    print(payload, err)


def build_fake_sdk() -> FakeSeaTalkSdk:
    """Build the fake module without touching ``sys.modules``."""
    module = ModuleType(_PACKAGE)
    module.__file__ = "<fake seatalk_oapi_sdk>"
    handle = FakeSeaTalkSdk(module=module)

    class SopConnError(Exception): ...

    class MissingCredentialError(SopConnError): ...

    class AlreadyConnectedError(SopConnError): ...

    class NotConnectedError(SopConnError): ...

    class NotRegisteredError(SopConnError): ...

    class MissingCallbackIDError(SopConnError): ...

    class RegisterError(SopConnError):
        def __init__(self, code: int = 0, message: str = "") -> None:
            super().__init__(f"register failed: {code} {message}")
            self.code, self.message = code, message

    class KickError(SopConnError):
        def __init__(self, message: str = "", env: Any = None) -> None:
            super().__init__(message)
            self.message, self.envelope = message, env

    class WebSocketClosedError(Exception):
        def __init__(self, code: int = 0, reason: str = "") -> None:
            super().__init__(f"websocket closed: {code} {reason}")
            self.code, self.reason = code, reason

    class EventDispatcher:
        def __init__(self) -> None:
            self.event_handler: Callable[[FakeEvent], None] | None = None
            self.kick_handler: Callable[[FakeEnvelope], None] | None = None
            # The real SDK defaults BOTH of these to handlers that ``print()``
            # — the envelope one dumps every frame's full JSON, message bodies
            # included. Defaulting them the same way here is what lets a test
            # catch a connector that forgets to silence them, because the
            # daemon's stdout is its log file.
            self.envelope_handler: Callable[[Any], None] | None = _printing_handler
            self.invalid_frame_handler: Callable[[bytes, Exception], None] | None = (
                _printing_invalid_frame_handler
            )

        def on_event(self, handler: Callable[[FakeEvent], None] | None) -> EventDispatcher:
            self.event_handler = handler
            return self

        def on_kick(self, handler: Callable[[FakeEnvelope], None] | None) -> EventDispatcher:
            self.kick_handler = handler
            return self

        def on_envelope(self, handler: Callable[[Any], None] | None) -> EventDispatcher:
            self.envelope_handler = handler
            return self

        def on_invalid_frame(
            self, handler: Callable[[bytes, Exception], None] | None
        ) -> EventDispatcher:
            self.invalid_frame_handler = handler
            return self

    class Client:
        sdk = module

        def __init__(
            self,
            app_id: str,
            app_secret: str,
            ws_url: str = "wss://ws-openapi.haiserve.com/ws/bot",
            dispatcher: EventDispatcher | None = None,
            ping_interval: float = 15.0,
            **_: Any,
        ) -> None:
            self.app_id, self.app_secret, self.ws_url = app_id, app_secret, ws_url
            self.dispatcher = dispatcher or EventDispatcher()
            handle.dispatchers.append(self.dispatcher)
            self._closed = threading.Event()

        # -- what the connector calls --------------------------------------

        def connect(self) -> str:
            handle.connects.append((self.app_id, self.app_secret))
            if handle.connect_errors:
                error = handle.connect_errors.pop(0)
                if error is not None:
                    raise error
            return "registered"

        def listen(self) -> None:
            handle.listen_threads.append(threading.current_thread())
            script = handle.plan.pop(0) if len(handle.plan) > 1 else (handle.plan or [hold()])[0]
            script(self)

        def ack(self, callback_id: str) -> None:
            if not callback_id:
                raise MissingCallbackIDError("seatalk oapi sdk: missing callback id")
            handle.acks.append(callback_id)

        def close(self) -> None:
            handle.closes += 1
            self._closed.set()

        # -- what a script calls -------------------------------------------

        def dispatch_event(self, data: dict[str, Any], *, callback_id: str = "cb-1") -> None:
            """Exactly the real dispatcher's order: handler inline, then ack."""
            handler = self.dispatcher.event_handler
            if handler is None:
                return
            handler(FakeEvent(app_id=self.app_id, callback_id=callback_id, data=data))
            self.ack(callback_id)

        def dispatch_kick(self, message: str) -> None:
            env = FakeEnvelope(message=message)
            if self.dispatcher.kick_handler is not None:
                self.dispatcher.kick_handler(env)
            raise KickError(message, env)

        def block_until_closed(self) -> None:
            self._closed.wait(timeout=10.0)

    module.Client = Client  # type: ignore[attr-defined]
    module.EventDispatcher = EventDispatcher  # type: ignore[attr-defined]
    module.Event = FakeEvent  # type: ignore[attr-defined]
    module.Envelope = FakeEnvelope  # type: ignore[attr-defined]
    module.SopConnError = SopConnError  # type: ignore[attr-defined]
    module.MissingCredentialError = MissingCredentialError  # type: ignore[attr-defined]
    module.AlreadyConnectedError = AlreadyConnectedError  # type: ignore[attr-defined]
    module.NotConnectedError = NotConnectedError  # type: ignore[attr-defined]
    module.NotRegisteredError = NotRegisteredError  # type: ignore[attr-defined]
    module.MissingCallbackIDError = MissingCallbackIDError  # type: ignore[attr-defined]
    module.RegisterError = RegisterError  # type: ignore[attr-defined]
    module.KickError = KickError  # type: ignore[attr-defined]
    module.WebSocketClosedError = WebSocketClosedError  # type: ignore[attr-defined]
    module.__version__ = "0.1.0-fake"  # type: ignore[attr-defined]
    return handle


def installed_fake_sdk() -> Iterator[FakeSeaTalkSdk]:
    """Put the fake in ``sys.modules`` for the duration, then clean up."""
    handle = build_fake_sdk()
    previous = sys.modules.get(_PACKAGE)
    sys.modules[_PACKAGE] = handle.module
    try:
        yield handle
    finally:
        if previous is None:
            sys.modules.pop(_PACKAGE, None)
        else:
            sys.modules[_PACKAGE] = previous


def write_fake_sdk_package(directory: Path, *, marker: str = "vendored") -> Path:
    """Write a minimal importable ``seatalk_oapi_sdk`` package under ``directory``.

    For the loader's own tests: what matters there is that ``load_sdk`` finds a
    package by path, not what the package can do.
    """
    package = directory / _PACKAGE
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(f'__version__ = "0.1.0"\nMARKER = "{marker}"\n')
    return package
