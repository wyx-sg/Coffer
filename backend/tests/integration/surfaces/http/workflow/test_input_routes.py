"""``/api/v1/workflow/runs/{run_id}/inputs`` — what a run reads (FR-032, FR-050).

Four routes over one list, and the thing worth proving about them is that they
work on a run that is already going: an input is the developer's at any point in
the run's life, not only at creation. The refusals matter for the same reason
they do next door — a run another machine owns, and a run that has ended — and
they travel the same way, through ``surfaces/http/errors.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import Surface, code_of, create_run, signal, started_run

_RUNS = "/api/v1/workflow/runs"


def _inputs(surface: Surface, run_id: str) -> list[dict[str, Any]]:
    response = surface.client.get(f"{_RUNS}/{run_id}/inputs")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# --- listing -----------------------------------------------------------------


def test_a_run_with_nothing_mounted_says_so(surface: Surface) -> None:
    run = create_run(surface.client)
    assert _inputs(surface, run["id"]) == []


def test_listing_the_inputs_of_an_unknown_run_is_404(surface: Surface) -> None:
    response = surface.client.get(f"{_RUNS}/nope/inputs")
    assert response.status_code == 404
    assert code_of(response) == "RESOURCE_NOT_FOUND"


# --- adding and removing while the run is going ------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="an input can be added and removed while the run is going"
)
def test_a_link_can_be_mounted_on_a_running_run(surface: Surface) -> None:
    """FR-050. No ``version`` is sent, because mounting an input is not a
    transition — the run did not move, it was given something to read."""
    run = started_run(surface.client)
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs",
        json={"kind": "link", "ref": "https://wiki.test/api", "label": "the API"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["items"] == [
        {
            "kind": "link",
            "ref": "https://wiki.test/api",
            "label": "the API",
            "size": None,
            # A link is not checked out anywhere and is not a repo.
            "path": None,
            "mount": None,
            # `wiki.` is how a self-hosted Confluence is named, so this one is
            # recognised — DERIVED on read (FR-065), never sent by the client.
            "provider": "confluence",
        }
    ]
    assert _inputs(surface, run["id"]) == response.json()["items"]


@pytest.mark.acceptance(
    spec="workflow", scenario="an input can be added and removed while the run is going"
)
def test_an_input_can_be_unmounted_while_the_run_is_going(surface: Surface) -> None:
    run = started_run(surface.client)
    surface.client.post(
        f"{_RUNS}/{run['id']}/inputs", json={"kind": "knowledge", "ref": "account-service"}
    )
    surface.client.post(
        f"{_RUNS}/{run['id']}/inputs", json={"kind": "link", "ref": "https://x.test"}
    )

    removed = surface.client.delete(f"{_RUNS}/{run['id']}/inputs/account-service")
    assert removed.status_code == 200, removed.text
    assert [item["ref"] for item in removed.json()["items"]] == ["https://x.test"]


def test_a_link_is_removable_by_the_url_it_was_mounted_under(surface: Surface) -> None:
    """A link's ``ref`` is a URL, so the path parameter has to survive one.

    The ASGI server percent-decodes the path before the router sees it, which is
    why the route uses a ``path`` converter: a dutifully encoded ``%2F`` arrives
    as a slash, and a plain segment would 404 on the very refs this kind mounts
    most.
    """
    run = started_run(surface.client)
    surface.client.post(
        f"{_RUNS}/{run['id']}/inputs", json={"kind": "link", "ref": "https://wiki.test/a/b"}
    )
    removed = surface.client.delete(f"{_RUNS}/{run['id']}/inputs/https%3A%2F%2Fwiki.test%2Fa%2Fb")
    assert removed.status_code == 200, removed.text
    assert removed.json()["items"] == []


def test_mounting_on_an_unknown_run_is_404(surface: Surface) -> None:
    response = surface.client.post(
        f"{_RUNS}/nope/inputs", json={"kind": "link", "ref": "https://x"}
    )
    assert response.status_code == 404
    assert code_of(response) == "RESOURCE_NOT_FOUND"


def test_an_aborted_run_reads_nothing_new(surface: Surface) -> None:
    run = started_run(surface.client)
    signal(surface.client, run["id"], "abort", run["version"])
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs", json={"kind": "link", "ref": "https://x.test"}
    )
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_RUN_TERMINAL"


def test_unmounting_something_that_is_not_mounted_says_so(surface: Surface) -> None:
    run = started_run(surface.client)
    response = surface.client.delete(f"{_RUNS}/{run['id']}/inputs/never-mounted")
    assert response.status_code == 404, response.text
    assert code_of(response) == "WORKFLOW_INPUT_NOT_FOUND"


def test_a_run_another_machine_owns_refuses_a_mount(surface: Surface) -> None:
    run = create_run(surface.client)
    surface.engine.machine.machine_id = "machine-b"
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs", json={"kind": "link", "ref": "https://x.test"}
    )
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_NOT_THIS_MACHINE"


# --- the upload --------------------------------------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="an uploaded file becomes an input the nodes can read"
)
def test_an_uploaded_file_is_mounted_as_an_input(surface: Surface) -> None:
    """FR-051. The bytes reach the store whole and come back described — the
    route asserts nothing about where they landed, which is the point of the
    seam."""
    run = started_run(surface.client)
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs/uploads",
        files={"file": ("brief.md", b"# the brief\n")},
        data={"label": "the brief"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["items"] == [
        {
            "kind": "file",
            "ref": "brief.md",
            "label": "the brief",
            "size": 12,
            "path": "/runs/" + run["id"] + "/inputs/brief.md",
            "mount": None,
            # Only a link has one: a file is already named by its kind.
            "provider": None,
        }
    ]
    assert surface.engine.uploads.files[(run["id"], "brief.md")] == b"# the brief\n"


def test_an_upload_without_a_label_is_still_mounted(surface: Surface) -> None:
    run = started_run(surface.client)
    response = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs/uploads",
        files={"file": ("notes.txt", b"hello")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["label"] is None


def test_an_upload_to_an_unknown_run_is_404(surface: Surface) -> None:
    response = surface.client.post(f"{_RUNS}/nope/inputs/uploads", files={"file": ("x.txt", b"x")})
    assert response.status_code == 404
    assert code_of(response) == "RESOURCE_NOT_FOUND"
