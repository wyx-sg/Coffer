"""Background worker that keeps the transcript summary cache warm.

The Conversations listing is fast once the reader has parsed an agent's
transcripts and slow exactly once — the first time, on a cold cache. With the
cache now surviving a restart (``infrastructure/agent/transcript_cache``) that
first time is rare, but it still exists: a fresh install, a deleted sidecar, a
user who has been working all day since the last pass. This worker makes sure
the visit that pays for it is never the user's.

Shaped after ``retention_worker.py``: a catch-up pass on start, then one every
interval, with every exception logged and none of them fatal. The difference
that matters is that the reader is synchronous and blocking — seconds of it on
a cold tree — and the daemon serves the MCP gateway from the same loop, so the
pass runs on a thread.

It is a *cache* pass, not a management operation: it reads the agents' own
files and writes only the sidecar, so it emits no audit event (FR-048 — no
workspace listing does).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

_DEFAULT_INTERVAL_SECONDS = 3600.0
_logger = logging.getLogger(__name__)

#: ``(agent_type_value, config_dir)`` — all the reader needs to warm one agent.
AgentTarget = tuple[str, str]


class TranscriptWarmWorker:
    """Parses every registered agent's transcripts on a timer, off the loop."""

    def __init__(
        self,
        *,
        warm: Callable[[str, str], int],
        list_targets: Callable[[], Awaitable[list[AgentTarget]]],
        interval_seconds: float = _DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        # ``warm`` is the reader's own blocking pass, injected so this layer
        # keeps no infrastructure import.
        self._warm = warm
        self._list_targets = list_targets
        self._interval = interval_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._stop.set()

    async def run(self) -> None:
        """Run until stop() is called."""
        while not self._stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def run_once(self) -> None:
        """One catch-up pass over every agent that has transcripts.

        Each agent is warmed independently: one unreadable config dir must not
        cost the others their pass.
        """
        try:
            targets = await self._list_targets()
        except Exception:
            _logger.exception("transcript_warm.list_failed")
            return
        for agent_type_value, config_dir in targets:
            try:
                count = await asyncio.to_thread(self._warm, agent_type_value, config_dir)
            except Exception:
                _logger.exception("transcript_warm.failed", extra={"agent_type": agent_type_value})
                continue
            _logger.info(
                "transcript_warm.done",
                extra={"agent_type": agent_type_value, "sessions": count},
            )
