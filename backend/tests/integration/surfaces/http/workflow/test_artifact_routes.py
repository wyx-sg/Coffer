"""``…/artifacts`` and ``…/promotion`` — what a run produced (FR-031, FR-043)."""

from __future__ import annotations

import pytest

from .conftest import Surface, create_run, started_run

_RUNS = "/api/v1/workflow/runs"


def test_an_empty_run_still_answers_with_a_catalogue(surface: Surface) -> None:
    run = create_run(surface.client)
    body = surface.client.get(f"{_RUNS}/{run['id']}/artifacts").json()
    assert body["items"] == []
    assert "No artifacts yet." in body["catalogue"]


def test_every_artifact_names_the_node_and_attempt_that_produced_it(
    surface: Surface,
) -> None:
    run = started_run(surface.client)
    surface.engine.artifacts.add(run["id"], "draft_td", 1, "td.md")
    surface.engine.artifacts.add(run["id"], "draft_td", 2, "td.md")

    body = surface.client.get(f"{_RUNS}/{run['id']}/artifacts").json()
    assert [(item["node_key"], item["attempt"]) for item in body["items"]] == [
        ("draft_td", 1),
        ("draft_td", 2),
    ]
    assert body["items"][0]["path"] == "draft_td/1/td.md"
    assert "draft_td" in body["catalogue"]


def test_the_catalogue_is_regenerated_from_the_directory(surface: Surface) -> None:
    """FR-031: generated, never hand-maintained — so whatever is on disk wins,
    and the file is rewritten as it is read."""
    run = started_run(surface.client)
    surface.engine.artifacts.catalogues[run["id"]] = "# stale nonsense\n"
    surface.engine.artifacts.add(run["id"], "draft_td", 1, "td.md")

    body = surface.client.get(f"{_RUNS}/{run['id']}/artifacts").json()
    assert "stale nonsense" not in body["catalogue"]
    assert surface.engine.artifacts.catalogues[run["id"]] == body["catalogue"]


@pytest.mark.acceptance(spec="workflow", scenario="a run's artifacts become a knowledge collection")
def test_promotion_copies_into_a_collection_and_leaves_the_run_alone(
    surface: Surface,
) -> None:
    run = started_run(surface.client)
    surface.engine.artifacts.add(run["id"], "draft_td", 1, "td.md")

    response = surface.client.post(
        f"{_RUNS}/{run['id']}/promotion", json={"collection": "delivery-output"}
    )
    assert response.status_code == 201, response.text
    assert response.json() == {"collection": "delivery-output", "copied": 1}
    assert surface.knowledge.created == ["delivery-output"]
    assert surface.engine.artifacts.deleted == []
    assert surface.client.get(f"{_RUNS}/{run['id']}/artifacts").json()["items"] != []


def test_a_finished_run_is_exactly_the_one_worth_promoting(surface: Surface) -> None:
    """Promotion is not a mutating command on the run, so a completed or
    aborted run is not refused it (FR-043)."""
    run = started_run(surface.client)
    surface.engine.artifacts.add(run["id"], "draft_td", 1, "td.md")
    from .conftest import signal

    assert signal(surface.client, run["id"], "abort", run["version"]).status_code == 200
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/promotion", json={"collection": "delivery-output"}
    )
    assert response.status_code == 201, response.text


def test_promoting_an_unknown_run_is_404(surface: Surface) -> None:
    response = surface.client.post(f"{_RUNS}/nope/promotion", json={"collection": "x"})
    assert response.status_code == 404


@pytest.mark.acceptance(
    spec="workflow", scenario="a delivery that has produced nothing yet is still worth keeping"
)
def test_a_run_with_nothing_produced_still_promotes_what_it_was_given(
    surface: Surface,
) -> None:
    """FR-043: a delivery that has so far only been given a brief is one whose
    brief is worth keeping — the button must not wait for an agent."""
    run = started_run(surface.client)
    surface.client.post(
        f"{_RUNS}/{run['id']}/inputs/uploads", files={"file": ("prd.pdf", b"the brief")}
    )
    surface.client.post(
        f"{_RUNS}/{run['id']}/inputs/notes", json={"title": "ops", "text": "# what ops said"}
    )
    surface.client.post(
        f"{_RUNS}/{run['id']}/inputs",
        json={"kind": "link", "ref": "https://mycorp.atlassian.net/wiki/x", "label": "the TD"},
    )

    response = surface.client.post(
        f"{_RUNS}/{run['id']}/promotion", json={"collection": "retry-fix"}
    )

    assert response.status_code == 201, response.text
    # The link is not copied — it is somebody else's page — so what is kept is
    # the fact that this delivery read it.
    _run_id, _destination, references = surface.engine.artifacts.promoted[-1]
    assert references is not None
    assert "https://mycorp.atlassian.net/wiki/x" in references
    assert "(confluence) — the TD" in references
    # And the uploads are still the run's.
    refs = [i["ref"] for i in surface.client.get(f"{_RUNS}/{run['id']}/inputs").json()["items"]]
    assert "prd.pdf" in refs and "ops.md" in refs
