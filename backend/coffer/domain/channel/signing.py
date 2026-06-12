"""SeaTalk event-callback signature (pure stdlib).

SeaTalk signs every callback POST with `sha256(raw_body + signing_secret)`
(lowercase hex) in the `Signature` header.
"""

from __future__ import annotations

import hashlib
import hmac


def seatalk_signature(body: bytes, signing_secret: str) -> str:
    """Compute the expected `Signature` header for a callback body."""
    return hashlib.sha256(body + signing_secret.encode("utf-8")).hexdigest()


def verify_seatalk_signature(body: bytes, signing_secret: str, signature: str) -> bool:
    """Constant-time comparison of the presented signature."""
    expected = seatalk_signature(body, signing_secret)
    return hmac.compare_digest(expected, signature.strip().lower())
