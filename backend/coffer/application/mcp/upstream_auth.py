"""Notice a rejected key from the agents' real calls.

A server's key is revoked while no one is pressing Test; the first anyone hears
of it is an agent's call coming back refused. When a forwarded call is rejected
at the transport (the upstream HTTP endpoint answered 401 or 403, surfaced as
:class:`~coffer.domain.errors.UpstreamAuthRejected`), the server's health row is
written ``failing`` with reason ``auth_rejected`` — the row the Overview's
``mcp_key_rejected`` item reads. A later call that reaches the upstream and is
answered clears it.

Only an auth rejection is recorded here. A tool result carrying ``isError`` is a
business error over a healthy connection and never marks a server failing
(spec mcp-gateway "Notice a rejected key from real calls"); unreachable and the
other runtime failures keep reading from the last Test.

The hot path stays cheap: the monitor remembers which servers it has found free of
a recorded rejection, so a successful call to a healthy
server touches the database at most once per daemon run.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol


class UpstreamHealthPort(Protocol):
    """The persisted per-server health row, as far as this monitor writes it."""

    async def get(self, resource_uid: str) -> tuple[str, datetime] | None: ...

    async def get_reason(self, resource_uid: str) -> str | None: ...

    async def upsert(
        self,
        resource_uid: str,
        status: Literal["healthy", "failing"],
        checked_at: datetime,
        failure_reason: Literal["auth_rejected"] | None = None,
    ) -> None: ...


class UpstreamAuthMonitor:
    """Writes and clears ``auth_rejected`` health from forwarded calls."""

    def __init__(
        self,
        health: UpstreamHealthPort,
        *,
        clock: Callable[[], datetime] | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._health = health
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        #: Called after a write, so the attention list is recomputed at once.
        self.on_change = on_change
        self._clean: set[str] = set()

    async def rejected(self, server_uid: str) -> None:
        """A forwarded call was refused for its key."""
        self._clean.discard(server_uid)
        await self._health.upsert(server_uid, "failing", self._clock(), "auth_rejected")
        self._changed()

    async def answered(self, server_uid: str) -> None:
        """A forwarded call reached the upstream and was answered."""
        if server_uid in self._clean:
            return
        if await self._recorded_rejected(server_uid):
            await self._health.upsert(server_uid, "healthy", self._clock())
            self._changed()
        self._clean.add(server_uid)

    async def _recorded_rejected(self, server_uid: str) -> bool:
        row = await self._health.get(server_uid)
        if row is None or row[0] != "failing":
            return False
        return await self._health.get_reason(server_uid) == "auth_rejected"

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()


__all__ = ["UpstreamAuthMonitor", "UpstreamHealthPort"]
