"""``/api/v1/workflow/approvals`` — the decisions waiting on a person (FR-044).

The route adds two answers to ``ApprovalService.decide`` and nothing else: 404
for an approval that is not there, and 409 for one that expired under the
developer's finger. Everything else — idempotence, the remembered write class,
the audit entry — is the service's, and is checked here only where the route is
what carries it.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest

from coffer.domain.workflow.run import ApprovalKind
from tests.unit.application.workflow.fakes import NOW

from .conftest import Surface, code_of, create_run, started_run

_APPROVALS = "/api/v1/workflow/approvals"

#: A payload with nesting and unicode — anything that "summarises" it mangles at
#: least one of these, and a decision on a summary is not a decision (FR-033).
VERBATIM: dict[str, Any] = {
    "project": "COF",
    "fields": {"labels": ["urgent", "运维"], "watchers": []},
}


def _ask(
    surface: Surface,
    run_id: str,
    *,
    tool_name: str | None = "jira__create_issue",
    ttl_seconds: int = 1800,
) -> dict[str, Any]:
    row = asyncio.run(
        surface.approvals.create(
            run_id=run_id,
            kind=ApprovalKind.TOOL_CALL,
            payload=VERBATIM,
            ttl_seconds=ttl_seconds,
            tool_name=tool_name,
        )
    )
    return {"id": row.id}


def _decide(surface: Surface, approval_id: str, **body: Any) -> Any:
    return surface.client.post(f"{_APPROVALS}/{approval_id}/decision", json=body)


# --- listing -----------------------------------------------------------------


def test_approvals_are_listed_across_every_run_pending_first(surface: Surface) -> None:
    first = started_run(surface.client)
    second = create_run(surface.client, title="another")
    decided = _ask(surface, first["id"])
    pending = _ask(surface, second["id"])
    assert _decide(surface, decided["id"], decision="approved").status_code == 200

    items = surface.client.get(_APPROVALS).json()["items"]
    assert [item["id"] for item in items] == [pending["id"], decided["id"]]
    assert items[0]["status"] == "pending"


def test_the_listing_can_be_narrowed_to_one_run(surface: Surface) -> None:
    first = started_run(surface.client)
    second = create_run(surface.client, title="another")
    mine = _ask(surface, first["id"])
    _ask(surface, second["id"])

    items = surface.client.get(_APPROVALS, params={"run_id": first["id"]}).json()["items"]
    assert [item["id"] for item in items] == [mine["id"]]


def test_the_listing_can_be_narrowed_to_one_status(surface: Surface) -> None:
    run = started_run(surface.client)
    approved = _ask(surface, run["id"])
    _ask(surface, run["id"], tool_name="jira__comment")
    _decide(surface, approved["id"], decision="approved")

    items = surface.client.get(_APPROVALS, params={"status": "approved"}).json()["items"]
    assert [item["id"] for item in items] == [approved["id"]]


def test_an_approval_carries_the_arguments_verbatim(surface: Surface) -> None:
    run = started_run(surface.client)
    asked = _ask(surface, run["id"])
    item = surface.client.get(_APPROVALS).json()["items"][0]
    assert item["id"] == asked["id"]
    assert item["payload"] == VERBATIM
    assert item["kind"] == "tool_call"
    assert item["tool_name"] == "jira__create_issue"


# --- deciding ----------------------------------------------------------------


def test_a_decision_is_recorded_with_who_made_it_and_where(surface: Surface) -> None:
    run = started_run(surface.client)
    asked = _ask(surface, run["id"])
    response = _decide(surface, asked["id"], decision="approved", comment="region is fine")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["comment"] == "region is fine"
    assert body["decided_by"] == "user"
    assert body["decided_surface"] == "api"
    assert body["decided_at"] is not None


@pytest.mark.acceptance(spec="workflow", scenario="an approval decision is idempotent")
def test_a_repeated_decision_returns_the_same_terminal_state(surface: Surface) -> None:
    """FR-038: idempotent, and nothing executes a second time — which here means
    no second event on the run's log."""
    run = started_run(surface.client)
    asked = _ask(surface, run["id"])
    first = _decide(surface, asked["id"], decision="approved").json()
    before = len(surface.engine.events.types_for(run["id"]))

    second = _decide(surface, asked["id"], decision="rejected").json()
    assert second["status"] == first["status"] == "approved"
    assert second["decided_at"] == first["decided_at"]
    assert len(surface.engine.events.types_for(run["id"])) == before


def test_a_rejection_keeps_the_reason_the_node_can_act_on(surface: Surface) -> None:
    run = started_run(surface.client)
    asked = _ask(surface, run["id"])
    body = _decide(surface, asked["id"], decision="rejected", comment="not this region").json()
    assert body["status"] == "rejected"
    assert body["comment"] == "not this region"


def test_a_remembered_write_class_reaches_the_tool_s_own_server(surface: Surface) -> None:
    """FR-036: the same tool is not asked about twice."""
    run = started_run(surface.client)
    asked = _ask(surface, run["id"])
    _decide(surface, asked["id"], decision="approved", remember_tool_class="write")
    assert surface.tool_class.remembered == [("jira", "create_issue", "write")]


def test_deciding_an_approval_that_is_not_there_is_404(surface: Surface) -> None:
    response = _decide(surface, "nope", decision="approved")
    assert response.status_code == 404
    assert code_of(response) == "RESOURCE_NOT_FOUND"


def test_deciding_an_expired_approval_is_409(surface: Surface) -> None:
    """The held call has already been failed (FR-037), so the click did not
    land — and rendering it as though it had would be a lie."""
    run = started_run(surface.client)
    asked = _ask(surface, run["id"], ttl_seconds=60)
    asyncio.run(surface.approvals.expire_due(now=NOW + timedelta(minutes=5)))

    response = _decide(surface, asked["id"], decision="approved")
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_ILLEGAL_TRANSITION"


def test_a_decision_only_a_person_can_make_is_refused_at_the_boundary(
    surface: Surface,
) -> None:
    """``expired`` and ``superseded`` are the system's own outcomes; a surface
    that accepted them could forge one."""
    run = started_run(surface.client)
    asked = _ask(surface, run["id"])
    response = _decide(surface, asked["id"], decision="expired")
    assert response.status_code == 422
    assert code_of(response) == "CONFIG_INVALID"


def test_aborting_a_run_leaves_no_decision_in_front_of_the_developer(
    surface: Surface,
) -> None:
    """A superseded approval is still listed — it is history — but it is not
    pending, so nothing is waiting on anyone."""
    run = started_run(surface.client)
    _ask(surface, run["id"])
    from .conftest import signal

    assert signal(surface.client, run["id"], "abort", run["version"]).status_code == 200
    items = surface.client.get(_APPROVALS).json()["items"]
    assert [item["status"] for item in items] == ["superseded"]
