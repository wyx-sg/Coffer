"""Which kind of failure ended a SeaTalk websocket attempt.

Three answers need three reactions, so the connector asks here first:

* a **kick** — another process registered the same app and took its single
  connection; back off long, do not fight it;
* a **refusal** — SeaTalk refused the app itself: the register handshake (the
  only frame that carries the App ID and App Secret) answered with a non-OK
  code, or the client was built without credentials. A new secret is the fix;
* anything else — DNS, a timeout, a dropped socket — is the network, and
  retrying is the whole of the fix; replacing the secret would not help.

Every match is by class name: the SDK runs in ``coffer-seatalk-bridge``, which
reports the class name of whatever ended the connection, and its internal
module layout is not part of any contract we can pin anyway.
"""

from __future__ import annotations

_REFUSALS = frozenset({"RegisterError", "MissingCredentialError"})


def is_kick(error_class: str | None) -> bool:
    """Whether the SDK's ``KickError`` ended the connection."""
    return error_class == "KickError"


def is_refusal(error_class: str | None) -> bool:
    """Whether SeaTalk refused the app's credentials."""
    return error_class in _REFUSALS
