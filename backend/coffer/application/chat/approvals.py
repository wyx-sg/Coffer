"""ApprovalChannel — the concrete inbound channel for human tool-approval.

Implements the ``ApprovalGate`` port. A running turn calls ``wait(request_id)``
and suspends; the HTTP ``POST .../approvals`` route calls ``resolve`` to deliver
the user's decision. Pure asyncio — no external SDK, no I/O — so it stays in the
application layer alongside the turn orchestrator.

A fresh ``ApprovalChannel`` is created per turn and discarded with it, so a
request id only needs to be unique within a turn.
"""

from __future__ import annotations

import asyncio

from coffer.application.chat.ports import ApprovalDecision
from coffer.domain.errors import ApprovalNotFound


class ApprovalChannel:
    """One turn's approval channel: a registry of pending decision futures."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[ApprovalDecision]] = {}

    def register(self, request_id: str) -> None:
        """Pre-register a pending request so a decision can be accepted even if
        it arrives before the adapter reaches ``wait()``.

        The orchestrator calls this as it forwards an ``ApprovalRequest`` event,
        closing the window where a fast client's decision would otherwise be
        rejected with a spurious ``ApprovalNotFound``.

        Trade-off: if the adapter violates the ``ApprovalGate`` contract and
        never ``wait()``s the request, a decision for it is accepted (204) but
        discarded — the future lives only until the turn ends, when the channel
        is dropped with its ``_ActiveTurn``, so the leak is turn-bounded.
        """
        if request_id not in self._pending:
            loop = asyncio.get_running_loop()
            self._pending[request_id] = loop.create_future()

    async def wait(self, request_id: str) -> ApprovalDecision:
        """Suspend until a decision for ``request_id`` is delivered.

        Raises ``asyncio.CancelledError`` if the turn is interrupted while
        waiting (the awaiting task is cancelled by the orchestrator). A decision
        that already arrived (via ``register`` + ``resolve``) is returned at once.
        """
        loop = asyncio.get_running_loop()
        future = self._pending.get(request_id)
        if future is None:
            future = loop.create_future()
            self._pending[request_id] = future
        try:
            return await future
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, request_id: str, decision: ApprovalDecision) -> None:
        """Deliver a decision to a turn waiting on ``wait(request_id)``.

        Raises ``ApprovalNotFound`` when no turn is currently waiting on
        ``request_id`` — an unknown id, or one already decided.
        """
        future = self._pending.get(request_id)
        if future is None or future.done():
            raise ApprovalNotFound(request_id)
        future.set_result(decision)
