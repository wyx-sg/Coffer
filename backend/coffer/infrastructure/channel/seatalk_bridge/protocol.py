"""The wire between the daemon and ``coffer-seatalk-bridge``.

In: exactly one JSON line on stdin, ``{"app_id", "app_secret", "sdk_dir"}`` —
the secret never travels in argv or the environment, where ``ps`` and every
child would see it. The daemon then keeps stdin open; EOF means "stop".

Out: one JSON object per line on stdout, each with a ``type``:

* ``sdk_missing`` ``{dir, detail}`` — ``seatalk_oapi_sdk`` is not importable;
  the bridge exits straight after.
* ``loaded`` ``{version}`` — the SDK imported; a connection is being made.
* ``connected`` — the register handshake succeeded.
* ``event`` ``{data}`` — one event's raw envelope, emitted before the SDK acks it.
* ``kick`` ``{reason}`` — another process took the app's single connection.
* ``invalid_frame`` ``{bytes, detail}`` — a frame the SDK could not parse;
  never its contents.
* ``notice`` ``{code, detail}`` — something worth a log line (an event with no
  data dict, an event that could not be forwarded).
* ``ended`` ``{outcome, error_class, error}`` — the last line: ``closed`` when
  the connection simply ended, ``failed`` with the exception's class name (the
  daemon classifies kicks and refusals by it) and its text.

Every string leaving the bridge has the app secret scrubbed out of it. Standard
library only.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

SDK_PACKAGE = "seatalk_oapi_sdk"

SDK_MISSING = "sdk_missing"
LOADED = "loaded"
CONNECTED = "connected"
EVENT = "event"
KICK = "kick"
INVALID_FRAME = "invalid_frame"
NOTICE = "notice"
ENDED = "ended"

OUTCOME_CLOSED = "closed"
OUTCOME_FAILED = "failed"

_REDACTED = "[redacted]"


@dataclass(frozen=True)
class BridgeConfig:
    """What one bridge process needs to hold one channel's connection."""

    app_id: str
    app_secret: str
    sdk_dir: str

    def __repr__(self) -> str:  # never the secret, not even in a traceback
        return f"BridgeConfig(app_id={self.app_id!r}, sdk_dir={self.sdk_dir!r})"


def encode_config(config: BridgeConfig) -> bytes:
    body = {"app_id": config.app_id, "app_secret": config.app_secret, "sdk_dir": config.sdk_dir}
    return json.dumps(body).encode("utf-8") + b"\n"


def decode_config(line: bytes | str) -> BridgeConfig:
    """Parse the config line; ``ValueError`` when it is not one."""
    try:
        body = json.loads(line)
    except (TypeError, ValueError) as e:
        raise ValueError("the bridge's config line is not JSON") from e
    if not isinstance(body, dict):
        raise ValueError("the bridge's config line is not an object")
    app_id, app_secret, sdk_dir = (body.get(k) for k in ("app_id", "app_secret", "sdk_dir"))
    if not (isinstance(app_id, str) and isinstance(app_secret, str) and isinstance(sdk_dir, str)):
        raise ValueError("the bridge's config needs app_id, app_secret and sdk_dir strings")
    return BridgeConfig(app_id=app_id, app_secret=app_secret, sdk_dir=sdk_dir)


def scrub(text: str, secret: str) -> str:
    """``text`` with every occurrence of ``secret`` replaced."""
    return text.replace(secret, _REDACTED) if secret else text


class Emitter:
    """Writes protocol lines, one at a time, from any thread.

    The SDK calls the event handler on its listen thread and may call the kick
    handler from another, so writes are serialised. A write that fails (the
    daemon is gone) marks the emitter broken and calls ``on_broken`` once, so
    the session can shut down instead of talking to nobody.
    """

    def __init__(self, write: Callable[[bytes], None], *, secret: str) -> None:
        self._write = write
        self._secret = secret
        self._lock = threading.Lock()
        self.broken = False
        self.on_broken: Callable[[], None] | None = None

    def emit(self, kind: str, **fields: Any) -> None:
        body: dict[str, Any] = {"type": kind}
        for key, value in fields.items():
            body[key] = scrub(value, self._secret) if isinstance(value, str) else value
        line = json.dumps(body, default=str).encode("utf-8") + b"\n"
        callback: Callable[[], None] | None = None
        with self._lock:
            if self.broken:
                return
            try:
                self._write(line)
            except OSError:
                self.broken = True
                callback = self.on_broken
        if callback is not None:
            callback()


__all__ = [
    "CONNECTED",
    "ENDED",
    "EVENT",
    "INVALID_FRAME",
    "KICK",
    "LOADED",
    "NOTICE",
    "OUTCOME_CLOSED",
    "OUTCOME_FAILED",
    "SDK_MISSING",
    "SDK_PACKAGE",
    "BridgeConfig",
    "Emitter",
    "decode_config",
    "encode_config",
    "scrub",
]
