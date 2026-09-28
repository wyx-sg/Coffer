"""The background advancer: one node per run, and no run takes the loop down."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable, Sequence
from typing import ClassVar

import pytest

from coffer.application.workflow.advance_worker import AdvanceWorker, driver_for
from coffer.application.workflow.context_composer import NodeContextRequest
from coffer.application.workflow.dispatch import NodeDispatch
from coffer.application.workflow.node_driver import MANUAL_NODE_SUMMARY
from coffer.domain.workflow.run import FailureReason
from coffer.domain.workflow.template import Node, NodeType


class FakeService:
    """Stands in for the node service's advancer pair."""

    def __init__(
        self,
        *,
        block: set[str] | None = None,
        raise_for: dict[str, Exception] | None = None,
    ) -> None:
        self.started: list[str] = []
        self.finished: list[str] = []
        self.block = block or set()
        self.raise_for = raise_for or {}
        self.release = asyncio.Event()

    async def advance(self, run_id: str) -> None:
        self.started.append(run_id)
        if run_id in self.raise_for:
            raise self.raise_for[run_id]
        if run_id in self.block:
            await self.release.wait()
        self.finished.append(run_id)


def make_worker(service: FakeService, due: Callable[[], object], **kwargs: float) -> AdvanceWorker:
    return AdvanceWorker(
        due_runs=due,  # type: ignore[arg-type]
        advance_run=service.advance,
        start_delay_s=kwargs.get("start_delay_s", 0.0),
        interval_s=kwargs.get("interval_s", 0.01),
    )


async def until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async def wait() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(wait(), timeout=timeout)


@pytest.mark.acceptance(
    spec="workflow", scenario="a run advances from one node to the next without prompting"
)
async def test_a_due_run_advances_without_anyone_asking() -> None:
    service = FakeService()
    queued = [["run-a"], []]

    async def due() -> Sequence[str]:
        return queued.pop(0) if queued else []

    worker = make_worker(service, due)
    worker.start()
    try:
        await until(lambda: service.finished == ["run-a"])
    finally:
        await worker.stop()


async def test_a_run_advances_one_node_at_a_time_however_often_it_is_offered() -> None:
    service = FakeService(block={"run-a"})

    async def due() -> Sequence[str]:
        return ["run-a"]

    worker = make_worker(service, due)
    worker.start()
    try:
        await until(lambda: service.started == ["run-a"])
        await asyncio.sleep(0.08)  # several ticks' worth of further offers
        assert service.started == ["run-a"]
        service.release.set()
        await until(lambda: service.finished != [])
    finally:
        await worker.stop()


async def test_one_runs_failure_does_not_stop_another_run() -> None:
    service = FakeService(raise_for={"run-a": RuntimeError("run A is broken")})

    async def due() -> Sequence[str]:
        return ["run-a", "run-b"]

    worker = make_worker(service, due)
    worker.start()
    try:
        await until(lambda: "run-b" in service.finished)
        assert "run-a" in service.started
    finally:
        await worker.stop()


async def test_a_round_that_cannot_even_ask_is_logged_and_the_loop_survives() -> None:
    service = FakeService()
    calls = {"n": 0}

    async def due() -> Sequence[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the database went away")
        return ["run-a"] if calls["n"] == 2 else []

    worker = make_worker(service, due)
    worker.start()
    try:
        await until(lambda: service.finished == ["run-a"])
    finally:
        await worker.stop()


async def test_nudge_advances_now_instead_of_at_the_next_tick() -> None:
    service = FakeService()
    ready: list[str] = []

    async def due() -> Sequence[str]:
        taken = list(ready)
        ready.clear()
        return taken

    # An interval long enough that only a nudge could produce a second round.
    worker = make_worker(service, due, interval_s=30.0)
    worker.start()
    try:
        await asyncio.sleep(0.02)
        ready.append("run-a")
        worker.nudge()
        await until(lambda: service.finished == ["run-a"])
    finally:
        await worker.stop()


async def test_stopping_cancels_the_node_in_flight_rather_than_failing_it() -> None:
    service = FakeService(block={"run-a"})

    async def due() -> Sequence[str]:
        return ["run-a"]

    worker = make_worker(service, due)
    worker.start()
    await until(lambda: service.started == ["run-a"])

    await asyncio.wait_for(worker.stop(), timeout=2.0)

    # The attempt was never finished and was never reported as failed: the
    # daemon is going away mid-turn, which start-up reconciliation reports as
    # interrupted (spec workflow "Report a node interrupted by a restart as
    # failed").
    assert service.finished == []


async def test_stopping_twice_is_harmless() -> None:
    service = FakeService()

    async def due() -> Sequence[str]:
        return []

    worker = make_worker(service, due)
    worker.start()
    await worker.stop()
    await worker.stop()


async def test_driver_for_wires_all_three_reports_to_one_service() -> None:
    class Sink:
        """The node service's driver-facing trio, recorded."""

        def __init__(self) -> None:
            self.conversations: list[tuple[str, str]] = []
            self.outputs: list[tuple[str, str, int]] = []
            self.failures: list[tuple[str, FailureReason, str | None]] = []

        async def record_conversation(self, attempt_id: str, conversation_id: str) -> None:
            self.conversations.append((attempt_id, conversation_id))

        async def report_output(self, attempt_id: str, summary: str, tokens: int = 0) -> str:
            self.outputs.append((attempt_id, summary, tokens))
            return "a command result the driver must ignore"

        async def report_failure(
            self,
            attempt_id: str,
            reason: FailureReason = FailureReason.AGENT_ERROR,
            detail: str | None = None,
        ) -> str:
            self.failures.append((attempt_id, reason, detail))
            return "a command result the driver must ignore"

    class UnusedPlatform:
        async def create_conversation(
            self, *, agent_key: str, cwd: str, run_context: str | None = None
        ) -> str:
            raise AssertionError("a manual node opens no conversation")

        async def start_turn(self, conversation_id: str, text: str) -> asyncio.Queue[object]:
            raise AssertionError("a manual node starts no turn")

        async def transcript(self, conversation_id: str) -> list[object]:
            return []

        async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None: ...

        def interrupt(self, conversation_id: str) -> None: ...

    class UnusedCompactor:
        async def compact(self, conversation_id: str) -> object:
            raise AssertionError("a manual node has no conversation to compact")

    class UnusedComposer:
        async def compose(self, request: NodeContextRequest) -> str:
            raise AssertionError("a manual node composes no context")

    class FakeRun:
        id = "run-a"
        title = "run a"
        inputs: ClassVar[list[dict[str, object]]] = []

    class FakeAttempt:
        id = "att-9"
        run_id = "run-a"
        attempt = 1
        status = "running"
        conversation_id: str | None = None

    sink = Sink()
    driver = driver_for(
        sink,
        platform=UnusedPlatform(),  # type: ignore[arg-type]
        composer=UnusedComposer(),  # type: ignore[arg-type]
        compactor=UnusedCompactor(),  # type: ignore[arg-type]
    )

    await driver(
        NodeDispatch(
            run=FakeRun(),  # type: ignore[arg-type]
            stage_key="sign_off",
            node=Node(key="sign_off", name="Sign off", type=NodeType.MANUAL),
            attempt=FakeAttempt(),  # type: ignore[arg-type]
            agent_key="claude_code",
            workdir="/repo",
        )
    )

    assert sink.outputs == [("att-9", MANUAL_NODE_SUMMARY, 0)]
    assert sink.failures == []


async def test_a_run_that_keeps_failing_is_not_retried_in_a_tight_loop() -> None:
    # A failed advance used to wake the loop at once, so a run whose advance
    # raised the same way every time was retried back to back with a full
    # traceback per attempt — an idle daemon wrote ~2 MB of log a second.
    service = FakeService(raise_for={"run-a": RuntimeError("run A is broken")})

    async def due() -> Sequence[str]:
        return ["run-a"]

    worker = make_worker(service, due, interval_s=30.0)
    worker.start()
    try:
        await until(lambda: service.started == ["run-a"])
        await asyncio.sleep(0.1)
        assert service.started == ["run-a"]
    finally:
        await worker.stop()


async def test_a_failing_run_is_retried_less_often_each_time() -> None:
    service = FakeService(raise_for={"run-a": RuntimeError("run A is broken")})
    loop = asyncio.get_running_loop()
    attempts: list[float] = []

    async def due() -> Sequence[str]:
        return ["run-a"]

    async def advance(run_id: str) -> None:
        attempts.append(loop.time())
        await service.advance(run_id)

    worker = AdvanceWorker(due_runs=due, advance_run=advance, start_delay_s=0.0, interval_s=0.02)
    worker.start()
    try:
        await until(lambda: len(attempts) >= 4)
    finally:
        await worker.stop()

    gaps = [b - a for a, b in itertools.pairwise(attempts)]
    assert gaps[2] > gaps[0] * 2


async def test_a_run_that_recovers_is_no_longer_held_back() -> None:
    service = FakeService()

    async def due() -> Sequence[str]:
        return ["run-a"]

    async def advance(run_id: str) -> None:
        if not service.started:  # only the first attempt fails
            service.started.append(run_id)
            raise RuntimeError("once")
        await service.advance(run_id)

    # A nudge-free success after a failure must reset the backoff: with an
    # interval this short, three successes arrive well within the timeout only
    # if the run is back to being advanced every tick.
    worker = AdvanceWorker(due_runs=due, advance_run=advance, start_delay_s=0.0, interval_s=0.01)
    worker.start()
    try:
        await until(lambda: len(service.finished) >= 3)
    finally:
        await worker.stop()


async def test_a_repeated_failure_logs_its_traceback_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = FakeService(raise_for={"run-a": RuntimeError("run A is broken")})

    async def due() -> Sequence[str]:
        return ["run-a"]

    worker = AdvanceWorker(
        due_runs=due, advance_run=service.advance, start_delay_s=0.0, interval_s=0.005
    )
    with caplog.at_level("WARNING", logger="coffer.application.workflow.advance_worker"):
        worker.start()
        try:
            await until(lambda: len(service.started) >= 3)
        finally:
            await worker.stop()

    with_traceback = [r for r in caplog.records if r.exc_info]
    assert len(with_traceback) == 1


async def test_a_run_is_given_up_after_too_many_failures_until_nudged() -> None:
    service = FakeService(raise_for={"run-a": RuntimeError("run A is broken")})

    async def due() -> Sequence[str]:
        return ["run-a"]

    worker = AdvanceWorker(
        due_runs=due,
        advance_run=service.advance,
        start_delay_s=0.0,
        interval_s=0.005,
        max_failures=3,
    )
    worker.start()
    try:
        await until(lambda: len(service.started) == 3)
        await asyncio.sleep(0.2)  # many backoffs' worth of ticks
        assert len(service.started) == 3

        worker.nudge()  # a developer acted: a fresh budget
        await until(lambda: len(service.started) == 6)
        await asyncio.sleep(0.2)
        assert len(service.started) == 6
    finally:
        await worker.stop()
