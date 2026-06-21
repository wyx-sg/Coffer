"""Auto-distill catch-up sweep + worker (Spec 007 FR-046).

A background sweep that scans each managed agent's transcript sessions and
distills any **settled, not-yet-distilled** session into the journal lane,
reusing the FR-045 distill path. Idempotent via a machine-local ledger.

All collaborators are injected as plain ``Callable`` ports so this
application-layer module imports nothing from infrastructure or surfaces
(import-linter compliant). The only cross-module import is
``NoModelConfiguredError`` from the sibling distill service — a peer
application module — used to detect the "no internal connection" no-op.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from coffer.application.distill.service import NoModelConfiguredError
from coffer.domain.distill.session import TranscriptSession

_logger = logging.getLogger(__name__)


class AutoDistillSweep:
    """One catch-up pass: find settled, recent, undistilled sessions and distill
    them into the journal lane, bounded by ``max_per_sweep``.

    ``run_once`` NEVER raises — a single session's (or agent's) failure is logged
    and suppressed so it can never abort the sweep or the daemon (mirrors FR-035).
    """

    def __init__(
        self,
        *,
        list_agent_names: Callable[[], Awaitable[list[str]]],
        list_sessions: Callable[[str], Awaitable[list[TranscriptSession]]],
        distill: Callable[[str, str], Awaitable[None]],
        is_distilled: Callable[[str, str, str], Awaitable[bool]],
        mark_distilled: Callable[[str, str, str], Awaitable[None]],
        session_sha: Callable[[str], str],
        now: Callable[[], datetime],
        settle_seconds: float,
        recency_seconds: float,
        max_per_sweep: int,
    ) -> None:
        self._list_agent_names = list_agent_names
        self._list_sessions = list_sessions
        self._distill = distill
        self._is_distilled = is_distilled
        self._mark_distilled = mark_distilled
        self._session_sha = session_sha
        self._now = now
        self._settle_seconds = settle_seconds
        self._recency_seconds = recency_seconds
        self._max_per_sweep = max_per_sweep

    async def run_once(self) -> None:
        """Run one catch-up pass. Never raises."""
        try:
            await self._sweep()
        except Exception:  # belt-and-suspenders: the pass is non-blocking.
            _logger.exception("auto_distill.sweep.failed")

    async def _sweep(self) -> None:
        try:
            agent_names = await self._list_agent_names()
        except Exception:
            _logger.exception("auto_distill.list_agents.failed")
            return

        # (agent_name, session_id, sha, last_activity_at) for every eligible session.
        eligible: list[tuple[str, str, str, datetime]] = []
        for name in agent_names:
            eligible.extend(await self._eligible_for_agent(name))

        if not eligible:
            return

        eligible.sort(key=lambda c: c[3])  # oldest-first by last_activity_at
        chosen = eligible[: self._max_per_sweep]
        deferred = len(eligible) - len(chosen)
        if deferred > 0:
            _logger.info(
                "auto_distill.deferred",
                extra={"deferred": deferred, "max_per_sweep": self._max_per_sweep},
            )

        for name, session_id, sha, _activity in chosen:
            if not await self._distill_one(name, session_id, sha):
                # NoModelConfiguredError → whole pass is a no-op; stop here.
                return

    async def _eligible_for_agent(self, name: str) -> list[tuple[str, str, str, datetime]]:
        """Return the eligible candidates for one agent. Skips the whole agent on
        a read error (e.g. unsupported agent type)."""
        try:
            sessions = await self._list_sessions(name)
        except Exception:
            _logger.debug("auto_distill.list_sessions.skip", extra={"agent": name})
            return []

        out: list[tuple[str, str, str, datetime]] = []
        now = self._now()
        for session in sessions:
            activity = session.last_activity_at
            if activity is None:
                continue
            age = (now - activity).total_seconds()
            if not (self._settle_seconds <= age <= self._recency_seconds):
                continue
            try:
                sha = self._session_sha(session.source_path)
            except Exception:
                _logger.debug(
                    "auto_distill.sha.skip",
                    extra={"agent": name, "session_id": session.session_id},
                )
                continue
            try:
                if await self._is_distilled(name, session.session_id, sha):
                    continue
            except Exception:
                _logger.debug(
                    "auto_distill.is_distilled.skip",
                    extra={"agent": name, "session_id": session.session_id},
                )
                continue
            out.append((name, session.session_id, sha, activity))
        return out

    async def _distill_one(self, name: str, session_id: str, sha: str) -> bool:
        """Distill one session + mark it. Returns ``False`` only when there is no
        internal model (caller should stop the pass); ``True`` otherwise."""
        try:
            await self._distill(name, session_id)
        except NoModelConfiguredError:
            _logger.info("auto_distill.no_model.noop")
            return False
        except Exception:
            # Per-session failure: log + leave UNMARKED so it retries next pass.
            _logger.warning(
                "auto_distill.distill.failed",
                extra={"agent": name, "session_id": session_id},
                exc_info=True,
            )
            return True
        try:
            await self._mark_distilled(name, session_id, sha)
        except Exception:
            _logger.warning(
                "auto_distill.mark.failed",
                extra={"agent": name, "session_id": session_id},
                exc_info=True,
            )
        return True


class AutoDistillSweepWorker:
    """Runs the sweep immediately on start (catch-up), then every
    ``interval_seconds``. A failing pass is logged but never kills the worker
    (the pass itself is already failure-suppressed)."""

    def __init__(
        self,
        *,
        sweep: Callable[[], Awaitable[None]],
        interval_seconds: float,
    ) -> None:
        self._sweep = sweep
        self._interval = interval_seconds
        self._stop = asyncio.Event()

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._stop.set()

    async def run(self) -> None:
        """Run until stop() is called."""
        while not self._stop.is_set():
            await self._run_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                continue

    async def _run_once(self) -> None:
        """Run one sweep. Never raises."""
        try:
            await self._sweep()
        except Exception:
            _logger.exception("auto_distill.worker.sweep.failed")
