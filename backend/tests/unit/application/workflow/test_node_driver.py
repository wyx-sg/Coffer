"""One node attempt: its conversation, its turn, its outcome (FR-019, FR-030)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from coffer.application.workflow.compaction import Compaction
from coffer.application.workflow.context_composer import NodeContextRequest
from coffer.application.workflow.dispatch import NodeDispatch
from coffer.application.workflow.node_driver import MANUAL_NODE_SUMMARY, NodeDriver
from coffer.domain.chat.events import (
    AgentEvent,
    QueueChanged,
    TextDelta,
    TurnDone,
    TurnError,
    TurnStarted,
)
from coffer.domain.workflow.run import FailureReason
from coffer.domain.workflow.template import Node, NodeType


class FakePlatform:
    """A ``TurnPlatformPort`` that replays a scripted list of agent events."""

    def __init__(
        self,
        events: list[AgentEvent] | None = None,
        *,
        conversation_id: str = "conv-1",
        fail_create: Exception | None = None,
        fail_start: Exception | None = None,
    ) -> None:
        self.events = events or []
        self.conversation_id = conversation_id
        self.fail_create = fail_create
        self.fail_start = fail_start
        self.created: list[dict[str, str | None]] = []
        self.turns: list[tuple[str, str]] = []
        self.interrupted: list[str] = []

    async def create_conversation(
        self, *, agent_key: str, cwd: str, run_context: str | None = None
    ) -> str:
        if self.fail_create is not None:
            raise self.fail_create
        self.created.append({"agent_key": agent_key, "cwd": cwd, "run_context": run_context})
        return self.conversation_id

    async def start_turn(self, conversation_id: str, text: str) -> asyncio.Queue[AgentEvent | None]:
        if self.fail_start is not None:
            raise self.fail_start
        self.turns.append((conversation_id, text))
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        for event in self.events:
            queue.put_nowait(event)
        queue.put_nowait(None)
        return queue

    def interrupt(self, conversation_id: str) -> None:
        self.interrupted.append(conversation_id)


class StubCompactor:
    """``ConversationCompactor``'s shape — it only ever gets called on a
    conversation that already has history."""

    def __init__(self, *, fail: Exception | None = None) -> None:
        self.seen: list[str] = []
        self.fail = fail

    async def compact(self, conversation_id: str) -> Compaction:
        if self.fail is not None:
            raise self.fail
        self.seen.append(conversation_id)
        return Compaction(compacted=0, kept=0)


class StubComposer:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.requests: list[NodeContextRequest] = []
        self.fail = fail

    async def compose(self, request: NodeContextRequest) -> str:
        if self.fail is not None:
            raise self.fail
        self.requests.append(request)
        return f"opening context for {request.node.key}"


@dataclass
class Recorder:
    opened: list[tuple[str, str]] = field(default_factory=list)
    ready: list[tuple[str, str, int]] = field(default_factory=list)
    failed: list[tuple[str, FailureReason, str]] = field(default_factory=list)

    async def on_conversation_opened(self, attempt_id: str, conversation_id: str) -> None:
        self.opened.append((attempt_id, conversation_id))

    async def on_output_ready(self, attempt_id: str, summary: str, tokens: int) -> None:
        self.ready.append((attempt_id, summary, tokens))

    async def on_failed(self, attempt_id: str, reason: FailureReason, detail: str) -> None:
        self.failed.append((attempt_id, reason, detail))


@dataclass
class FakeRun:
    """The ``RunRow`` attributes the driver reads off a dispatch, and no more."""

    id: str = "run-1"
    title: str = "Ship the retry fix"
    inputs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FakeAttempt:
    """The ``AttemptRow`` attributes the driver reads, and no more."""

    id: str = "att-1"
    run_id: str = "run-1"
    attempt: int = 1
    status: str = "running"
    conversation_id: str | None = None
    #: What the developer queued for this attempt before it opened (FR-068).
    instructions: str | None = None


def make_driver(
    platform: FakePlatform,
    composer: StubComposer | None = None,
    compactor: StubCompactor | None = None,
) -> tuple[NodeDriver, Recorder, StubComposer]:
    recorder = Recorder()
    composer = composer or StubComposer()
    driver = NodeDriver(
        platform=platform,  # type: ignore[arg-type]
        composer=composer,  # type: ignore[arg-type]
        compactor=compactor or StubCompactor(),  # type: ignore[arg-type]
        on_conversation_opened=recorder.on_conversation_opened,
        on_output_ready=recorder.on_output_ready,
        on_failed=recorder.on_failed,
    )
    return driver, recorder, composer


def make_dispatch(
    *,
    node_type: NodeType = NodeType.AI,
    follow_up: str | None = None,
    attempt: FakeAttempt | None = None,
    run: FakeRun | None = None,
) -> NodeDispatch:
    return NodeDispatch(
        run=run or FakeRun(),  # type: ignore[arg-type]
        stage_key="design",
        node=Node(key="draft_td", name="Draft the design", type=node_type),
        attempt=attempt or FakeAttempt(),  # type: ignore[arg-type]
        agent_key="claude_code",
        workdir="/repo",
        follow_up=follow_up,
    )


@pytest.mark.acceptance(spec="workflow", scenario="a node's work happens in its own conversation")
async def test_a_nodes_work_happens_in_a_conversation_in_the_runs_workdir() -> None:
    platform = FakePlatform([TurnStarted(), TextDelta(text="done")])
    driver, recorder, composer = make_driver(platform)

    await driver.run(make_dispatch())

    assert platform.created == [
        {"agent_key": "claude_code", "cwd": "/repo", "run_context": "run-1/att-1"}
    ]
    assert recorder.opened == [("att-1", "conv-1")]
    assert platform.turns == [("conv-1", "opening context for draft_td")]
    assert composer.requests[0].attempt_id == "att-1"
    assert composer.requests[0].attempt == 1


@pytest.mark.acceptance(spec="workflow", scenario="a node's work happens in its own conversation")
async def test_the_conversation_is_recorded_before_the_turn_starts() -> None:
    # FR-027: an interrupted attempt must still have a readable conversation,
    # which is only true if the id was reported before anything could be lost.
    done = TurnDone(prompt_tokens=1, completion_tokens=1, stop_reason="end_turn")
    platform = FakePlatform([done])
    driver, recorder, _composer = make_driver(platform)
    order: list[str] = []

    async def note_open(attempt_id: str, conversation_id: str) -> None:
        order.append("opened")

    original_start = platform.start_turn

    async def noting_start(conversation_id: str, text: str) -> asyncio.Queue[AgentEvent | None]:
        order.append("started")
        return await original_start(conversation_id, text)

    driver._on_conversation_opened = note_open
    platform.start_turn = noting_start  # type: ignore[method-assign]

    await driver.run(make_dispatch())

    assert order == ["opened", "started"]
    assert recorder.ready


async def test_the_assistants_text_and_tokens_become_the_nodes_output() -> None:
    platform = FakePlatform(
        [
            TurnStarted(),
            TextDelta(text="Wrote "),
            TextDelta(text="td.md.\n"),
            QueueChanged(pending=[]),
            TurnDone(prompt_tokens=120, completion_tokens=30, stop_reason="end_turn"),
        ]
    )
    driver, recorder, _composer = make_driver(platform)

    await driver.run(make_dispatch())

    assert recorder.ready == [("att-1", "Wrote td.md.", 150)]
    assert recorder.failed == []


async def test_an_adapter_that_reports_no_tokens_contributes_zero_not_a_guess() -> None:
    silent = TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end_turn")
    driver, recorder, _composer = make_driver(FakePlatform([TextDelta(text="ok"), silent]))

    await driver.run(make_dispatch())

    assert recorder.ready == [("att-1", "ok", 0)]


async def test_a_turn_error_fails_the_attempt_with_the_agents_own_words() -> None:
    platform = FakePlatform(
        [
            TextDelta(text="partial"),
            TurnError(code="stream_ended", message="the agent stopped responding"),
        ]
    )
    driver, recorder, _composer = make_driver(platform)

    await driver.run(make_dispatch())

    assert recorder.ready == []
    assert recorder.failed == [
        ("att-1", FailureReason.AGENT_ERROR, "stream_ended: the agent stopped responding")
    ]


async def test_the_first_turn_error_is_the_reason_reported() -> None:
    errors = [TurnError(code="first", message="one"), TurnError(code="second", message="two")]
    driver, recorder, _composer = make_driver(FakePlatform(errors))

    await driver.run(make_dispatch())

    assert recorder.failed[0][2] == "first: one"


async def test_a_conversation_that_cannot_be_opened_fails_the_attempt() -> None:
    platform = FakePlatform(fail_create=RuntimeError("no such agent"))
    driver, recorder, _composer = make_driver(platform)

    await driver.run(make_dispatch())

    assert recorder.opened == []
    assert recorder.failed == [("att-1", FailureReason.AGENT_ERROR, "no such agent")]


async def test_a_turn_that_cannot_be_started_fails_the_attempt() -> None:
    platform = FakePlatform(fail_start=RuntimeError("turn in progress"))
    driver, recorder, _composer = make_driver(platform)

    await driver.run(make_dispatch())

    assert recorder.opened == [("att-1", "conv-1")]
    assert recorder.failed == [("att-1", FailureReason.AGENT_ERROR, "turn in progress")]


async def test_context_that_cannot_be_composed_fails_the_attempt_not_the_worker() -> None:
    platform = FakePlatform()
    driver, recorder, _composer = make_driver(platform, StubComposer(fail=OSError("disk gone")))

    await driver.run(make_dispatch())

    assert platform.turns == []
    assert recorder.failed == [("att-1", FailureReason.AGENT_ERROR, "disk gone")]


async def test_a_manual_node_opens_no_conversation_and_waits_for_the_developer() -> None:
    platform = FakePlatform()
    driver, recorder, composer = make_driver(platform)

    await driver.run(make_dispatch(node_type=NodeType.MANUAL))

    assert platform.created == []
    assert platform.turns == []
    assert composer.requests == []
    assert recorder.ready == [("att-1", MANUAL_NODE_SUMMARY, 0)]


async def test_feedback_runs_on_the_attempts_own_conversation_without_recomposing() -> None:
    platform = FakePlatform([TextDelta(text="fixed it")])
    driver, recorder, composer = make_driver(platform)
    attempt = FakeAttempt(conversation_id="conv-existing")

    await driver.run(make_dispatch(follow_up="Use the other region.", attempt=attempt))

    assert platform.created == []
    assert composer.requests == []
    assert platform.turns == [("conv-existing", "Use the other region.")]
    assert recorder.ready == [("att-1", "fixed it", 0)]


async def test_feedback_on_an_attempt_with_no_conversation_is_reported_not_swallowed() -> None:
    platform = FakePlatform()
    driver, recorder, _composer = make_driver(platform)

    await driver.run(make_dispatch(follow_up="Do it differently."))

    assert platform.turns == []
    assert recorder.failed[0][1] is FailureReason.AGENT_ERROR


async def test_cancelling_a_node_reports_nothing_and_leaves_the_attempt_running() -> None:
    class BlockingPlatform(FakePlatform):
        async def start_turn(
            self, conversation_id: str, text: str
        ) -> asyncio.Queue[AgentEvent | None]:
            self.turns.append((conversation_id, text))
            return asyncio.Queue()  # never terminated

    platform = BlockingPlatform()
    driver, recorder, _composer = make_driver(platform)

    task = asyncio.create_task(driver.run(make_dispatch()))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert recorder.ready == []
    assert recorder.failed == []


async def test_interrupt_reaches_the_platform_and_swallows_its_refusal() -> None:
    platform = FakePlatform()
    driver, _recorder, _composer = make_driver(platform)

    driver.interrupt("conv-a")

    assert platform.interrupted == ["conv-a"]


async def test_a_follow_up_compacts_the_conversation_before_the_turn_starts() -> None:
    # FR-049: the follow-up is the only path that runs a turn on a
    # conversation that already has history, so it is the only one that can be
    # over its share of the budget.
    platform = FakePlatform([TextDelta(text="fixed it")])
    compactor = StubCompactor()
    driver, _recorder, _composer = make_driver(platform, compactor=compactor)
    attempt = FakeAttempt(conversation_id="conv-existing")

    await driver.run(make_dispatch(follow_up="Use the other region.", attempt=attempt))

    assert compactor.seen == ["conv-existing"]
    assert platform.turns == [("conv-existing", "Use the other region.")]


async def test_opening_a_fresh_conversation_compacts_nothing() -> None:
    platform = FakePlatform([TextDelta(text="done")])
    compactor = StubCompactor()
    driver, _recorder, _composer = make_driver(platform, compactor=compactor)

    await driver.run(make_dispatch())

    assert compactor.seen == []


async def test_a_compaction_that_blows_up_does_not_cost_the_attempt_its_turn() -> None:
    platform = FakePlatform([TextDelta(text="fixed it")])
    compactor = StubCompactor(fail=RuntimeError("the model is down"))
    driver, recorder, _composer = make_driver(platform, compactor=compactor)
    attempt = FakeAttempt(conversation_id="conv-existing")

    await driver.run(make_dispatch(follow_up="Carry on.", attempt=attempt))

    assert platform.turns == [("conv-existing", "Carry on.")]
    assert recorder.ready == [("att-1", "fixed it", 0)]


async def test_the_driver_is_usable_as_the_dispatcher_seam_itself() -> None:
    platform = FakePlatform([TextDelta(text="done")])
    driver, recorder, _composer = make_driver(platform)

    await driver(make_dispatch())  # NodeDispatcher.__call__

    assert recorder.ready == [("att-1", "done", 0)]
