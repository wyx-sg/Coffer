"""``workflow_runs`` and ``workflow_events`` against real SQLite.

The round-trips, and the two things the schema exists to make true: a stale
version loses (FR-015), and a run's log cannot be forked (one ``sequence`` per
run). The cascade lives here too, because deleting a run is the one write that
reaches all four tables at once.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy.exc

from coffer.infrastructure.workflow.repository import RunProjection

from .conftest import Repos

SNAPSHOT = {
    "stages": [{"key": "design", "nodes": [{"key": "draft_td", "type": "ai"}]}],
}
ACTOR = {"actor_kind": "human", "actor_id": "owner", "source_surface": "web"}


async def _run(repos: Repos, **overrides: object) -> str:
    run_id = uuid.uuid4().hex
    kwargs: dict[str, object] = {
        "run_id": run_id,
        "title": "Ship the thing",
        "workdir": "/repo",
        "machine_id": "machine-a",
        "template_snapshot": SNAPSHOT,
        "template_ref": "delivery",
    }
    kwargs.update(overrides)
    await repos.runs.create_run(**kwargs)  # type: ignore[arg-type]
    return run_id


# --------------------------------------------------------------------------- #
# workflow_runs
# --------------------------------------------------------------------------- #


async def test_run_round_trips_with_its_frozen_snapshot(repos: Repos) -> None:
    run_id = await _run(repos)

    row = await repos.runs.get_run(run_id)

    assert row is not None
    assert row.title == "Ship the thing"
    assert row.workdir == "/repo"
    assert row.machine_id == "machine-a"
    assert row.template_ref == "delivery"
    # The snapshot is the thing the engine executes, so it must survive the
    # round trip structurally, not as a string that happens to look like JSON.
    assert row.template_snapshot["stages"][0]["nodes"][0]["key"] == "draft_td"
    assert row.status == "draft"
    assert row.version == 1
    assert row.tokens_spent == 0
    assert row.inputs == []


async def test_list_runs_filters_by_status_and_is_newest_first(repos: Repos) -> None:
    older = await _run(repos, title="Older")
    newer = await _run(repos, title="Newer")
    base = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    await repos.runs.update_run_projection(
        older, 1, RunProjection("running", "design", "draft_td", 0), now=base
    )
    await repos.runs.update_run_projection(
        newer, 1, RunProjection("running", "design", "draft_td", 0), now=base + timedelta(hours=1)
    )
    await _run(repos, title="Still a draft")

    running = await repos.runs.list_runs(status="running")

    assert [r.id for r in running] == [newer, older]
    assert len(await repos.runs.list_runs()) == 3


async def test_projection_update_bumps_the_version(repos: Repos) -> None:
    run_id = await _run(repos)

    updated = await repos.runs.update_run_projection(
        run_id, 1, RunProjection("running", "design", "draft_td", 1200)
    )

    assert updated is not None
    assert updated.version == 2
    assert updated.status == "running"
    assert updated.current_stage_key == "design"
    assert updated.current_node_key == "draft_td"
    assert updated.tokens_spent == 1200


@pytest.mark.acceptance(spec="workflow", scenario="a stale version is refused rather than applied")
async def test_stale_version_is_refused_and_changes_nothing(repos: Repos) -> None:
    """FR-015: the second of two callers who both observed version 1 loses."""
    run_id = await _run(repos)
    first = await repos.runs.update_run_projection(
        run_id, 1, RunProjection("running", "design", "draft_td", 10)
    )
    assert first is not None

    conflict = await repos.runs.update_run_projection(
        run_id, 1, RunProjection("aborted", None, None, 999)
    )

    assert conflict is None
    row = await repos.runs.get_run(run_id)
    assert row is not None
    assert row.version == 2
    assert row.status == "running"
    assert row.tokens_spent == 10


async def test_projection_update_of_an_unknown_run_is_refused(repos: Repos) -> None:
    assert (
        await repos.runs.update_run_projection(
            "no-such-run", 1, RunProjection("running", None, None, 0)
        )
        is None
    )


# --------------------------------------------------------------------------- #
# workflow_events
# --------------------------------------------------------------------------- #


async def test_events_round_trip_and_number_themselves(repos: Repos) -> None:
    run_id = await _run(repos)

    first = await repos.events.append_event(
        event_id=uuid.uuid4().hex,
        run_id=run_id,
        event_type="run.created",
        actor=ACTOR,
    )
    second = await repos.events.append_event(
        event_id=uuid.uuid4().hex,
        run_id=run_id,
        event_type="node.started",
        actor=ACTOR,
        stage_key="design",
        node_key="draft_td",
        payload={"attempt": 1},
    )

    assert (first.sequence, second.sequence) == (1, 2)
    assert second.actor["source_surface"] == "web"
    assert second.payload == {"attempt": 1}
    assert second.node_key == "draft_td"
    assert first.payload == {}

    listed = await repos.events.list_events(run_id)
    assert [e.event_type for e in listed] == ["run.created", "node.started"]
    assert [e.sequence for e in listed[1:]] == [2]
    assert [e.event_type for e in await repos.events.list_events(run_id, after_sequence=1)] == [
        "node.started"
    ]


async def test_sequences_are_per_run_not_global(repos: Repos) -> None:
    one = await _run(repos)
    two = await _run(repos)

    await repos.events.append_event(
        event_id=uuid.uuid4().hex, run_id=one, event_type="run.created", actor=ACTOR
    )
    other = await repos.events.append_event(
        event_id=uuid.uuid4().hex, run_id=two, event_type="run.created", actor=ACTOR
    )

    assert other.sequence == 1


async def test_duplicate_sequence_in_a_run_is_refused(repos: Repos) -> None:
    """The log cannot be forked: ``(run_id, sequence)`` is unique."""
    run_id = await _run(repos)
    await repos.events.append_event(
        event_id=uuid.uuid4().hex, run_id=run_id, event_type="run.created", actor=ACTOR
    )

    from coffer.infrastructure.workflow.models import WorkflowEventModel

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        async with repos.events._sm() as session:
            session.add(
                WorkflowEventModel(
                    id=uuid.uuid4().hex,
                    run_id=run_id,
                    sequence=1,
                    event_type="run.started",
                    actor=ACTOR,
                    payload={},
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()


async def test_deleting_a_run_cascades_its_children(repos: Repos) -> None:
    run_id = await _run(repos)
    await repos.events.append_event(
        event_id=uuid.uuid4().hex, run_id=run_id, event_type="run.created", actor=ACTOR
    )
    attempt = await repos.attempts.insert_attempt(
        attempt_id=uuid.uuid4().hex,
        run_id=run_id,
        stage_key="design",
        node_key="draft_td",
        attempt=1,
    )
    await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=run_id,
        kind="tool_call",
        payload={"a": 1},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        attempt_id=attempt.id,
    )

    from sqlalchemy import delete

    from coffer.infrastructure.workflow.models import WorkflowRunModel

    async with repos.runs._sm() as session:
        await session.execute(delete(WorkflowRunModel).where(WorkflowRunModel.id == run_id))
        await session.commit()

    assert await repos.events.list_events(run_id) == []
    assert await repos.attempts.list_attempts(run_id) == []
    assert await repos.approvals.list_approvals(run_id) == []
