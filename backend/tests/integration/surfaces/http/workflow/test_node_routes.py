"""``…/nodes/{node_key}/actions`` and ``…/tasks`` — the node half (FR-021, FR-028).

Both routes answer with the node's latest attempt, so every test here reads the
same shape. The engine is driven directly where a test needs a node in a state
only a finished turn produces — ``record_output`` is what the driver calls, and
faking the HTTP route into that state instead would be testing the test.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from coffer.domain.workflow.run import FailureReason

from .conftest import Surface, act, code_of, detail, node_of, started_run

_RUNS = "/api/v1/workflow/runs"


def _reviewable(surface: Surface, run_id: str, node_key: str) -> None:
    """Take the node to ``waiting_review`` the way the driver does: it started,
    it produced something, and the developer has not answered yet."""
    asyncio.run(surface.engine.nodes.record_output(run_id, node_key, summary="drafted", tokens=7))


def _version(surface: Surface, run_id: str) -> int:
    body: dict[str, Any] = detail(surface.client, run_id)
    return int(body["run"]["version"])


# --- the six actions ---------------------------------------------------------


def test_starting_a_node_answers_with_its_running_attempt(surface: Surface) -> None:
    run = started_run(surface.client)
    response = act(surface.client, run["id"], "draft_td", "start", run["version"])
    assert response.status_code == 200, response.text
    attempt = response.json()
    assert attempt["node_key"] == "draft_td"
    assert attempt["stage_key"] == "design"
    assert attempt["attempt"] == 1
    assert attempt["status"] == "running"
    assert surface.engine.dispatcher.calls, "the node was never handed to the driver"


def test_feedback_is_more_to_do_on_the_same_attempt(surface: Surface) -> None:
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    _reviewable(surface, run["id"], "draft_td")

    response = act(
        surface.client,
        run["id"],
        "draft_td",
        "feedback",
        _version(surface, run["id"]),
        feedback="cover the migration too",
    )
    assert response.status_code == 200, response.text
    attempt = response.json()
    assert attempt["attempt"] == 1, "feedback opened a new attempt instead of reusing one"
    assert attempt["status"] == "running"


def test_a_retry_opens_the_next_attempt_and_leaves_the_last_one_standing(
    surface: Surface,
) -> None:
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    _reviewable(surface, run["id"], "draft_td")

    response = act(surface.client, run["id"], "draft_td", "retry", _version(surface, run["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["attempt"] == 2
    assert response.json()["status"] == "pending"


@pytest.mark.acceptance(
    spec="workflow", scenario="a required artifact that was never written blocks completion"
)
def test_completing_a_node_that_owes_an_artifact_is_refused(surface: Surface) -> None:
    """FR-023: the refusal IS the wait — nothing about the run moves."""
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    _reviewable(surface, run["id"], "draft_td")

    response = act(surface.client, run["id"], "draft_td", "complete", _version(surface, run["id"]))
    assert response.status_code == 400
    assert code_of(response) == "WORKFLOW_MISSING_ARTIFACT"
    assert "td.md" in response.json()["error"]["message"]
    assert node_of(detail(surface.client, run["id"]), "draft_td")["status"] == "waiting_review"


def test_the_artifact_can_be_waived_or_written(surface: Surface) -> None:
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    _reviewable(surface, run["id"], "draft_td")

    surface.engine.artifacts.add(run["id"], "draft_td", 1, "td.md")
    response = act(surface.client, run["id"], "draft_td", "complete", _version(surface, run["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def test_waive_artifacts_completes_the_node_anyway(surface: Surface) -> None:
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    _reviewable(surface, run["id"], "draft_td")

    response = act(
        surface.client,
        run["id"],
        "draft_td",
        "complete",
        _version(surface, run["id"]),
        waive_artifacts=True,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def test_a_skipped_node_can_be_restored(surface: Surface) -> None:
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    _reviewable(surface, run["id"], "draft_td")

    skipped = act(surface.client, run["id"], "draft_td", "skip", _version(surface, run["id"]))
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["status"] == "skipped"

    restored = act(surface.client, run["id"], "draft_td", "restore", _version(surface, run["id"]))
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "pending"


def test_a_failed_attempt_reports_why(surface: Surface) -> None:
    run = started_run(surface.client)
    act(surface.client, run["id"], "draft_td", "start", run["version"])
    asyncio.run(
        surface.engine.nodes.record_failure(
            run["id"], "draft_td", reason=FailureReason.AGENT_ERROR, detail="the agent gave up"
        )
    )
    node = node_of(detail(surface.client, run["id"]), "draft_td")
    assert node["latest"]["failure_reason"] == "agent_error"


# --- the refusals ------------------------------------------------------------


def test_an_action_the_node_does_not_allow_is_409(surface: Surface) -> None:
    run = started_run(surface.client)
    response = act(surface.client, run["id"], "draft_td", "complete", run["version"])
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_ILLEGAL_TRANSITION"


def test_a_node_the_template_never_declared_is_409(surface: Surface) -> None:
    run = started_run(surface.client)
    response = act(surface.client, run["id"], "invented", "start", run["version"])
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_ILLEGAL_TRANSITION"


def test_a_stale_version_is_refused_before_the_node_is_touched(surface: Surface) -> None:
    run = started_run(surface.client)
    response = act(surface.client, run["id"], "draft_td", "start", run["version"] - 1)
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_VERSION_CONFLICT"
    assert node_of(detail(surface.client, run["id"]), "draft_td")["status"] == "pending"


def test_an_action_on_an_unknown_run_is_404(surface: Surface) -> None:
    assert act(surface.client, "nope", "draft_td", "start", 1).status_code == 404


def test_an_action_outside_the_vocabulary_is_refused_at_the_boundary(surface: Surface) -> None:
    run = started_run(surface.client)
    response = act(surface.client, run["id"], "draft_td", "obliterate", run["version"])
    assert response.status_code == 422
    assert code_of(response) == "CONFIG_INVALID"


# --- ad-hoc tasks ------------------------------------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="an ad-hoc task joins a stage and carries the same context"
)
def test_an_adhoc_task_joins_the_stage_with_its_own_key(surface: Surface) -> None:
    run = started_run(surface.client)
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/tasks",
        json={
            "version": run["version"],
            "stage_key": "design",
            "name": "Check the vendor docs",
            "instructions": "Read the vendor's rate limits and note them.",
        },
    )
    assert response.status_code == 201, response.text
    attempt = response.json()
    assert attempt["node_key"] == "adhoc:check-the-vendor-docs"
    assert attempt["stage_key"] == "design"
    assert attempt["attempt"] == 1
    assert attempt["status"] == "pending"


def test_an_adhoc_task_shows_up_in_the_run_s_detail_as_a_node(surface: Surface) -> None:
    run = started_run(surface.client)
    surface.client.post(
        f"{_RUNS}/{run['id']}/tasks",
        json={
            "version": run["version"],
            "stage_key": "design",
            "name": "Check the vendor docs",
            "instructions": "Read the vendor's rate limits.",
        },
    )
    node = node_of(detail(surface.client, run["id"]), "adhoc:check-the-vendor-docs")
    assert node["name"] == "Check the vendor docs"
    assert node["adhoc"] is True
    assert node["type"] == "ai"
    assert "start" in node["allowed_actions"]


def test_two_tasks_of_the_same_name_do_not_share_a_key(surface: Surface) -> None:
    run = started_run(surface.client)
    keys = []
    for _ in range(2):
        response = surface.client.post(
            f"{_RUNS}/{run['id']}/tasks",
            json={
                "version": _version(surface, run["id"]),
                "stage_key": "design",
                "name": "Check the vendor docs",
                "instructions": "again",
            },
        )
        assert response.status_code == 201, response.text
        keys.append(response.json()["node_key"])
    assert keys == ["adhoc:check-the-vendor-docs", "adhoc:check-the-vendor-docs-2"]


def test_a_task_added_to_a_stage_that_is_not_in_the_template_is_409(surface: Surface) -> None:
    run = started_run(surface.client)
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/tasks",
        json={
            "version": run["version"],
            "stage_key": "nowhere",
            "name": "x",
            "instructions": "y",
        },
    )
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_ILLEGAL_TRANSITION"
