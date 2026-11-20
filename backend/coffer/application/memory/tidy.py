"""Tidying memory as one change (spec memory "Tidy memory as one change").

**Tidy** on the Memory page hands :func:`tidy_prompt` to the person's agent.
The agent runs ``coffer memory tidy-start`` before it edits anything and
``coffer memory tidy-finish`` with its report when it is done. In between, the
hub is paused in the vault writer: the agent's edits stay in the working tree,
and finishing commits them all as one commit whose summary is the report. The
Memory page's History shows it as one version, and restoring the version
before it undoes the whole tidy.

An agent that never finishes must not pause the hub for ever: a tidy whose hub
has not changed for :data:`IDLE_S` is closed, committing what it did.
The rules a tidy follows are Coffer's, in the coffer-guide skill: the person
does not edit them (ADR keep-memory-in-one-place-agents-write-themselves).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from coffer.application.memory.service import ProjectSummary
from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.vault.writers import WRITER_AGENT, CommitMeta
from coffer.infrastructure.memory.hub_store import HubStore

logger = logging.getLogger(__name__)

#: How long the hub may sit unchanged before an open tidy is closed.
IDLE_S = 30 * 60
#: The longest report kept; a commit summary is one line.
MAX_REPORT = 4000
OP_TIDY = "tidy"

_STEPS = (
    'Read the "Memory" section of the coffer-guide skill first: it is the format '
    "every memory file follows and the rules a tidy applies.",
    "Run `coffer memory tidy-start` before you change anything.",
    "Go through the projects one at a time. Merge topics that belong together and "
    "split one that mixes subjects; drop a memory that is duplicated, stale or "
    "contradicted by a newer one; move what is about an outside system rather than "
    "the developer or the project into knowledge; fix every file that breaks the "
    "format.",
    "Leave alone what you are not sure about and list it in your report.",
    'Run `coffer memory tidy-finish --set summary="<your report>"`. The report says '
    "what you changed and what you left for the developer to decide.",
)


def tidy_prompt(folder: str, projects: Sequence[ProjectSummary]) -> str:
    """The prompt that hands a tidy of every project's memory to an agent."""
    facts = [f"Memory folder: {folder}"]
    facts += [
        f"{p.folder}: {p.topics} file{'s' if p.topics != 1 else ''}"
        + (f", {p.problems} breaking the format" if p.problems else "")
        for p in projects
    ]
    if not projects:
        facts.append("No memories yet.")
    return render_handoff(
        Handoff(
            task=(
                "Tidy the developer's memory in Coffer by the rules in the coffer-guide "
                'skill\'s "Memory" section.'
            ),
            facts=tuple(facts),
            steps=_STEPS,
        )
    )


@dataclass(frozen=True)
class TidyStatus:
    running: bool
    #: When the open tidy started (seconds since the epoch).
    started_at: float | None = None


@dataclass
class _Run:
    started_at: float
    last_activity: float
    fingerprint: tuple[tuple[str, str | None], ...] = ()


class MemoryTidy:
    """The one tidy of the hub that can be open at a time."""

    def __init__(
        self,
        hub: HubStore,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._hub = hub
        self._clock = clock
        self._wall = wall
        self._run: _Run | None = None
        hub.pause(lambda: self._run is not None)

    def status(self) -> TidyStatus:
        run = self._run
        return TidyStatus(running=run is not None, started_at=run.started_at if run else None)

    async def start(self) -> TidyStatus:
        """Open a tidy; what changed before is committed first as the ``disk``
        edit it is, so the tidy's commit holds only the agent's work."""
        if self._run is None:
            await asyncio.to_thread(self._hub.settle)
            run = _Run(started_at=self._wall(), last_activity=self._clock())
            self._run = run
            run.fingerprint = await asyncio.to_thread(self._hub.pending)
        return self.status()

    async def finish(self, report: str, *, actor: str, agent: str | None = None) -> str | None:
        """Close the tidy and commit what it changed as one commit carrying
        ``report``; the commit, or ``None`` when it changed nothing."""
        return await self._close(report, actor=actor, agent=agent)

    async def _close(self, report: str, *, actor: str, agent: str | None = None) -> str | None:
        self._run = None
        meta = CommitMeta(
            WRITER_AGENT, OP_TIDY, _summary(report), actor=actor, agent=agent or "agent"
        )
        return await asyncio.to_thread(self._hub.settle_as, meta)

    async def expire(self) -> bool:
        """Close a tidy whose hub sat unchanged for :data:`IDLE_S`."""
        run = self._run
        if run is None:
            return False
        fingerprint = await asyncio.to_thread(self._hub.pending)
        now = self._clock()
        if fingerprint != run.fingerprint:
            run.fingerprint = fingerprint
            run.last_activity = now
            return False
        if now - run.last_activity < IDLE_S:
            return False
        try:
            await self._close("", actor="daemon")
        except Exception:
            logger.warning("memory.tidy.expire_failed", exc_info=True)
        return True


def _summary(report: str) -> str:
    text = " ".join(report.split())
    if not text:
        return "Tidied memory"
    return text if len(text) <= MAX_REPORT else text[: MAX_REPORT - 1] + "…"


__all__ = ["IDLE_S", "MAX_REPORT", "OP_TIDY", "MemoryTidy", "TidyStatus", "tidy_prompt"]
