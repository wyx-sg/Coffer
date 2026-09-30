"""Locate and import SeaTalk's official WebSocket SDK, which we do not ship.

``seatalk-oapi-sdk-py`` is the only client for SeaTalk's WebSocket Event
Callback. It is distributed from an internal Shopee portal, is absent from
public PyPI, and carries no public licence — so Coffer, which is MIT and
OSS-bound, can neither vendor it into this repository nor declare it as a
dependency. Reimplementing it is not an option either: the frame protocol
behind the register handshake is unpublished.

So it is an **optional runtime dependency the operator supplies**. This module
is the whole of that contract:

* ``sdk_dir()`` — where we look: ``$COFFER_SEATALK_SDK_DIR`` when set, else
  ``~/.coffer/vendor``. (Same per-subsystem env-override convention as
  ``$COFFER_KNOWLEDGE_ROOT``.)
* ``load_sdk()`` — prepend that directory to ``sys.path`` *only when it exists*,
  then import the package. The import is attempted lazily, never at daemon
  import time, so a daemon with no SDK starts exactly as it always did.
* When the package cannot be imported, ``SeaTalkSdkMissingError`` says where we
  looked and where to read about it; ``sdk_location()`` hands the same facts
  to the hand-off that puts it there. A websocket channel then reports ``sdk_missing``
  and keeps retrying; nothing crashes. An installation without the SDK — which
  is what an outside user of this project gets — has no SeaTalk inbound: its
  SeaTalk channels report ``sdk_missing`` and still send (spec channels/seatalk
  "Load the websocket client library from an operator-supplied directory").
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path
from types import ModuleType

from coffer.application.channel.sdk_handoff import SdkLocation

_logger = logging.getLogger(__name__)

_PACKAGE = "seatalk_oapi_sdk"
#: SeaTalk's own page for the SDK — where the person downloads it.
DOCS_URL = "https://open.seatalk.io/docs/WebSocket-Event-Callback"


class SeaTalkSdkMissingError(RuntimeError):
    """The operator-supplied SeaTalk WebSocket SDK is not importable."""


def sdk_dir() -> Path:
    """The directory the operator drops the SDK package into."""
    override = os.environ.get("COFFER_SEATALK_SDK_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".coffer" / "vendor"


def load_sdk() -> ModuleType:
    """Import ``seatalk_oapi_sdk``, adding the vendor directory to the path.

    Idempotent in both halves: the vendor directory is inserted into
    ``sys.path`` at most once (a reconnect ladder calls this every few seconds,
    and a path that grows per attempt would be a slow leak), and a second call
    after a successful import returns the already-imported module.
    """
    directory = sdk_dir()
    entry = str(directory)
    if directory.is_dir() and entry not in sys.path:
        sys.path.insert(0, entry)
        _logger.info("channel.seatalk_sdk.path_added", extra={"dir": entry})
    existing = sys.modules.get(_PACKAGE)
    if existing is not None:
        return existing
    try:
        return importlib.import_module(_PACKAGE)
    except ImportError as e:
        # A statement of fact, not a procedure: the steps that put the SDK in
        # place are a hand-off the status route builds from ``sdk_location()``
        # (spec channels/seatalk "Load the websocket client library from an
        # operator-supplied directory").
        raise SeaTalkSdkMissingError(
            f"SeaTalk's WebSocket SDK ({_PACKAGE}) was not found in {entry}, so this "
            f"channel receives nothing until it is there; its outbound sends are "
            f"unaffected. See {DOCS_URL}."
        ) from e


def sdk_location() -> SdkLocation:
    """Where the SDK is looked for, and whether an environment override chose it."""
    return SdkLocation(
        directory=str(sdk_dir()), from_env=bool(os.environ.get("COFFER_SEATALK_SDK_DIR"))
    )
