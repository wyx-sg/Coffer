"""Pairing codes — the owner-binding security boundary.

Codes are memory-only by design: a daemon restart drops them and the user
re-issues. 8 characters from an unambiguous alphabet, single use, 1-hour TTL,
bounded wrong guesses (exhaustion invalidates the code). Fail closed.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
_CODE_LENGTH = 8
_DEFAULT_TTL_SECONDS = 3600
_DEFAULT_MAX_ATTEMPTS = 10


@dataclass
class _Pending:
    code: str
    expires_at: datetime
    attempts_left: int


class PairingManager:
    """Issue and claim pairing codes, one pending code per channel."""

    def __init__(
        self,
        *,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._now = now_fn or (lambda: datetime.now(tz=UTC))
        self._pending: dict[str, _Pending] = {}

    def issue(self, channel: str) -> tuple[str, datetime]:
        """Generate a fresh code for the channel, replacing any pending one."""
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
        expires_at = self._now() + timedelta(seconds=self._ttl)
        self._pending[channel] = _Pending(
            code=code, expires_at=expires_at, attempts_left=self._max_attempts
        )
        return code, expires_at

    def pending(self, channel: str) -> bool:
        """Whether an unexpired code is outstanding for the channel."""
        entry = self._pending.get(channel)
        if entry is None:
            return False
        if self._now() >= entry.expires_at:
            del self._pending[channel]
            return False
        return True

    def try_claim(self, channel: str, text: str) -> bool:
        """Attempt to claim the channel's pending code with a message text.

        Success consumes the code. A wrong guess burns an attempt; exhausting
        attempts (or expiry) invalidates the code entirely.
        """
        entry = self._pending.get(channel)
        if entry is None:
            return False
        if self._now() >= entry.expires_at:
            del self._pending[channel]
            return False
        if secrets.compare_digest(text.strip().upper(), entry.code):
            del self._pending[channel]
            return True
        entry.attempts_left -= 1
        if entry.attempts_left <= 0:
            del self._pending[channel]
        return False

    def clear(self, channel: str) -> None:
        """Drop any pending code (channel deleted)."""
        self._pending.pop(channel, None)
