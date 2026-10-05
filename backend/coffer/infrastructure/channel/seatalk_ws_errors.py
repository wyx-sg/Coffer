"""Which kind of failure ended a SeaTalk websocket attempt.

Three answers need three reactions, so the connector asks here first:

* a **kick** — another process registered the same app and took its single
  connection; back off long, do not fight it;
* a **refusal** — SeaTalk refused the app itself: the register handshake (the
  only frame that carries the App ID and App Secret) answered with a non-OK
  code, or the client was built without credentials. A new secret is the fix;
* anything else — DNS, a timeout, a dropped socket — is the network, and
  retrying is the whole of the fix; replacing the secret would not help.

Every match is by class name rather than ``isinstance``: the SDK is imported
dynamically from an operator-supplied directory, so its error classes are not
importable at module scope here and its internal module layout is not part of
any contract we can pin.
"""

from __future__ import annotations

_REFUSALS = frozenset({"RegisterError", "MissingCredentialError"})


def is_kick(error: BaseException) -> bool:
    """Whether this exception is the SDK's ``KickError``."""
    return type(error).__name__ == "KickError"


def is_refusal(error: BaseException) -> bool:
    """Whether SeaTalk refused the app's credentials."""
    return type(error).__name__ in _REFUSALS
