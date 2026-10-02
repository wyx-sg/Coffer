"""One authenticated Bot API call, with the error contract around it.

The Telegram counterpart to ``seatalk_transport.py``: the adapter keeps a thin
``_call`` so every call site reads the same, and the envelope handling lives
here so ``telegram.py`` stays inside the size cap.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from coffer.domain.channel.errors import ChannelSendFailed

_logger = logging.getLogger(__name__)

#: How many times a rate-limited call is retried, and the longest single wait the
#: platform's ``retry_after`` is honoured for (spec channels "Render replies by the
#: adapter's declared capabilities": a rate-limited send backs off and retries).
_RATE_RETRIES = 3
_MAX_RETRY_AFTER_SECONDS = 30.0


async def call(
    client: httpx.AsyncClient, base: str, name: str, method: str, /, **params: Any
) -> Any:
    """POST ``method`` and unwrap the Bot API envelope.

    The leading arguments are positional-only so a Bot API parameter may share a
    name with one of them (``createForumTopic`` takes a ``name``).

    Every failure surfaces as ``ChannelSendFailed``. A response that parsed and
    said no is marked ``api_rejected``: it is a decision by the platform, not a
    transport fault, and a caller must not retry it the same way.
    """
    attempt = 0
    while True:
        try:
            response = await client.post(f"{base}/{method}", json=params)
        except httpx.HTTPError as e:
            raise ChannelSendFailed(name, type(e).__name__) from e
        delay = _retry_after(response) if response.status_code == 429 else None
        if delay is None or attempt >= _RATE_RETRIES:
            break
        # The platform told us when to come back: wait that long, then resend. A
        # 429 means the request was refused, so resending cannot duplicate it.
        attempt += 1
        _logger.warning(
            "telegram.rate_limited", extra={"channel": name, "method": method, "delay": delay}
        )
        await asyncio.sleep(delay)
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


def _retry_after(response: httpx.Response) -> float | None:
    """The wait a 429 asks for (``parameters.retry_after``), bounded; ``None``
    when the response does not say, which is then an ordinary refusal."""
    try:
        payload = response.json()
    except ValueError:
        return None
    parameters = payload.get("parameters") if isinstance(payload, dict) else None
    value = parameters.get("retry_after") if isinstance(parameters, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return min(float(value), _MAX_RETRY_AFTER_SECONDS)
