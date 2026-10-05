"""A paired person's SeaTalk profile picture (spec channels "Show each paired
person's platform picture").

``GET /contacts/v2/profile`` answers an employee's profile, ``avatar`` (a
picture URL) among it. It needs the app's **Get Employee Profile** permission;
an app without it is refused, which reads as "no picture" and leaves the
list's initials in place. The picture itself is downloaded from that URL
without the app's token, which belongs to the Open API alone.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from coffer.domain.channel.errors import ChannelSendFailed

__all__ = ["PROFILE_PATH", "fetch_avatar"]

PROFILE_PATH = "/contacts/v2/profile"


async def fetch_avatar(
    get: Callable[..., Awaitable[Any]],
    client: httpx.AsyncClient,
    name: str,
    employee_code: str,
) -> bytes | None:
    """The person's picture, or ``None`` when their profile carries none.
    Raises ``ChannelSendFailed`` when SeaTalk refused or could not be reached."""
    payload = await get(PROFILE_PATH, {"employee_code": employee_code}, retries=1)
    employees = payload.get("employees") if isinstance(payload, dict) else None
    profile = next(
        (
            e
            for e in employees or []
            if isinstance(e, dict) and str(e.get("employee_code", "")) == employee_code
        ),
        None,
    )
    url = str(profile.get("avatar") or "") if profile is not None else ""
    if not url.startswith("https://"):
        return None
    try:
        response = await client.get(url)
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        raise ChannelSendFailed(name, f"avatar download: {type(e).__name__}") from e
    if not response.is_success:
        raise ChannelSendFailed(
            name, f"avatar download: {response.status_code}", status=response.status_code
        )
    return response.content
