"""What the daemon remembers about upstreams that will not start.

A server that cannot be reached (a VPN that is down, a command that is gone, a
token the upstream rejects) fails the same way a minute later. Every client
session owns its own :class:`~coffer.application.mcp.supervisor.SubprocessSupervisor`,
so without one shared memory each session re-ran the whole retry ladder against
the same dead server: four sessions made 23 ``mcp.upstream.spawn_failed``
records in a minute and kept doing so forever.

The ledger is that shared memory, one per daemon:

- **exponential backoff with a cap**: after the first exhausted ladder the
  server is not tried again for ``base`` seconds, then twice that, up to
  ``cap``. Every session sees the same wait.
- **circuit breaker**: after ``FAILING_AFTER`` exhausted ladders in a row the
  server is *failing*. That is said once in the log, and the message every
  caller gets while backing off names it, so the server's status can show it.
- a success, an edit of the server or a delete forgets all of it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_logger = logging.getLogger(__name__)

#: Exhausted ladders in a row after which a server is reported as failing.
FAILING_AFTER = 3
DEFAULT_BACKOFF_BASE_SECONDS = 60.0
DEFAULT_BACKOFF_CAP_SECONDS = 1800.0


@dataclass
class UpstreamFailure:
    consecutive_failures: int = 0
    retry_at: datetime | None = None
    last_error: str | None = None
    failing: bool = False


class UpstreamFailureLedger:
    """Per-server failure streaks shared by every supervisor in the daemon."""

    def __init__(
        self,
        *,
        base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._base = base_seconds
        self._cap = cap_seconds
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._by_server: dict[str, UpstreamFailure] = {}

    def get(self, server: str) -> UpstreamFailure | None:
        return self._by_server.get(server)

    def now(self) -> datetime:
        return self._clock()

    def backing_off(self, server: str) -> UpstreamFailure | None:
        """The failure record while the server must not be tried yet, else None."""
        rec = self._by_server.get(server)
        if rec and rec.retry_at is not None and self._clock() < rec.retry_at:
            return rec
        return None

    def record_failure(self, server: str, error: str) -> UpstreamFailure:
        rec = self._by_server.setdefault(server, UpstreamFailure())
        rec.consecutive_failures += 1
        rec.last_error = error
        wait = min(self._base * 2 ** (rec.consecutive_failures - 1), self._cap)
        rec.retry_at = self._clock() + timedelta(seconds=wait)
        if rec.consecutive_failures >= FAILING_AFTER and not rec.failing:
            rec.failing = True
            _logger.warning(
                "mcp.upstream.failing",
                extra={"server": server, "failures": rec.consecutive_failures, "error": error},
            )
        return rec

    def record_success(self, server: str) -> None:
        rec = self._by_server.pop(server, None)
        if rec is not None and rec.failing:
            _logger.info("mcp.upstream.recovered", extra={"server": server})

    def forget(self, server: str) -> None:
        self._by_server.pop(server, None)
