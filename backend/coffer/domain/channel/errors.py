"""Channel-kind domain errors (spec 009).

Kept in their own module because `domain/errors.py` is at its size budget;
HTTP status mapping lives in `surfaces/http/errors.py` like every other code.
"""

from __future__ import annotations

from coffer.domain.errors import CofferError


class ChannelNotPaired(CofferError):  # noqa: N818
    """The channel has no paired peer to deliver to."""

    code = "CHANNEL_NOT_PAIRED"

    def __init__(self, channel: str) -> None:
        super().__init__(f"channel {channel!r} has no paired peer")


class ChannelNotRunning(CofferError):  # noqa: N818
    """The channel's adapter is not running (disabled or starting)."""

    code = "CHANNEL_NOT_RUNNING"

    def __init__(self, channel: str) -> None:
        super().__init__(f"channel {channel!r} adapter is not running")


class ChannelSendFailed(CofferError):  # noqa: N818
    """The IM platform refused or failed the outbound send.

    ``api_rejected`` distinguishes an explicit platform rejection (an HTTP
    response that said no) from a transport failure (timeout, connection
    reset) where the request may in fact have been delivered — retry logic
    must not resend on the latter. ``status`` carries the HTTP status of a
    rejection when known.
    """

    code = "CHANNEL_SEND_FAILED"

    def __init__(
        self,
        channel: str,
        detail: str,
        *,
        api_rejected: bool = False,
        status: int | None = None,
    ) -> None:
        super().__init__(f"send via channel {channel!r} failed: {detail}")
        self.api_rejected = api_rejected
        self.status = status
