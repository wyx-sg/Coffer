"""One-time codes that hand a browser the API token (spec 001 FR-025).

``coffer open`` has the token — it can read ``~/.coffer/daemon.json``. The
browser it launches cannot. Something has to carry the credential across, and
the URL is the only channel a freshly-opened browser will read.

Putting the *token* in the URL is what we refuse: it is long-lived, it unlocks
the credential endpoints, and a URL lands in browser history, in the shell's
scrollback, and in whatever the user pastes into a bug report. FR-012/FR-013
would not survive that.

So the CLI mints a **single-use code** instead. It is valid for
:data:`CODE_TTL_SECONDS`, dies the moment it is redeemed, and buys exactly one
thing: the token, returned in a response body the page stores itself. A code
recovered from history later is inert — either it was already spent, or it has
expired.

The store is process-local and deliberately tiny. Codes do not survive a daemon
restart, which is correct: a restarted daemon has rotated its token anyway.
"""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass

# Long enough that guessing is hopeless against a loopback-only listener that
# also expires the code within the minute.
_CODE_BYTES = 32

CODE_TTL_SECONDS = 60.0

# Refuse to accumulate codes if something ever mints them in a loop. Well past
# any real use — `coffer open` mints one at a time.
_MAX_LIVE_CODES = 16


@dataclass(frozen=True)
class _Entry:
    code: str
    expires_at: float


_LIVE: list[_Entry] = []


def _purge(now: float) -> None:
    _LIVE[:] = [e for e in _LIVE if e.expires_at > now]


def issue_code(*, now: float | None = None) -> str:
    """Mint a single-use code for the browser hand-off."""
    current = time.monotonic() if now is None else now
    _purge(current)
    if len(_LIVE) >= _MAX_LIVE_CODES:
        # Drop the oldest rather than refusing: the caller is the authenticated
        # CLI, and a stuck queue should not lock the user out of their own UI.
        del _LIVE[0]
    code = secrets.token_urlsafe(_CODE_BYTES)
    _LIVE.append(_Entry(code=code, expires_at=current + CODE_TTL_SECONDS))
    return code


def redeem_code(code: str, *, now: float | None = None) -> bool:
    """Consume ``code``; True when it was live. Any code is spent by one call.

    Compared with :func:`hmac.compare_digest` against every live entry so a
    wrong code costs the same time whichever entry it nearly matched.
    """
    current = time.monotonic() if now is None else now
    _purge(current)
    matched = -1
    for index, entry in enumerate(_LIVE):
        if hmac.compare_digest(entry.code, code):
            matched = index
    if matched < 0:
        return False
    del _LIVE[matched]
    return True


def reset() -> None:
    """Drop every live code — daemon shutdown and tests."""
    _LIVE.clear()
