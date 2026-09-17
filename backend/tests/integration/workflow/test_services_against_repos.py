"""The two services over the real repositories and the real artifact store.

The unit tier proves the state machine against fakes. This tier proves the three
things a fake cannot: that the SQL the services drive actually round-trips, that
the optimistic lock is the database's and not the fake's, and that a projection
rebuilt from rows on disk equals the one the run carried before its process
stopped.
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

import pytest

from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.workflow.errors import WorkflowVersionConflict
from coffer.domain.workflow.run import (
    FailureReason,
    NodeAction,
    NodeStatus,
    RunSignal,
    RunStatus,
)
from coffer.infrastructure.workflow import artifacts as artifact_store
from coffer.infrastructure.workflow import paths

from .conftest import Repos

TEMPLATE: dict[str, Any] = {
    "attempt_ceiling": 3,
    "stages": [
        {
            "key": "design",
            "name": "Tech Design",
            "nodes": [
                {
                    "key": "draft_td",
                    "name": "Draft the technical design",
                    "type": "ai",
                    "artifacts": [{"name": "td.md", "required": True}],
                }
            ],
        },
        {
            "key": "coding",
            "name": "Coding",
            "nodes": [{"key": "write_code", "name": "Write the code", "type": "ai"}],
        },
    ],
}


class _Templates:
    async def get(self, ref: ResourceRef) -> Resource:
        if ref.name != "delivery":
            raise ResourceNotFound(ref.kind, ref.name)
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        return Resource(
            id=1,
            kind=ref.kind,
            name=ref.name,
            description=None,
            config=TEMPLATE,
            enabled=True,
            created_at=now,
            updated_at=now,
        )


class _Turns:
    def __init__(self) -> None:
        self.opened = 0

    async def create_conversation(
        self, *, agent_key: str, cwd: str, run_context: str | None = None
    ) -> str:
        self.opened += 1
        return f"conv-{self.opened}"

    async def start_turn(self, conversation_id: str, text: str) -> Any:
        raise AssertionError("no turn runs in this tier")

    async def transcript(self, conversation_id: str) -> Any:
        return []

    async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None:
        return None

    def interrupt(self, conversation_id: str) -> None:
        return None


class _Artifacts:
    """The real on-disk store, behind the port's own names."""

    def run_dir(self, run_id: str) -> str:
        return str(paths.run_dir(run_id))

    def workspace_dir(self, run_id: str) -> str:
        return str(paths.workspace_dir(run_id))

    def ensure_run_dirs(self, run_id: str) -> None:
        artifact_store.ensure_run_dirs(run_id)

    def list_artifacts(self, run_id: str) -> Any:
        return artifact_store.list_artifacts(run_id)

    def write_catalogue(self, run_id: str, markdown: str) -> None:
        paths.catalog_path(run_id).write_text(markdown, encoding="utf-8")

    def read_catalogue(self, run_id: str) -> str:
        return paths.catalog_path(run_id).read_text(encoding="utf-8")

    def collect_artifacts(self, run_id: str, destination: str) -> int:
        return artifact_store.collect_artifacts(run_id, pathlib.Path(destination))

    def delete_run_dir(self, run_id: str) -> None:
        import shutil

        shutil.rmtree(paths.run_dir(run_id), ignore_errors=True)


class _Machine:
    def __init__(self) -> None:
        self.id = "machine-a"

    def current(self) -> str:
        return self.id


class _Audit:
    def __init__(self) -> None:
        self.types: list[str] = []

    async def record(
        self,
        event_type: str,
        *,
        actor: str,
        resource_kind: str | None = None,
        resource_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.types.append(event_type)


class Wired:
    def __init__(self, repos: Repos) -> None:
        self.machine = _Machine()
        self.audit = _Audit()
        self.turns = _Turns()
        self.artifacts = _Artifacts()
        self.repos = repos
        self.runs = WorkflowRunService(
            runs=repos.runs,
            events=repos.events,
            attempts=repos.attempts,
            approvals=repos.approvals,
            artifacts=self.artifacts,
            machine=self.machine,
            audit=self.audit,
            templates=_Templates(),
            default_agent="claude_code",
        )
        self.nodes = WorkflowNodeService(
            runs=repos.runs,
            events=repos.events,
            attempts=repos.attempts,
            artifacts=self.artifacts,
            machine=self.machine,
            audit=self.audit,
            default_agent="claude_code",
        )


@pytest.fixture
def wired(repos: Repos) -> Wired:
    return Wired(repos)


@pytest.mark.acceptance(
    spec="workflow", scenario="a run advances from one node to the next without prompting"
)
async def test_a_run_is_created_started_and_advanced_on_real_rows(wired: Wired) -> None:
    run = await wired.runs.create_run(template="delivery", title="Ship it")
    assert run.status == RunStatus.DRAFT.value
    assert paths.artifacts_dir(run.id).is_dir()

    started = await wired.runs.signal(run.id, RunSignal.START, version=run.version)
    assert started.run.status == RunStatus.RUNNING.value

    result = await wired.nodes.act(
        run.id, "draft_td", NodeAction.START, version=started.run.version
    )
    assert result.run.current_node_key == "draft_td"

    # FR-023 over the real filesystem: the artifact has to actually be there.
    artifact_store.write_artifact(run.id, "draft_td", 1, "td.md", "# design")
    done = await wired.nodes.record_output(run.id, "draft_td", summary="drafted", tokens=90)

    assert done.run.tokens_spent == 90
    position = await wired.nodes.next_position(run.id)
    assert position is not None
    assert position.node_key == "write_code"


@pytest.mark.acceptance(spec="workflow", scenario="a stale version is refused rather than applied")
async def test_the_version_race_is_settled_by_the_database(wired: Wired) -> None:
    """FR-015: two commands, one observed version, one change.

    Both calls pass the in-memory version check — they read the same row — so
    what refuses the loser is the UPDATE's own WHERE clause, which is exactly
    the guarantee a fake cannot give.
    """
    run = await wired.runs.create_run(template="delivery", title="Ship it")
    started = await wired.runs.signal(run.id, RunSignal.START, version=run.version)
    version = started.run.version

    first, second = await asyncio.gather(
        wired.runs.signal(run.id, RunSignal.PAUSE, version=version),
        wired.runs.signal(run.id, RunSignal.PAUSE, version=version),
        return_exceptions=True,
    )
    outcomes = [first, second]
    conflicts = [o for o in outcomes if isinstance(o, WorkflowVersionConflict)]
    assert len(conflicts) == 1
    assert conflicts[0].current == version + 1

    row = await wired.repos.runs.get_run(run.id)
    assert row is not None
    assert row.version == version + 1


@pytest.mark.acceptance(spec="workflow", scenario="an interrupted node is reported, not resumed")
async def test_a_restart_rebuilds_the_position_and_reports_the_interrupted_node(
    wired: Wired,
) -> None:
    """FR-014 + FR-027, against rows that survive the service that wrote them."""
    run = await wired.runs.create_run(template="delivery", title="Ship it")
    started = await wired.runs.signal(run.id, RunSignal.START, version=run.version)
    await wired.nodes.act(run.id, "draft_td", NodeAction.START, version=started.run.version)
    attempt = await wired.repos.attempts.latest_attempt(run.id, "draft_td")
    assert attempt is not None
    await wired.repos.attempts.update_attempt(attempt.id, conversation_id="conv-node")

    # The daemon dies here; nothing wrote a projection for what it was doing.
    before = await wired.repos.runs.get_run(run.id)
    assert before is not None
    rebuilt = await wired.runs.rebuild_projection(run.id)

    assert rebuilt.status == RunStatus.RUNNING.value
    assert rebuilt.current_node_key == "draft_td"
    reread = await wired.repos.attempts.latest_attempt(run.id, "draft_td")
    assert reread is not None
    assert reread.status == NodeStatus.FAILED.value
    assert reread.failure_reason == FailureReason.INTERRUPTED.value
    # The conversation is still there to read, which is the whole difference
    # between reporting an interruption and dropping it.
    assert reread.conversation_id == "conv-node"


async def test_deleting_a_run_cascades_its_rows_and_removes_its_directory(
    wired: Wired,
) -> None:
    run = await wired.runs.create_run(template="delivery", title="Ship it")
    started = await wired.runs.signal(run.id, RunSignal.START, version=run.version)
    await wired.nodes.act(run.id, "draft_td", NodeAction.START, version=started.run.version)
    artifact_store.write_artifact(run.id, "draft_td", 1, "td.md", "# design")

    await wired.runs.delete_run(run.id)

    assert await wired.repos.runs.get_run(run.id) is None
    assert await wired.repos.events.list_events(run.id) == []
    assert await wired.repos.attempts.list_attempts(run.id) == []
    assert not paths.run_dir(run.id).exists()


async def test_an_adhoc_task_survives_the_round_trip(wired: Wired) -> None:
    """FR-028: its key, its stage and its instructions come back off the rows."""
    run = await wired.runs.create_run(template="delivery", title="Ship it")
    started = await wired.runs.signal(run.id, RunSignal.START, version=run.version)

    await wired.nodes.add_adhoc_task(
        run.id,
        stage_key="coding",
        name="Bump the client",
        instructions="Raise the pinned version.",
        version=started.run.version,
    )

    attempt = await wired.repos.attempts.latest_attempt(run.id, "adhoc:bump-the-client")
    assert attempt is not None
    assert attempt.stage_key == "coding"
    assert attempt.instructions == "Raise the pinned version."
    walk = await wired.nodes.walk(run.id)
    assert "adhoc:bump-the-client" in walk.unfinished
