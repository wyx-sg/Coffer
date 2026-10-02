"""Pairing codes — the person-binding security boundary.

Codes are memory-only by design: a daemon restart drops them and the user
re-issues. 8 characters from an unambiguous alphabet, single use, 1-hour TTL,
bounded wrong guesses (exhaustion invalidates the code). Fail closed.

"Pair by a one-tap start link" adds a second way to present the same code — a start link
carrying it — which arrives as ``/start <CODE>``. It is normalised here rather than at
the transport so BOTH ways in are governed by one gate: same single use, same TTL, same
attempt budget.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from coffer.application.audit_service import AuditService
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ChannelPeer, ChannelPeerRepoPort
from coffer.domain.audit import AuditEventType

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
    #: The ``sender_id`` of the person this pairing replaces, or ``None`` when it
    #: adds a person beside the ones already paired.
    replaces: str | None = None


class PairingManager:
    """Issue and claim pairing codes, one pending code per channel.

    Keyed by the channel's uid, so a rename between issuing and claiming does not
    lose the code (ADR identity-is-the-uid-inside-the-file)."""

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
        self._pending: dict[str, _Pending] = {}  # channel uid -> code

    def issue(self, channel: str, *, replaces: str | None = None) -> tuple[str, datetime]:
        """Generate a fresh code for the channel, replacing any pending one.

        ``replaces`` names the paired person whose identity the claimant takes
        over; without it the claimant is added beside everyone already paired."""
        code = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
        expires_at = self._now() + timedelta(seconds=self._ttl)
        self._pending[channel] = _Pending(
            code=code,
            expires_at=expires_at,
            attempts_left=self._max_attempts,
            replaces=replaces,
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

    def replaces(self, channel: str) -> str | None:
        """The person the channel's pending code replaces (``None``: adds one)."""
        entry = self._pending.get(channel)
        return entry.replaces if entry is not None else None

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
    """The code a message presents, however it was presented (see
    "Pair by a one-tap start link"): typed on
    its own, or carried by a start link as ``/start <CODE>``."""
    match = _START_PAYLOAD.match(text.strip())
    return (match.group(1) if match else text.strip()).upper()


def start_link(bot_username: str, code: str) -> str:
    """The one-tap pairing link for a Telegram bot (see "Pair by a one-tap start link").
    Empty when the bot's username is unknown — the typed code is then the only way
    in."""
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

    The claimant becomes one more paired person; when the code was issued to
    replace someone, that person's rows are un-paired in the same write.

    ``None`` means nothing was claimed — either the message was empty (non-text
    content must never burn a pairing attempt: a stranger's sticker cannot
    invalidate the code) or the code did not match.

    Lives beside the manager rather than on the inbound processor so the
    security boundary — what claims a code, and what a claim writes — reads in
    one place.
    """
    if not text.strip():
        return None
    if not sender_id:
        # A pairing binds a person, and the owner gate compares sender ids: a
        # claim from a message whose sender the transport could not name would
        # bind nobody. Refused before the code is touched, so it burns nothing.
        return None
    replaces = pairing.replaces(binding.resource.uid)
    if not pairing.try_claim(binding.resource.uid, text):
        _logger.debug("channel.inbound.ignored", extra={"channel": binding.resource.name})
        return None
    peer = ChannelPeer(
        resource_uid=binding.resource.uid,
        chat_id=chat_id,
        display_name=sender_display,
        paired_at=datetime.now(tz=UTC),
        sender_id=sender_id,
    )
    await peers.upsert_replacing(
        peer, await _replaced_chats(peers, binding.resource.uid, chat_id, sender_id, replaces)
    )
    await audit.record(
        AuditEventType.CHANNEL_PAIRED.value,
        # The row the binding was built from, so the pairing is filed under the
        # channel's identity and stays in its history across a rename — the
        # audit service takes the resource rather than a name to look up
        # precisely so a caller that already holds the row cannot mis-file it.
        resource=binding.resource,
        actor="channel",
        details={"chat_id": chat_id, "sender_id": sender_id, "display_name": sender_display},
    )
    return peer


async def _replaced_chats(
    peers: ChannelPeerRepoPort,
    resource_uid: str,
    chat_id: str,
    sender_id: str,
    replaces: str | None,
) -> list[str]:
    """The chats to un-pair with this claim: every row of the person it replaces
    (their DM and each group that inherited their ``sender_id``), none when the
    code only adds a person.

    spec channels "Serve several paired people": a code issued without a target
    leaves everyone already paired in place; one issued to re-pair a person
    removes that person's authority — left in place, their DM would still pass
    the gate. The same sender claiming again keeps its rows (a rebind, not a
    change of person).

    The caller writes the un-pairs and the new row as one ``upsert_replacing``,
    so a failure cannot leave the replaced person gone and the new one unsaved.
    """
    if replaces is None or replaces == sender_id:
        return []
    return [
        existing.chat_id
        for existing in await peers.list_by_resource(resource_uid)
        if existing.sender_id == replaces and existing.chat_id != chat_id
    ]
