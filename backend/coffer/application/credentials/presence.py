"""Presence grants: the daemon's proof that a present human approved one operation.

Spec secret "Release plaintext only to a present human in the desktop
app"; ADR only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, rules
1 to 3. The desktop shell runs a LocalAuthentication check (Touch ID or the login
password) for each operation, with no reuse window. When it passes, the shell
asks the daemon for a one-time challenge bound to that operation and its
target, signs it, and sends the signature with the request. The daemon releases
plaintext, applies an approval or writes a key backup only against a signature
that verifies, for that operation and that target, once.

The signing key is derived from the master key (``HMAC-SHA256(master_key,
GRANT_KEY_CONTEXT)``). In a signed release the master key sits in a Keychain
access group only Coffer's Developer-ID binaries can read, so a process an
agent controls cannot derive it; the shell is the only one of those binaries
whose code signs a grant. In a development build the key is a file, which an
agent could read — the daemon reports that build as ``development`` and the
docs say the boundary does not hold there.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as _secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from coffer.domain.credential_errors import PresenceGrantInvalid
from coffer.domain.secrets import GRANT_KEY_CONTEXT, GRANT_OPS, grant_message

#: How long a challenge stays redeemable. Long enough for a Touch ID prompt,
#: short enough that a stolen nonce is useless by the time anyone reads it.
CHALLENGE_TTL_SECONDS = 120.0
#: Outstanding challenges kept at once; the oldest goes first.
_MAX_OUTSTANDING = 64


def derive_grant_key(master_key: bytes) -> bytes:
    """The grant-signing key: never the master key itself, never stored."""
    return hmac.new(master_key.strip(), GRANT_KEY_CONTEXT, hashlib.sha256).digest()


def sign_grant(grant_key: bytes, op: str, target: str, nonce: str) -> str:
    """What the desktop shell computes; here for the daemon's check and tests."""
    return hmac.new(grant_key, grant_message(op, target, nonce), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class Challenge:
    nonce: str
    op: str
    target: str
    expires_at: float


class PresenceGrants:
    """Issue and redeem one-time, operation-bound presence challenges."""

    def __init__(
        self,
        grant_key: Callable[[], bytes | None],
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._grant_key = grant_key
        self._clock = clock
        self._outstanding: dict[str, Challenge] = {}

    def challenge(self, op: str, target: str) -> Challenge:
        if op not in GRANT_OPS:
            raise PresenceGrantInvalid(f"unknown grant operation {op!r}")
        self._expire()
        while len(self._outstanding) >= _MAX_OUTSTANDING:
            self._outstanding.pop(next(iter(self._outstanding)))
        issued = Challenge(
            nonce=_secrets.token_urlsafe(24),
            op=op,
            target=target,
            expires_at=self._clock() + CHALLENGE_TTL_SECONDS,
        )
        self._outstanding[issued.nonce] = issued
        return issued

    def redeem(self, op: str, target: str, nonce: str, signature: str) -> None:
        """Verify and consume a grant, or raise ``PresenceGrantInvalid``.

        The nonce is consumed whether or not the signature verifies, so a
        guessed signature cannot be retried against the same challenge.
        """
        self._expire()
        issued = self._outstanding.pop(nonce, None)
        if issued is None:
            raise PresenceGrantInvalid("the presence grant is unknown, used or expired")
        if (issued.op, issued.target) != (op, target):
            raise PresenceGrantInvalid("the presence grant was issued for another operation")
        key = self._grant_key()
        if key is None:
            raise PresenceGrantInvalid("no master key to verify a presence grant against")
        expected = sign_grant(key, op, target, nonce)
        if not hmac.compare_digest(expected, signature.strip().lower()):
            raise PresenceGrantInvalid("the presence grant is not signed by the Coffer app")

    def _expire(self) -> None:
        now = self._clock()
        for nonce in [n for n, c in self._outstanding.items() if c.expires_at <= now]:
            del self._outstanding[nonce]
