"""Check a bot's credentials without saving them (spec channels "Check
credentials before they are saved").

The Add channel form and the Replace token dialog call this as the person
pastes, so a wrong token is named under its field instead of surfacing later as
a channel that never connects. Nothing here stores, caches or logs a credential:
the only effect is one outbound call to the platform, bounded by a timeout.

The platform calls sit behind ``CredentialProbe`` (adapted in
``infrastructure/channel/credential_probe.py``), and the stored credentials of an
existing channel behind ``StoredCredentialReader``, so this module is the rule
and the two ports are the I/O.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

_logger = logging.getLogger(__name__)

#: Longest the platform may take. A person is watching a field, so a slow
#: platform is reported as such rather than waited out.
CHECK_TIMEOUT_SECONDS = 8.0

Reason = Literal["missing", "rejected", "unreachable", "timeout"]


class CredentialProbeError(Exception):
    """A platform refused the credentials, or could not be asked."""

    def __init__(self, reason: Reason, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason: Reason = reason
        self.detail = detail


@dataclass(frozen=True)
class ProbedBot:
    """Who the platform says the credentials belong to."""

    #: The platform's stable identity for the bot — what two probes are compared on.
    bot_id: str
    #: ``@handle`` without the at-sign; ``None`` where the platform has none.
    handle: str | None = None
    name: str | None = None


class CredentialProbe(Protocol):
    async def telegram(self, bot_token: str) -> ProbedBot: ...

    async def seatalk(self, app_id: str, app_secret: str) -> ProbedBot: ...


@dataclass(frozen=True)
class StoredCredentials:
    """What an existing channel holds, resolved from its secret store."""

    platform: str
    bot_token: str | None = None
    app_id: str | None = None


class StoredCredentialReader(Protocol):
    async def read(self, channel_uid: str) -> StoredCredentials | None:
        """The channel's stored credentials, or ``None`` when it does not exist
        or its secret cannot be read right now."""
        ...


@dataclass(frozen=True)
class CredentialCheckRequest:
    platform: str
    bot_token: str | None = None
    app_id: str | None = None
    app_secret: str | None = None
    #: An existing channel to compare the new credentials with.
    channel_uid: str | None = None


@dataclass(frozen=True)
class CredentialCheckResult:
    ok: bool
    bot_handle: str | None = None
    bot_name: str | None = None
    #: Whether the credentials are the stored channel's own bot; ``None`` when
    #: there was nothing to compare with.
    same_bot: bool | None = None
    reason: Reason | None = None
    #: The platform's own words about a rejection, when it gave any.
    detail: str | None = None


class CredentialCheck:
    def __init__(
        self,
        probe: CredentialProbe,
        stored: StoredCredentialReader,
        *,
        timeout: float = CHECK_TIMEOUT_SECONDS,
    ) -> None:
        self._probe = probe
        self._stored = stored
        self._timeout = timeout

    async def check(self, request: CredentialCheckRequest) -> CredentialCheckResult:
        stored = await self._stored_of(request)
        try:
            bot = await self._probe_new(request, stored)
        except CredentialProbeError as e:
            return CredentialCheckResult(ok=False, reason=e.reason, detail=e.detail or None)
        same_bot = await self._same_bot(request, stored, bot)
        return CredentialCheckResult(
            ok=True, bot_handle=bot.handle, bot_name=bot.name, same_bot=same_bot
        )

    async def _stored_of(self, request: CredentialCheckRequest) -> StoredCredentials | None:
        if not request.channel_uid:
            return None
        stored = await self._stored.read(request.channel_uid)
        return stored if stored is not None and stored.platform == request.platform else None

    async def _probe_new(
        self, request: CredentialCheckRequest, stored: StoredCredentials | None
    ) -> ProbedBot:
        try:
            async with asyncio.timeout(self._timeout):
                if request.platform == "telegram":
                    if not request.bot_token:
                        raise CredentialProbeError("missing")
                    return await self._probe.telegram(request.bot_token.strip())
                app_id = (request.app_id or (stored.app_id if stored else None) or "").strip()
                if not app_id or not request.app_secret:
                    raise CredentialProbeError("missing")
                return await self._probe.seatalk(app_id, request.app_secret.strip())
        except TimeoutError as e:
            raise CredentialProbeError("timeout") from e

    async def _same_bot(
        self, request: CredentialCheckRequest, stored: StoredCredentials | None, bot: ProbedBot
    ) -> bool | None:
        if stored is None:
            return None
        if request.platform == "seatalk":
            # A SeaTalk bot IS its app: the id the person typed (or the channel
            # keeps) names it, and the secret only proves they hold it.
            return bot.bot_id == stored.app_id if stored.app_id else None
        if not stored.bot_token:
            return None
        try:
            async with asyncio.timeout(self._timeout):
                before = await self._probe.telegram(stored.bot_token)
        except (CredentialProbeError, TimeoutError):
            # The old token may be exactly what was revoked; "unknown" is the
            # honest answer, and not a reason to withhold the new token's result.
            _logger.debug("channel.credential_check.stored_unreadable")
            return None
        return before.bot_id == bot.bot_id
