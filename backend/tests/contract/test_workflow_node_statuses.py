"""spec workflow "Keep a node to seven statuses", read off every place that
holds the list.

The engine holds it as ``domain.workflow.run.NodeStatus``. The API reports it
twice over: the contract (``openspec/specs/workflow/contracts/
api.openapi.yaml``) narrows ``NodeOut.status`` and ``NodeAttemptOut.status``
with an ``enum``, and the served app types those same fields as a plain string
whose values come from the enum. So the check is three-sided — the domain's
seven, the contract's seven, and the served schema carrying both fields — and
the literal list is written out here rather than derived, because a list
derived from the enum could not notice the enum growing an eighth.

What the API actually reports over a real run is asserted beside the other
end-to-end scenarios, in ``tests/integration/workflow/
test_requirement_scenarios.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from coffer.domain.workflow.run import NodeStatus
from coffer.main import app

_CONTRACT = (
    Path(__file__).resolve().parents[3] / "openspec/specs/workflow/contracts/api.openapi.yaml"
)

SEVEN = [
    "pending",
    "running",
    "waiting_review",
    "waiting_approval",
    "completed",
    "skipped",
    "failed",
]


@pytest.mark.acceptance(spec="workflow", scenario="a node is only ever in one of seven statuses")
def test_the_engine_and_the_api_list_exactly_the_seven_node_statuses() -> None:
    # As the engine holds them.
    assert [status.value for status in NodeStatus] == SEVEN

    # As the contract says the API reports them.
    schemas = yaml.safe_load(_CONTRACT.read_text())["components"]["schemas"]
    for component in ("NodeOut", "NodeAttemptOut"):
        declared: list[Any] = schemas[component]["properties"]["status"]["enum"]
        assert declared == SEVEN, component

    # And the served app reports both fields, required, as that vocabulary's
    # carrier (a string: the values are the enum's, see the module docstring).
    served = app.openapi()["components"]["schemas"]
    for component in ("NodeOut", "NodeAttemptOut"):
        status = served[component]["properties"]["status"]
        assert status["type"] == "string", component
        assert set(status.get("enum", SEVEN)) == set(SEVEN), component
        assert "status" in served[component]["required"], component
