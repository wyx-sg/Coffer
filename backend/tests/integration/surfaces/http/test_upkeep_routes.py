"""``POST /knowledge/collections/{uid}/curate`` refuses a concurrent pass, and
``GET /api/v1/upkeep/runs`` says what is in flight (spec knowledge FR-030).

The bug both exist for: the Tidy button's disabled state used to live in a
browser component, so leaving the page mid-pass and coming back showed an idle
button and the next click started a SECOND pass over the same files. The daemon
holds that fact now — it refuses the second start, and it can be asked what it
is rewriting so a page that mounts mid-pass renders the pass.

``client`` (a full app over a temp HOME) comes from ``conftest.py``.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.application.knowledge.service import KIND_KNOWLEDGE
from coffer.application.memory.service import KIND_MEMORY
from coffer.application.upkeep_runs import UPKEEP_RUNS

from .conftest import _create_collection


def _collection_uid(client: TestClient, name: str) -> str:
    """The uid of the collection labelled ``name``.

    The curate route is addressed by identity and the upkeep-runs key is that
    same uid — a pass takes minutes, and the two writers can only collide if
    both spell the collection the way that cannot be edited between them
    reading it (ADR resource-identity-is-an-immutable-uid).
    """
    r = client.get("/api/v1/resources", params={"kind": "knowledge", "name": name})
    assert r.status_code == 200, r.text
    return str(r.json()["resources"][0]["uid"])


@pytest.mark.acceptance(
    spec="knowledge",
    scenario=(
        "a second curation pass over the same collection is refused while the first is running"
    ),
)
def test_a_second_curation_over_the_same_collection_is_refused(client) -> None:
    """The in-flight pass is simulated by claiming the collection's key
    directly: the route is synchronous, so a genuine second request could only
    come from another thread, and what is under test is the refusal itself."""
    _create_collection(client, "shopee")
    _create_collection(client, "other")
    shopee = _collection_uid(client, "shopee")
    other_uid = _collection_uid(client, "other")

    assert UPKEEP_RUNS.claim(KIND_KNOWLEDGE, shopee) is True
    try:
        refused = client.post(f"/api/v1/knowledge/collections/{shopee}/curate")
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "UPKEEP_ALREADY_RUNNING"

        # Per collection, not vault-wide: a different collection is unaffected.
        # No internal connection is configured here, so the pass is the clean
        # no-op spec knowledge FR-029 promises rather than a model call.
        other = client.post(f"/api/v1/knowledge/collections/{other_uid}/curate")
        assert other.status_code == 200, other.text
        assert other.json()["status"] == "no_model"
        # The report names the collection by LABEL: the caller already holds the
        # uid it sent, and what a pass report adds is something to render.
        assert other.json()["collection"] == "other"
    finally:
        UPKEEP_RUNS.release(KIND_KNOWLEDGE, shopee)

    assert client.post(f"/api/v1/knowledge/collections/{shopee}/curate").status_code == 200


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="the daemon names the passes in flight",
)
def test_upkeep_runs_names_every_kind_in_flight_and_empties_out(client) -> None:
    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []

    UPKEEP_RUNS.claim(KIND_KNOWLEDGE, "shopee")
    UPKEEP_RUNS.claim(KIND_MEMORY, "coffer")
    try:
        runs = client.get("/api/v1/upkeep/runs").json()["runs"]
        assert {(r["kind"], r["name"]) for r in runs} == {
            ("knowledge", "shopee"),
            ("memory", "coffer"),
        }
        # Every run says when it started, so a surface can report duration.
        assert all(r["started_at"] for r in runs)
    finally:
        UPKEEP_RUNS.release(KIND_KNOWLEDGE, "shopee")
        UPKEEP_RUNS.release(KIND_MEMORY, "coffer")

    assert client.get("/api/v1/upkeep/runs").json()["runs"] == []


def test_upkeep_runs_requires_the_daemon_token(client) -> None:
    resp = client.get("/api/v1/upkeep/runs", headers={"X-Coffer-Token": "wrong"})
    assert resp.status_code == 401
