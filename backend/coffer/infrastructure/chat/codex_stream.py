"""Small helpers of the Codex adapter: attachment notes and the notification drain."""

from __future__ import annotations

import asyncio
import contextlib
import pathlib
from collections.abc import AsyncIterator
from typing import Any

from coffer.domain.chat.attachment import Attachment
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient


def attachment_note(att: Attachment) -> str:
    """The prompt line naming one attachment; a pruned file degrades to a note that
    it could not be read (spec channels "Hand inbound attachments to the turn as
    references"), as the Claude adapter does."""
    if not pathlib.Path(att.path).is_file():
        return f"[Attached file '{att.filename}' could not be read]"
    return f"[The user attached a file '{att.filename}', saved at {att.path}.]"


async def notifications_until_eof(
    rpc: CodexRpcClient,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Yield notifications until the RPC read loop reaches EOF.

    Race each fetch against the public ``rpc.eof`` signal; when the read loop
    has finished AND no buffered notification remains, end cleanly so ``_stream``
    can synthesize a terminal.  The ``finally`` block always cancels in-flight
    futures to prevent "Task was destroyed but it is pending!" warnings when the
    pump task is cancelled mid-wait.
    """
    stream = rpc.notifications()
    eof_waiter: asyncio.Future[Any] = asyncio.ensure_future(rpc.eof.wait())
    nxt: asyncio.Future[Any] | None = None
    try:
        while True:
            nxt = asyncio.ensure_future(stream.__anext__())
            await asyncio.wait({nxt, eof_waiter}, return_when=asyncio.FIRST_COMPLETED)
            if nxt.done():
                yield nxt.result()
                nxt = None
                continue
            # EOF fired first — give any notification produced in the same tick
            # a chance to land, then stop if none did.
            await asyncio.sleep(0)
            if nxt.done():
                yield nxt.result()
                nxt = None
                continue
            return  # EOF and no buffered notification
    finally:
        if not eof_waiter.done():
            eof_waiter.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await eof_waiter
        if nxt is not None and not nxt.done():
            nxt.cancel()
            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                await nxt
