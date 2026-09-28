"""The background advancer: a run moves without being asked (spec
workflow "Run at most one node at a time").

Shaped like ``RetentionWorker`` and ``ConvergeWorker`` — a catch-up round
shortly after boot, then a tick on an interval, and a round that raises is
logged rather than allowed to end the loop. The reason is the same one those
two have: this worker is the only thing moving every run on the machine, so one
run's bad state must cost that run and nothing else.

Two rules it enforces itself rather than trusting upstream:

* **One node at a time per run** ("Run at most one node at a time").
  ``advance_run`` does not return until that run's node has finished its turn,
  and a run already being advanced is skipped on every later tick. The node
  service refuses a second running node too; a ceiling only one side honours is
  not a ceiling.
* **Runs do not block each other.** Each run advances as its own task keyed by
  run id, so a node that spends twenty minutes on a build does not hold up
  another run's first node.

What it deliberately does not do is decide anything. It does not read a run's
status, does not choose the next node, does not write an event: ``due_runs``
says which runs are worth looking at and ``advance_run`` does the whole of the
rest, so there is exactly one place where "what happens next" is decided and it
is not here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from coffer.application.workflow.compaction import ConversationCompactor
from coffer.application.workflow.context_composer import ContextComposer
from coffer.application.workflow.node_driver import NodeDriver
from coffer.application.workflow.ports import TurnPlatformPort
from coffer.domain.workflow.run import FailureReason

__all__ = [
    "DEFAULT_INTERVAL_S",
    "DEFAULT_START_DELAY_S",
    "AdvanceRun",
    "AdvanceWorker",
    "DueRuns",
    "NodeOutcomeSink",
    "driver_for",
]

_logger = logging.getLogger(__name__)

#: Long enough that start-up reconciliation — which is what decides an
#: interrupted node's fate (spec workflow "Report a node interrupted by a
#: restart as failed") — has finished before the first tick, so
#: the advancer never adopts a node the daemon is still making its mind up
#: about.
DEFAULT_START_DELAY_S = 5.0

#: The poll is one cheap query, and a nudge covers the case that matters (a
#: command the developer just issued), so this only has to be short enough that
#: a missed nudge is not noticed.
DEFAULT_INTERVAL_S = 5.0

#: A run whose advance raised waits ``interval * 2**(failures-1)`` before the
#: next try, never longer than this. Without a wait a run that fails the same
#: way every time is retried back to back — each failure used to wake the loop
#: at once — and an idle daemon wrote a traceback per attempt, ~2 MB a second.
DEFAULT_MAX_BACKOFF_S = 300.0

#: After this many failures in a row the advancer stops retrying the run on
#: its own. Something that fails five times with backoff in between is not
#: transient; retrying it forever only fills the log. A nudge (a developer
#: command) or a restart gives it a fresh budget.
DEFAULT_MAX_FAILURES = 5

#: The runs worth looking at this tick — this machine's runs in a status that
#: can still move. Answering with a run that turns out to have nothing due is
#: free; omitting one stalls it until something nudges.
DueRuns = Callable[[], Awaitable[Sequence[str]]]

#: Start one run's next node, if it has one, and return when that node's turn
#: has ended. Satisfied by the node service's "what should run next" pair —
#: ``next_position`` then ``act(..., NodeAction.START, ...)``.
AdvanceRun = Callable[[str], Awaitable[None]]


class NodeOutcomeSink(Protocol):
    """The three answers a driven node sends back to the node service.

    Declared here rather than in ``ports.py`` because it is not a seam out of
    this kind: both ends are the workflow engine, and the Protocol exists only
    so :func:`driver_for` can wire one object's methods into the driver without
    either module importing the other.
    """

    async def record_conversation(self, attempt_id: str, conversation_id: str) -> None: ...

    async def report_output(self, attempt_id: str, summary: str, tokens: int = 0) -> object: ...

    async def report_failure(
        self,
        attempt_id: str,
        reason: FailureReason = FailureReason.AGENT_ERROR,
        detail: str | None = None,
    ) -> object: ...


def driver_for(
    sink: NodeOutcomeSink,
    *,
    platform: TurnPlatformPort,
    composer: ContextComposer,
    compactor: ConversationCompactor,
) -> NodeDriver:
    """A driver whose outcomes land on ``sink``.

    One function so the composition root cannot wire two of the three callbacks
    to one service and the third to another — which is the failure mode that
    would leave an attempt open forever with nobody able to say why. The two
    wrappers exist because the service's reports answer with a command result
    the driver has no use for and must not be tempted to act on.
    """

    async def output_ready(attempt_id: str, summary: str, tokens: int) -> None:
        await sink.report_output(attempt_id, summary, tokens)

    async def failed(attempt_id: str, reason: FailureReason, detail: str) -> None:
        await sink.report_failure(attempt_id, reason, detail)

    return NodeDriver(
        platform=platform,
        composer=composer,
        compactor=compactor,
        on_conversation_opened=sink.record_conversation,
        on_output_ready=output_ready,
        on_failed=failed,
    )


class AdvanceWorker:
    """Polls for runs that can move and advances them, one node per run."""

    def __init__(
        self,
        *,
        due_runs: DueRuns,
        advance_run: AdvanceRun,
        start_delay_s: float = DEFAULT_START_DELAY_S,
        interval_s: float = DEFAULT_INTERVAL_S,
        max_backoff_s: float = DEFAULT_MAX_BACKOFF_S,
        max_failures: int = DEFAULT_MAX_FAILURES,
    ) -> None:
        self._due_runs = due_runs
        self._advance_run = advance_run
        self._start_delay = start_delay_s
        self._interval = interval_s
        self._max_backoff = max_backoff_s
        self._max_failures = max_failures
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._inflight: dict[str, asyncio.Task[None]] = {}
        #: run id → (failures in a row, loop time before which it is skipped).
        #: A run at ``max_failures`` is skipped until a nudge clears this.
        self._failures: dict[str, tuple[int, float]] = {}

    def start(self) -> None:
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._loop(), name="workflow-advance")

    def nudge(self) -> None:
        """Advance now instead of at the next tick.

        Called after a command that could have made a node due — starting a
        run, completing a node, deciding an approval. It is a hint: missing one
        costs a tick, never a node.

        It also gives every failing run a fresh retry budget: a developer acted,
        so whatever made the run fail may have changed.
        """
        self._failures.clear()
        self._wake.set()

    async def stop(self) -> None:
        """Stop the loop and the nodes it has in flight.

        A cancelled node is left ``running`` on purpose: the process is going
        away mid-turn, which is precisely the state start-up reconciliation
        reports as ``interrupted`` (spec workflow "Report a node interrupted
        by a restart as failed"). Writing a failure here would be the daemon
        guessing at what it is about to lose.
        """
        self._stop.set()
        self._wake.set()
        for task in (self._loop_task, *self._inflight.values()):
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._inflight.clear()
        self._loop_task = None

    async def _loop(self) -> None:
        await self._sleep(self._start_delay)
        while not self._stop.is_set():
            # Cleared before the round, not inside the wait: a nudge that
            # arrives while the round is running is for the *next* round, and
            # clearing afterwards would swallow it.
            self._wake.clear()
            await self._tick()
            await self._sleep(self._interval)

    async def _tick(self) -> None:
        """One round: ask which runs can move, start the ones that are idle."""
        try:
            run_ids = await self._due_runs()
        except asyncio.CancelledError:
            raise
        except Exception:  # the loop outlives any single round
            _logger.exception("workflow.advance.due_failed")
            return
        now = asyncio.get_running_loop().time()
        for run_id in run_ids:
            if run_id in self._inflight:
                # Spec workflow "Run at most one node at a time", enforced on
                # this side too: the run is already moving, and a second
                # advance would race its own node.
                continue
            failures, retry_at = self._failures.get(run_id, (0, 0.0))
            if failures >= self._max_failures or now < retry_at:
                continue
            self._inflight[run_id] = asyncio.create_task(
                self._advance(run_id), name=f"workflow-advance:{run_id}"
            )

    async def _advance(self, run_id: str) -> None:
        try:
            await self._advance_run(run_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One run raising must not touch another run, and must not take the
            # loop with it. The attempt stays as the service last wrote it; the
            # developer retries it. No wake: waking here is what turned a run
            # that fails every time into a tight retry loop.
            self._record_failure(run_id)
        else:
            self._failures.pop(run_id, None)
            # The node that just ended may have made the next one due; do not
            # make the run wait out an interval to find out.
            self._wake.set()
        finally:
            self._inflight.pop(run_id, None)

    def _record_failure(self, run_id: str) -> None:
        """Log the failure and hold the run back before its next try."""
        failures = self._failures.get(run_id, (0, 0.0))[0] + 1
        backoff = min(self._interval * 2 ** (failures - 1), self._max_backoff)
        self._failures[run_id] = (failures, asyncio.get_running_loop().time() + backoff)
        extra = {"run_id": run_id, "failures": failures}
        if failures == 1:
            _logger.exception("workflow.advance.run_failed", extra=extra)
        elif failures >= self._max_failures:
            # The traceback was logged on the first failure; repeating it
            # would say nothing new.
            _logger.error("workflow.advance.run_given_up", extra=extra)
        else:
            _logger.warning(
                "workflow.advance.run_failed_again", extra={**extra, "retry_in_s": backoff}
            )

    async def _sleep(self, seconds: float) -> None:
        """Wait out the interval, returning early on a stop or a nudge."""
        if self._stop.is_set():
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
