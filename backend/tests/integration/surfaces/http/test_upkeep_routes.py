"""``GET /api/v1/upkeep/runs`` says what is in flight.

The bug it exists for: a button's disabled state used to live in a browser
component, so leaving the page mid-pass and coming back showed an idle button
and the next click started a SECOND pass over the same files. The daemon holds
that fact now, and can be asked what it is rewriting so a page that mounts
mid-pass renders the pass.

``client`` (a full app over a temp HOME) comes from ``conftest.py``.
"""

from __future__ import annotations

import pytest

from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UPKEEP_RUNS


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the daemon names the passes in flight",
)
def test_upkeep_runs_names_every_pass_in_flight_and_empties_out(client) -> None:
    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []

    UPKEEP_RUNS.claim(KIND_MEMORY, "shopee")
    UPKEEP_RUNS.claim(KIND_MEMORY, "coffer")
    try:
        runs = client.get("/api/v1/upkeep/runs").json()["runs"]
        assert {(r["kind"], r["name"]) for r in runs} == {
            ("memory", "shopee"),
            ("memory", "coffer"),
        }
        # Every run says when it started, so a surface can report duration.
        assert all(r["started_at"] for r in runs)
    finally:
        UPKEEP_RUNS.release(KIND_MEMORY, "shopee")
        UPKEEP_RUNS.release(KIND_MEMORY, "coffer")

    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []


def test_upkeep_runs_requires_the_daemon_token(client) -> None:
    resp = client.get("/api/v1/upkeep/runs", headers={"X-Coffer-Token": "wrong"})
    assert resp.status_code == 401
