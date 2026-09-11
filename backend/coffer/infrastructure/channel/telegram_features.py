"""Capabilities the deployed Bot API server may or may not have (FR-059).

Rich messages, streamed drafts and ephemeral messages arrived in Bot API 10.1
through 10.3. The server a user's bot token actually reaches is not guaranteed
to be that new, and nothing in the protocol announces a version — the only
honest way to find out is to try once and read the refusal.

So each of these is a :class:`Feature`: available until the platform itself
rejects it, then latched off **for the life of the process** and never tried
again. The caller falls back to the mechanism the feature replaced, which means
a Coffer running against an older server degrades in formatting and liveness,
never in delivery.

The latch is deliberately one-way and per-adapter. One-way because a server
that does not know a method will not learn it mid-session, and retrying per
message would put a failed round trip in front of every reply. Per-adapter
because two channels may point at different Bot API servers (a self-hosted
local one alongside api.telegram.org).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from coffer.domain.channel.errors import ChannelSendFailed

__all__ = ["Feature", "FeatureSet", "is_unsupported"]

_logger = logging.getLogger(__name__)

#: Substrings Telegram uses when a METHOD or PARAMETER is not known to it, as
#: opposed to when the request was merely wrong. Matched case-insensitively
#: against the `description` field of a 400/404 refusal.
_UNSUPPORTED_MARKERS = (
    "method not found",
    "method is not available",
    "unknown method",
    "unsupported",
    "unknown parameter",
    "unknown field",
)


def is_unsupported(error: BaseException) -> bool:
    """Whether ``error`` says the platform does not KNOW this call.

    The distinction matters more than it looks. A 400 saying "can't parse
    entities" means this one message was malformed — retry it differently, keep
    the feature. A 404 "method not found" means the server has never heard of
    the method — every future call will fail the same way, so latch it off.
    Treating the first as the second would disable rich messages for the whole
    process over one bad table; treating the second as the first would put a
    doomed round trip in front of every single reply.
    """
    if not isinstance(error, ChannelSendFailed):
        return False
    if not error.api_rejected:
        return False  # a transport error says nothing about what the server supports
    if error.status == 404:
        return True
    text = str(error).casefold()
    return any(marker in text for marker in _UNSUPPORTED_MARKERS)


@dataclass
class Feature:
    """One platform capability, available until the platform refuses it."""

    name: str
    _available: bool = True

    @property
    def available(self) -> bool:
        return self._available

    def note_failure(self, channel: str, error: BaseException) -> bool:
        """Record an attempt that failed; return whether the feature is now off.

        Only an "I do not know this" refusal latches. Anything else — a bad
        message, a rate limit, a network blip — leaves the feature on, because
        it says nothing about what the server can do.
        """
        if not is_unsupported(error):
            return False
        self._available = False
        _logger.info(
            "telegram.feature.unavailable",
            extra={"channel": channel, "feature": self.name, "reason": str(error)},
        )
        return True


@dataclass
class FeatureSet:
    """The Bot API 10.x capabilities one adapter probes for itself."""

    #: sendRichMessage / editMessageText(rich_message) — Bot API 10.1 (FR-061).
    rich_messages: Feature = field(default_factory=lambda: Feature("rich_messages"))
    #: sendMessageDraft — Bot API 10.1, can_stop in 10.3 (FR-062/FR-063).
    message_drafts: Feature = field(default_factory=lambda: Feature("message_drafts"))
    #: ephemeral_message_parameters on sendMessage — Bot API 10.2/10.3 (FR-064).
    ephemeral_messages: Feature = field(default_factory=lambda: Feature("ephemeral_messages"))
