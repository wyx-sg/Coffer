"""The requests a gateway session is still answering, so a client can cancel one.

Spec mcp-gateway "Cancel a request only when the client says so". A client
cancels with ``notifications/cancelled`` naming the request's id; the id is
looked up in its own session only, so two sessions that happen to use the same
id never cancel each other's work. Cancelling stops the gateway's handling and,
through the MCP SDK, sends the upstream one ``notifications/cancelled`` of its
own; nothing is ever resent.

A dropped HTTP connection is not a cancellation: the request runs on in its own
task (``asyncio.shield``) and its answer is simply not delivered.
"""

from __future__ import annotations

import asyncio
import json
import weakref
from collections.abc import Coroutine
from typing import Any

from coffer.application.runtime.supervisor import spawn
from coffer.domain.mcp.jsonrpc_errors import INVALID_REQUEST, JsonRpcError


class RequestCancelled(Exception):  # noqa: N818
    """The client cancelled this request; it gets no response."""


def _key(request_id: object) -> str:
    # JSON form, so the integer 1 and the string "1" stay two different ids.
    return json.dumps(request_id, sort_keys=True)


class InflightRequests:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        # Tasks stopped by ``cancel``, as opposed to the session ending.
        self._cancelled: weakref.WeakSet[asyncio.Task[Any]] = weakref.WeakSet()

    def __len__(self) -> int:
        return len(self._tasks)

    async def run(self, request_id: object, work: Coroutine[Any, Any, Any]) -> Any:
        """Run ``work`` under ``request_id`` and return its result.

        Raises ``RequestCancelled`` when :meth:`cancel` stopped it, and refuses
        an id that is still in flight in this session (JSON-RPC ids are unique
        among a session's outstanding requests).
        """
        key = _key(request_id)
        if key in self._tasks:
            work.close()
            raise JsonRpcError(INVALID_REQUEST, f"request id {request_id!r} is already in flight")
        task = spawn(work, name=f"mcp-request:{key}")
        self._tasks[key] = task
        task.add_done_callback(lambda _t: self._forget(key, task))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled() and task in self._cancelled:
                raise RequestCancelled from None
            raise

    def cancel(self, request_id: object) -> bool:
        """Cancel the in-flight request ``request_id``; False when there is none
        (already answered, or never seen), which a client may legitimately send."""
        key = _key(request_id)
        task = self._tasks.get(key)
        if task is None or task.done():
            return False
        self._cancelled.add(task)
        task.cancel()
        return True

    def cancel_all(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()

    def _forget(self, key: str, task: asyncio.Task[Any]) -> None:
        if self._tasks.get(key) is task:
            del self._tasks[key]
        if not task.cancelled():
            # Retrieved here so an answer nobody waited for (the client hung up)
            # is not reported as "exception was never retrieved".
            task.exception()


__all__ = ["InflightRequests", "RequestCancelled"]
