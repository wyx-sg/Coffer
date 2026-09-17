"""``workflow_node_attempts`` and ``workflow_approvals`` against real SQLite.

A retry appends rather than rewrites (FR-022), an ad-hoc task is recorded as
any node is (FR-028), and a decision is taken exactly once — repeated,
expired, or superseded by an abort (FR-033, FR-037, FR-038).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy.exc

from coffer.domain.workflow.run import ApprovalStatus

from .conftest import Repos

SNAPSHOT = {
    "attempt_ceiling": 3,
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
        "template_ref": "workflow:delivery",
    }
    kwargs.update(overrides)
    await repos.runs.create_run(**kwargs)  # type: ignore[arg-type]
    return run_id


# --------------------------------------------------------------------------- #
# workflow_node_attempts
# --------------------------------------------------------------------------- #


async def test_attempt_round_trips_and_moves_forward(repos: Repos) -> None:
    run_id = await _run(repos)
    started = datetime.now(UTC)

    row = await repos.attempts.insert_attempt(
        attempt_id=uuid.uuid4().hex,
        run_id=run_id,
        stage_key="design",
        node_key="draft_td",
        attempt=1,
        status="running",
        conversation_id="conv-1",
        started_at=started,
    )
    updated = await repos.attempts.update_attempt(
        row.id, status="failed", failure_reason="interrupted", tokens=4200
    )

    assert updated is not None
    assert updated.status == "failed"
    assert updated.failure_reason == "interrupted"
    assert updated.tokens == 4200
    # Not passed on the update, so not touched — an attempt only moves forward.
    assert updated.conversation_id == "conv-1"
    assert updated.stage_key == "design"


async def test_a_retry_is_a_second_row_and_the_first_survives(repos: Repos) -> None:
    """FR-022: a retry appends ``attempt + 1``; the earlier try stays readable."""
    run_id = await _run(repos)
    first = await repos.attempts.insert_attempt(
        attempt_id=uuid.uuid4().hex,
        run_id=run_id,
        stage_key="design",
        node_key="draft_td",
        attempt=1,
        status="failed",
        conversation_id="conv-1",
    )
    await repos.attempts.insert_attempt(
        attempt_id=uuid.uuid4().hex,
        run_id=run_id,
        stage_key="design",
        node_key="draft_td",
        attempt=2,
        status="running",
        conversation_id="conv-2",
    )

    latest = await repos.attempts.latest_attempt(run_id, "draft_td")
    assert latest is not None
    assert (latest.attempt, latest.conversation_id) == (2, "conv-2")

    kept = await repos.attempts.list_attempts(run_id)
    assert [a.attempt for a in kept] == [1, 2]
    assert kept[0].id == first.id
    assert kept[0].conversation_id == "conv-1"


async def test_duplicate_attempt_number_for_a_node_is_refused(repos: Repos) -> None:
    run_id = await _run(repos)
    await repos.attempts.insert_attempt(
        attempt_id=uuid.uuid4().hex,
        run_id=run_id,
        stage_key="design",
        node_key="draft_td",
        attempt=1,
    )

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await repos.attempts.insert_attempt(
            attempt_id=uuid.uuid4().hex,
            run_id=run_id,
            stage_key="design",
            node_key="draft_td",
            attempt=1,
        )


async def test_an_adhoc_task_is_an_attempt_like_any_other(repos: Repos) -> None:
    """FR-028: an unplanned task is recorded and attributed exactly as a node is."""
    run_id = await _run(repos)

    row = await repos.attempts.insert_attempt(
        attempt_id=uuid.uuid4().hex,
        run_id=run_id,
        stage_key="coding",
        node_key="adhoc:rerun-the-migration",
        attempt=1,
        instructions="Re-run 0085 against the staging copy.",
    )

    assert row.node_key == "adhoc:rerun-the-migration"
    latest = await repos.attempts.latest_attempt(run_id, "adhoc:rerun-the-migration")
    assert latest is not None
    assert latest.instructions == "Re-run 0085 against the staging copy."


async def test_latest_attempt_of_an_unstarted_node_is_none(repos: Repos) -> None:
    run_id = await _run(repos)
    assert await repos.attempts.latest_attempt(run_id, "never_started") is None


# --------------------------------------------------------------------------- #
# workflow_approvals
# --------------------------------------------------------------------------- #


async def test_approval_round_trips_with_its_payload_verbatim(repos: Repos) -> None:
    run_id = await _run(repos)
    expires = datetime.now(UTC) + timedelta(minutes=30)
    payload = {"repo": "coffer", "title": "Ship it", "labels": ["release", "risky"]}

    row = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=run_id,
        kind="tool_call",
        tool_name="gitlab__create_merge_request",
        payload=payload,
        expires_at=expires,
    )

    stored = await repos.approvals.get_approval(row.id)
    assert stored is not None
    assert stored.status == ApprovalStatus.PENDING.value
    assert stored.tool_name == "gitlab__create_merge_request"
    # Verbatim, not a summary (FR-033) — nested structure and all.
    assert stored.payload == payload
    assert stored.decided_at is None


@pytest.mark.acceptance(spec="workflow", scenario="an approval decision is idempotent")
async def test_a_second_decision_returns_the_first_one_unchanged(repos: Repos) -> None:
    """FR-038: deciding twice does not authorise a second execution."""
    run_id = await _run(repos)
    row = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=run_id,
        kind="tool_call",
        payload={},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    approved = await repos.approvals.decide_approval(
        row.id, status=ApprovalStatus.APPROVED.value, decided_by="owner", decided_surface="web"
    )
    assert approved is not None
    first_decided_at = approved.decided_at

    again = await repos.approvals.decide_approval(
        row.id, status=ApprovalStatus.REJECTED.value, decided_by="someone-else"
    )

    assert again is not None
    assert again.status == ApprovalStatus.APPROVED.value
    assert again.decided_by == "owner"
    assert again.decided_at == first_decided_at


async def test_deciding_an_unknown_approval_is_none(repos: Repos) -> None:
    assert await repos.approvals.decide_approval("nope", status="approved") is None


async def test_only_approvals_past_their_deadline_expire(repos: Repos) -> None:
    run_id = await _run(repos)
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    due = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=run_id,
        kind="tool_call",
        payload={},
        expires_at=now - timedelta(seconds=1),
    )
    fresh = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=run_id,
        kind="tool_call",
        payload={},
        expires_at=now + timedelta(minutes=10),
    )

    expired = await repos.approvals.expire_due_approvals(now=now)

    assert [a.id for a in expired] == [due.id]
    still_pending = await repos.approvals.list_approvals(
        run_id, status=ApprovalStatus.PENDING.value
    )
    assert [a.id for a in still_pending] == [fresh.id]


async def test_an_already_decided_approval_does_not_expire(repos: Repos) -> None:
    run_id = await _run(repos)
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    row = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=run_id,
        kind="tool_call",
        payload={},
        expires_at=now - timedelta(seconds=1),
    )
    await repos.approvals.decide_approval(row.id, status=ApprovalStatus.APPROVED.value)

    assert await repos.approvals.expire_due_approvals(now=now) == []
    kept = await repos.approvals.get_approval(row.id)
    assert kept is not None
    assert kept.status == ApprovalStatus.APPROVED.value


async def test_aborting_supersedes_only_this_run_s_pending_approvals(repos: Repos) -> None:
    aborted = await _run(repos)
    other = await _run(repos)
    mine = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=aborted,
        kind="node_action",
        payload={"action": "complete"},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    theirs = await repos.approvals.create_approval(
        approval_id=uuid.uuid4().hex,
        run_id=other,
        kind="node_action",
        payload={},
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )

    superseded = await repos.approvals.supersede_pending(aborted)

    assert [a.id for a in superseded] == [mine.id]
    untouched = await repos.approvals.get_approval(theirs.id)
    assert untouched is not None
    assert untouched.status == ApprovalStatus.PENDING.value
