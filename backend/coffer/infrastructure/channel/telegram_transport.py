"""One authenticated Bot API call, with the error contract around it.

The Telegram counterpart to ``seatalk_transport.py``: the adapter keeps a thin
``_call`` so every call site reads the same, and the envelope handling lives
here so ``telegram.py`` stays inside the size cap.
"""

from __future__ import annotations

from typing import Any

import httpx

from coffer.domain.channel.errors import ChannelSendFailed


async def call(client: httpx.AsyncClient, base: str, name: str, method: str, **params: Any) -> Any:
    """POST ``method`` and unwrap the Bot API envelope.

    Every failure surfaces as ``ChannelSendFailed``. A response that parsed and
    said no is marked ``api_rejected``: it is a decision by the platform, not a
    transport fault, and a caller must not retry it the same way.
    """
    try:
        response = await client.post(f"{base}/{method}", json=params)
    except httpx.HTTPError as e:
        raise ChannelSendFailed(name, type(e).__name__) from e
    try:
        payload = response.json()
    except ValueError as e:
        # A gateway 502/503 returns an HTML page, not the Bot API JSON envelope
        # — json() raises (a JSONDecodeError is NOT an httpx.HTTPError), so
        # surface it as the channel error contract.
        raise ChannelSendFailed(
            name,
            f"{method}: non-JSON response ({response.status_code})",
            api_rejected=True,
            status=response.status_code,
        ) from e
    if not isinstance(payload, dict) or not payload.get("ok", False):
        description = ""
        if isinstance(payload, dict):
            description = str(payload.get("description", ""))
        raise ChannelSendFailed(
            name,
            f"{method}: {description or response.status_code}",
            api_rejected=True,
            status=response.status_code,
        )
    return payload.get("result")
