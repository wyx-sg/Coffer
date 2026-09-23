"""The adapter behind a task's index of the run so far (spec workflow "Generate
the index of earlier tasks").

It is the one place that turns attempt ROWS into the index the composer
renders, so the three judgements it makes are worth pinning: which attempt of a
task is the one to show, what a task is called, and what happens when the
template it would read the name from will not parse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.surfaces.http.workflow_adapters import EarlierTasks

NOW = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)

TEMPLATE = {
    "stages": [
        {
            "key": "design",
            "name": "Design",
            "nodes": [{"key": "draft_td", "name": "Draft the technical design", "type": "ai"}],
        },
        {
            "key": "build",
            "name": "Build",
            "nodes": [{"key": "implement", "name": "Make the change", "type": "ai"}],
        },
    ]
}


@dataclass
class FakeRun:
    id: str = "run-1"
    template_snapshot: object = None


@dataclass
class FakeAttempt:
    id: str
    node_key: str
    attempt: int = 1
    status: str = "completed"
    failure_reason: str | None = None
    started_at: datetime | None = NOW


class FakeRuns:
    def __init__(self, snapshot: object = None) -> None:
        self.snapshot = snapshot if snapshot is not None else TEMPLATE

    async def get_run(self, run_id: str) -> FakeRun | None:
        return FakeRun(id=run_id, template_snapshot=self.snapshot)


class FakeAttempts:
    def __init__(self, rows: list[FakeAttempt]) -> None:
        self.rows = rows

    async def list_attempts(self, run_id: str) -> list[FakeAttempt]:
        return list(self.rows)


def adapter(rows: list[FakeAttempt], *, snapshot: object = None) -> EarlierTasks:
    return EarlierTasks(runs=FakeRuns(snapshot), attempts=FakeAttempts(rows))


async def test_a_task_is_named_by_the_runs_frozen_template() -> None:
    rows = [FakeAttempt(id="a1", node_key="draft_td"), FakeAttempt(id="a2", node_key="implement")]

    earlier = await adapter(rows).earlier("run-1", "a2")

    assert [(t.node_key, t.name) for t in earlier] == [("draft_td", "Draft the technical design")]


async def test_only_the_latest_attempt_of_a_task_is_listed() -> None:
    """A retry supersedes; the index must not offer both answers.

    The run reopened the task because what it produced was not right, so
    listing attempt 1 beside attempt 2 would hand the next task a discarded
    deliverable with nothing to tell it apart from the real one.
    """
    rows = [
        FakeAttempt(id="a1", node_key="draft_td", attempt=1, status="failed"),
        FakeAttempt(id="a2", node_key="draft_td", attempt=2, status="completed"),
        FakeAttempt(id="a3", node_key="implement"),
    ]

    earlier = await adapter(rows).earlier("run-1", "a3")

    assert [(t.node_key, t.attempt, t.status) for t in earlier] == [("draft_td", 2, "completed")]


async def test_a_retry_still_sees_what_its_own_earlier_attempt_did() -> None:
    """The one case where a task appears "before itself", and it should.

    Attempt 2 of a task opens with attempt 1 of that same task in its index —
    which failed, and produced what it produced. That is the most useful thing
    anyone in the run knows, and cutting it would make a retry start blind to
    the reason it exists.
    """
    rows = [
        FakeAttempt(
            id="a1", node_key="draft_td", attempt=1, status="failed", failure_reason="interrupted"
        ),
        FakeAttempt(id="a2", node_key="draft_td", attempt=2, status="running"),
    ]

    earlier = await adapter(rows).earlier("run-1", "a2")

    assert [(t.node_key, t.attempt, t.failure_reason) for t in earlier] == [
        ("draft_td", 1, "interrupted")
    ]


async def test_nothing_from_this_attempt_onwards_is_in_the_index() -> None:
    rows = [
        FakeAttempt(id="a1", node_key="draft_td"),
        FakeAttempt(id="a2", node_key="implement"),
        FakeAttempt(id="a3", node_key="release"),
    ]

    earlier = await adapter(rows).earlier("run-1", "a2")

    assert [t.node_key for t in earlier] == ["draft_td"]


async def test_an_adhoc_task_is_named_from_its_key_rather_than_left_as_one() -> None:
    """An unplanned task is in no template, so no lookup answers for it.

    Un-slugging the key is not the name the developer typed, but it is never
    wrong about WHICH task it is, and `fix the parser` reads where
    `adhoc:fix-the-parser` does not.
    """
    rows = [
        FakeAttempt(id="a1", node_key="adhoc:fix-the-parser"),
        FakeAttempt(id="a2", node_key="implement"),
    ]

    earlier = await adapter(rows).earlier("run-1", "a2")

    assert earlier[0].name == "fix the parser"


async def test_a_snapshot_that_will_not_parse_still_yields_an_index() -> None:
    """A display name is not worth refusing to open a task over.

    The keys are readable on their own, so a run whose snapshot is corrupt gets
    an index of keys rather than a task that cannot start — the context layer
    is not the place that decides a run is over.
    """
    rows = [FakeAttempt(id="a1", node_key="draft_td"), FakeAttempt(id="a2", node_key="implement")]

    earlier = await adapter(rows, snapshot={"stages": "not a list"}).earlier("run-1", "a2")

    assert [(t.node_key, t.name) for t in earlier] == [("draft_td", "draft_td")]
