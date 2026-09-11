"""The long-poll loop: ask for updates, hand each one to a dispatcher.

Split out of ``telegram.py`` to keep that file inside the size cap. The loop
owns two rules that are easy to get wrong and expensive when they are:

* the offset is committed only AFTER a dispatch attempt, so a crash re-delivers
  the update rather than swallowing it — and a single poison update cannot
  wedge the channel, because a dispatch that raises still advances past it;
* every failure backs off. An earlier version retried a non-list result with no
  delay, which span the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.telegram_updates import ALLOWED_UPDATES

__all__ = ["BACKOFF_LADDER", "poll_updates"]

_logger = logging.getLogger(__name__)

#: Retry delays for a failing poll, in seconds; the last one repeats.
BACKOFF_LADDER = (1.0, 5.0, 30.0)


async def poll_updates(
    call: Callable[..., Awaitable[Any]],
    dispatch: Callable[[dict[str, Any]], Awaitable[None]],
    *,
    channel: str,
    timeout: int,
) -> None:
    """Poll ``getUpdates`` forever, dispatching each update. Never returns."""
    offset: int | None = None
    failures = 0
    while True:
        try:
            params: dict[str, Any] = {
                "timeout": timeout,
                "allowed_updates": list(ALLOWED_UPDATES),
            }
            if offset is not None:
                params["offset"] = offset
            updates = await call("getUpdates", **params)
            if not isinstance(updates, list):
                raise ChannelSendFailed(channel, "getUpdates: non-list result")
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            delay = BACKOFF_LADDER[min(failures, len(BACKOFF_LADDER) - 1)]
            failures += 1
            _logger.warning("telegram.poll.retry", extra={"channel": channel, "delay": delay})
            await asyncio.sleep(delay)
            continue
        for update in updates:
            if not isinstance(update, dict) or "update_id" not in update:
                # Malformed element: skip without touching the offset — never
                # let one bad update kill the poll task.
                _logger.warning("telegram.poll.bad_update", extra={"channel": channel})
                continue
            try:
                await dispatch(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                _logger.exception("telegram.dispatch.failed", extra={"channel": channel})
            # Commit only after dispatch: a crash re-delivers; no poison-update wedge.
            offset = int(update["update_id"]) + 1
