"""A workflow that is switched off starts no new runs (FR-066)."""

from __future__ import annotations

import pytest

from tests.unit.application.workflow.fakes import FakeTemplates

from .conftest import Surface, create_run

_RUNS = "/api/v1/workflow/runs"


@pytest.mark.acceptance(spec="workflow", scenario="a disabled workflow starts no new runs")
def test_creating_a_run_from_a_disabled_workflow_is_refused(surface: Surface) -> None:
    surface.engine.templates.disable("delivery")

    response = surface.client.post(
        _RUNS, json={"template_uid": FakeTemplates.uid_of("delivery"), "title": "nope"}
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_TEMPLATE_DISABLED"


def test_a_run_already_created_keeps_going_after_its_workflow_is_switched_off(
    surface: Surface,
) -> None:
    # Switching a workflow off retires it from the menu; it does not reach
    # into work already under way. The run froze its own snapshot (FR-011).
    run = create_run(surface.client, title="already going")
    surface.engine.templates.disable("delivery")

    started = surface.client.post(
        f"{_RUNS}/{run['id']}/signals", json={"version": run["version"], "signal": "start"}
    )

    assert started.status_code == 200, started.text
    assert started.json()["status"] == "running"
