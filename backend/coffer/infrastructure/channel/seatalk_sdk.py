"""Where SeaTalk's WebSocket SDK is looked for — which we do not ship, and never import.

``seatalk-oapi-sdk-py`` is the only client for SeaTalk's WebSocket Event
Callback. It is distributed from an internal Shopee portal, is absent from
public PyPI, and carries no public licence — so Coffer, which is AGPL-3.0 and
OSS-bound, can neither vendor it into this repository nor declare it as a
dependency. Reimplementing it is not an option either: the frame protocol
behind the register handshake is unpublished.

So it is an **optional runtime dependency the operator supplies**, and it is
imported only by the separate ``coffer-seatalk-bridge`` executable
(``seatalk_bridge``), never by the daemon: the directory it comes from is one
any agent running as the same user can write to, and the daemon of a signed
build can read the master key. This module is the daemon's side of that
contract:

* ``sdk_dir()`` — where the bridge looks: ``$COFFER_SEATALK_SDK_DIR`` when set,
  else ``~/.coffer/vendor`` (machine state beside the class directories, ADR
  storage-is-five-classes-by-nature). (Same per-subsystem env-override
  convention as ``$COFFER_DB_URL``.)
* ``missing_message()`` — the fact a channel reports as ``sdk_missing`` when the
  bridge cannot import the package; ``sdk_location()`` hands the same facts to
  the hand-off that puts it there. The channel keeps retrying and still sends
  (spec channels/seatalk "Load the websocket client library from an
  operator-supplied directory").
"""

from __future__ import annotations

import os
from pathlib import Path

from coffer.application.channel.sdk_handoff import SdkLocation
from coffer.infrastructure.vault.home import vendor_dir

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
    return vendor_dir()


def missing_message(directory: Path | str) -> str:
    """What a channel says while the SDK is not importable from ``directory``.

    A statement of fact, not a procedure: the steps that put the SDK in place
    are a hand-off the status route builds from ``sdk_location()``.
    """
    return (
        f"SeaTalk's WebSocket SDK ({_PACKAGE}) was not found in {directory}, so this "
        f"channel receives nothing until it is there; its outbound sends are "
        f"unaffected. See {DOCS_URL}."
    )


def sdk_location() -> SdkLocation:
    """Where the SDK is looked for, and whether an environment override chose it."""
    return SdkLocation(
        directory=str(sdk_dir()), from_env=bool(os.environ.get("COFFER_SEATALK_SDK_DIR"))
    )
