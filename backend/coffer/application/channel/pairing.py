"""Pairing codes — the owner-binding security boundary.

Codes are memory-only by design: a daemon restart drops them and the user
re-issues. 8 characters from an unambiguous alphabet, single use, 1-hour TTL,
bounded wrong guesses (exhaustion invalidates the code). Fail closed.

FR-066 adds a second way to present the same code — a start link carrying it —
which arrives as ``/start <CODE>``. It is normalised here rather than at the
transport so BOTH ways in are governed by one gate: same single use, same TTL,
same attempt budget.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from coffer.application.audit_service import AuditService
from coffer.application.channel.ports import ChannelBinding, ChannelPeer, ChannelPeerRepoPort
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
#: ``/start CODE`` as a deep link delivers it — optionally addressed to the bot
#: by username in a group (``/start@mybot CODE``).
_START_PAYLOAD = re.compile(r"^/start(?:@\S+)?\s+(\S+)\s*$", re.IGNORECASE)
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
        if secrets.compare_digest(_presented_code(text), entry.code):
            del self._pending[channel]
            return True
        entry.attempts_left -= 1
        if entry.attempts_left <= 0:
            del self._pending[channel]
        return False

    def clear(self, channel: str) -> None:
        """Drop any pending code (channel deleted)."""
        self._pending.pop(channel, None)


def _presented_code(text: str) -> str:
    """The code a message presents, however it was presented (FR-066): typed on
    its own, or carried by a start link as ``/start <CODE>``."""
    match = _START_PAYLOAD.match(text.strip())
    return (match.group(1) if match else text.strip()).upper()


def start_link(bot_username: str, code: str) -> str:
    """The one-tap pairing link for a Telegram bot (FR-066). Empty when the
    bot's username is unknown — the typed code is then the only way in."""
    return f"https://t.me/{bot_username}?start={code}" if bot_username else ""


async def claim_pairing(
    binding: ChannelBinding,
    *,
    text: str,
    chat_id: str,
    sender_display: str,
    sender_id: str,
    pairing: PairingManager,
    peers: ChannelPeerRepoPort,
    audit: AuditService,
) -> ChannelPeer | None:
    """Claim the channel's pending code with ``text``; return the bound peer.

    ``None`` means nothing was claimed — either the message was empty (non-text
    content must never burn a pairing attempt: a stranger's sticker cannot
    invalidate the owner's code) or the code did not match.

    Lives beside the manager rather than on the inbound processor so the
    security boundary — what claims a code, and what a claim writes — reads in
    one place.
    """
    if not text.strip():
        return None
    if not pairing.try_claim(binding.name, text):
        _logger.debug("channel.inbound.ignored", extra={"channel": binding.name})
        return None
    peer = ChannelPeer(
        resource_id=binding.resource_id,
        chat_id=chat_id,
        display_name=sender_display,
        paired_at=datetime.now(tz=UTC),
        active_conversation_id=None,
        sender_id=sender_id or None,
    )
    await peers.upsert(peer)
    await audit.record(
        AuditEventType.CHANNEL_PAIRED.value,
        ref=ResourceRef(kind="channel", name=binding.name),
        actor="channel",
        details={"chat_id": chat_id, "display_name": sender_display},
    )
    return peer
