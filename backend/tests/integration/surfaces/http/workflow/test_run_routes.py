"""``/api/v1/workflow/runs`` — create, read, signal, delete (FR-044).

The refusals matter more than the happy paths here: every one of them is a
domain error travelling through ``surfaces/http/errors.py`` to the status and
code the contract names, and that mapping is what this module is really for.
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import (
    Surface,
    act,
    code_of,
    create_run,
    detail,
    node_of,
    signal,
    started_run,
)

_RUNS = "/api/v1/workflow/runs"


def _stage_keys(payload: dict[str, Any]) -> list[str]:
    return [stage["key"] for stage in payload["stages"]]


# --- create / list / read ----------------------------------------------------


def test_a_created_run_starts_in_draft_and_is_owned_here(surface: Surface) -> None:
    run = create_run(surface.client)
    assert run["status"] == "draft"
    assert run["owned_here"] is True
    assert run["template_ref"] == "delivery"
    assert run["version"] == 1
    # A run has no conversation of its own (FR-030): every conversation in it
    # belongs to one task.
    assert "main_conversation_id" not in run


def test_creating_a_run_from_a_template_that_is_not_there_is_404(surface: Surface) -> None:
    response = surface.client.post(
        _RUNS, json={"template_uid": "wfuid-nope", "title": "x", "workdir": "/repo"}
    )
    assert response.status_code == 404
    assert code_of(response) == "RESOURCE_NOT_FOUND"


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is created from a template and a title alone"
)
def test_creating_a_run_asks_for_a_template_and_a_title_and_nothing_else(
    surface: Surface,
) -> None:
    """FR-011. The working directory is Coffer's own, made per run (FR-053) and
    reported back; the inputs are mounted afterwards (FR-050). Neither is a
    field of the creation body any more, and a client that still sends one is
    not humoured."""
    run = create_run(surface.client, workdir="/somewhere/else", inputs=[{"kind": "link"}])
    assert run["workdir"] != "/somewhere/else"
    assert run["workdir"]
    assert detail(surface.client, run["id"])["inputs"] == []


def test_mounted_inputs_show_up_in_the_run_s_detail(surface: Surface) -> None:
    """The detail reads the run's own ``inputs`` column, and the inputs routes
    write it — so what one says the other shows, without a second store."""
    run = create_run(surface.client)
    mounted = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs",
        json={"kind": "knowledge", "ref": "account-service", "label": "the service"},
    )
    assert mounted.status_code == 201, mounted.text
    assert detail(surface.client, run["id"])["inputs"] == [
        {
            "kind": "knowledge",
            "ref": "account-service",
            "label": "the service",
            "size": None,
            "path": None,
            "mount": None,
            # Only a link has one: a collection is already named by its kind.
            "provider": None,
        }
    ]


def test_the_listing_can_be_narrowed_to_one_status(surface: Surface) -> None:
    draft = create_run(surface.client, title="still drafting")
    running = started_run(surface.client)

    everything = surface.client.get(_RUNS).json()["items"]
    assert {item["id"] for item in everything} == {draft["id"], running["id"]}

    only_running = surface.client.get(_RUNS, params={"status": "running"}).json()["items"]
    assert [item["id"] for item in only_running] == [running["id"]]


def test_an_unknown_run_is_404_everywhere_it_can_be_named(surface: Surface) -> None:
    for path in ("", "/events", "/artifacts"):
        response = surface.client.get(f"{_RUNS}/nope{path}")
        assert response.status_code == 404, path
        assert code_of(response) == "RESOURCE_NOT_FOUND"


# --- the detail the web UI renders -------------------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="a template with any number of stages runs as written"
)
def test_the_detail_carries_the_template_s_stages_and_nodes(surface: Surface) -> None:
    run = create_run(surface.client)
    payload = detail(surface.client, run["id"])
    assert _stage_keys(payload) == ["design", "coding"]
    node = node_of(payload, "draft_td")
    assert node["name"] == "Draft the technical design"
    assert node["type"] == "ai"
    assert node["status"] == "pending"
    assert node["attempt"] == 0
    assert node["adhoc"] is False
    assert node["conversation_id"] is None
    assert node["latest"] is None


@pytest.mark.acceptance(
    spec="workflow", scenario="a task is its own conversation, opened from the run"
)
def test_a_node_carries_the_conversation_the_ui_opens(surface: Surface) -> None:
    """A task IS its conversation (FR-030), so the identifier the UI navigates
    to is on the node itself rather than only inside the attempt that happens to
    hold it. It is the LATEST attempt's, which is the one that counts now."""
    run = started_run(surface.client)
    started = act(surface.client, run["id"], "draft_td", "start", run["version"])
    assert started.status_code == 200, started.text
    surface.engine.attempts.rows[started.json()["id"]].conversation_id = "conv-node-1"

    node = node_of(detail(surface.client, run["id"]), "draft_td")
    assert node["conversation_id"] == "conv-node-1"
    assert node["latest"]["conversation_id"] == "conv-node-1"


def test_a_draft_run_does_not_offer_to_start_a_node(surface: Surface) -> None:
    """``node.start`` requires a running run, so offering it on a draft would be
    a button that refuses itself.

    ``skip`` stays, because that is what the transition table says a ``pending``
    node accepts and this field is the table's answer, not the surface's. Note
    that ``WorkflowNodeService.act`` refuses every non-``start`` action on a node
    with no attempt row yet ("not started"), so today's ``skip`` on a
    never-tried node is refused by the engine — a gap in the engine rather than
    in what is reported here, and pinned so it is noticed either way.
    """
    run = create_run(surface.client)
    assert node_of(detail(surface.client, run["id"]), "draft_td")["allowed_actions"] == ["skip"]


def test_a_running_run_offers_exactly_what_the_transition_table_allows(
    surface: Surface,
) -> None:
    from coffer.domain.workflow.run import NodeStatus
    from coffer.domain.workflow.template import NodeType
    from coffer.domain.workflow.transitions import allowed_node_actions

    run = started_run(surface.client)
    node = node_of(detail(surface.client, run["id"]), "draft_td")
    assert set(node["allowed_actions"]) == {
        action.value for action in allowed_node_actions(NodeStatus.PENDING, NodeType.AI)
    }


def test_a_terminal_run_offers_no_action_at_all(surface: Surface) -> None:
    run = started_run(surface.client)
    aborted = signal(surface.client, run["id"], "abort", run["version"]).json()
    assert aborted["status"] == "aborted"
    payload = detail(surface.client, run["id"])
    assert all(
        node["allowed_actions"] == [] for stage in payload["stages"] for node in stage["nodes"]
    )


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is read-only on a machine that does not own it"
)
def test_a_run_another_machine_owns_is_visible_and_offers_nothing(surface: Surface) -> None:
    run = started_run(surface.client)
    surface.engine.machine.machine_id = "machine-b"

    listed = surface.client.get(_RUNS).json()["items"][0]
    assert listed["owned_here"] is False

    payload = detail(surface.client, run["id"])
    assert payload["run"]["owned_here"] is False
    assert node_of(payload, "draft_td")["allowed_actions"] == []

    refused = signal(surface.client, run["id"], "pause", run["version"])
    assert refused.status_code == 409
    assert code_of(refused) == "WORKFLOW_NOT_THIS_MACHINE"


# --- signals -----------------------------------------------------------------


def test_the_four_signals_move_the_run(surface: Surface) -> None:
    run = started_run(surface.client)
    paused = signal(surface.client, run["id"], "pause", run["version"]).json()
    assert paused["status"] == "paused"
    resumed = signal(surface.client, run["id"], "resume", paused["version"]).json()
    assert resumed["status"] == "running"
    aborted = signal(surface.client, run["id"], "abort", resumed["version"]).json()
    assert aborted["status"] == "aborted"


@pytest.mark.acceptance(spec="workflow", scenario="a stale version is refused rather than applied")
def test_a_stale_version_is_refused_with_the_run_s_current_position(surface: Surface) -> None:
    """FR-015: refused, never merged — and the refusal hands the client what it
    needs to re-read and decide without a second round trip."""
    run = started_run(surface.client)
    response = signal(surface.client, run["id"], "pause", run["version"] - 1)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "WORKFLOW_VERSION_CONFLICT"
    assert error["details"]["current"] == run["version"]
    assert error["details"]["expected"] == run["version"] - 1
    assert error["details"]["status"] == "running"


@pytest.mark.acceptance(spec="workflow", scenario="a run reaches completed when its last node does")
def test_a_terminal_run_refuses_every_mutating_command(surface: Surface) -> None:
    run = started_run(surface.client)
    aborted = signal(surface.client, run["id"], "abort", run["version"]).json()

    again = signal(surface.client, run["id"], "resume", aborted["version"])
    assert again.status_code == 409
    assert code_of(again) == "WORKFLOW_RUN_TERMINAL"

    mounted = surface.client.post(
        f"{_RUNS}/{run['id']}/inputs", json={"kind": "link", "ref": "https://example.test"}
    )
    assert mounted.status_code == 409
    assert code_of(mounted) == "WORKFLOW_RUN_TERMINAL"


def test_an_illegal_signal_says_what_was_allowed_instead(surface: Surface) -> None:
    run = create_run(surface.client)  # draft: start or abort, never resume
    response = signal(surface.client, run["id"], "resume", run["version"])
    assert response.status_code == 409
    assert code_of(response) == "WORKFLOW_ILLEGAL_TRANSITION"


# --- the log -----------------------------------------------------------------


def test_the_event_log_is_the_run_s_record(surface: Surface) -> None:
    run = started_run(surface.client)
    items = surface.client.get(f"{_RUNS}/{run['id']}/events").json()["items"]
    assert [item["event_type"] for item in items] == ["run.created", "run.started"]
    assert [item["sequence"] for item in items] == [1, 2]
    assert items[0]["actor"] == {
        "actor_kind": "user",
        "actor_id": "user",
        "source_surface": "api",
    }


def test_the_log_can_be_read_from_a_sequence_onwards(surface: Surface) -> None:
    run = started_run(surface.client)
    items = surface.client.get(f"{_RUNS}/{run['id']}/events", params={"after_sequence": 1}).json()[
        "items"
    ]
    assert [item["event_type"] for item in items] == ["run.started"]


# --- deletion ----------------------------------------------------------------


def test_deleting_a_run_takes_its_directory_with_it(surface: Surface) -> None:
    run = create_run(surface.client)
    response = surface.client.delete(f"{_RUNS}/{run['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert surface.engine.artifacts.deleted == [run["id"]]
    assert surface.client.get(f"{_RUNS}/{run['id']}").status_code == 404


def test_deleting_an_unknown_run_is_404(surface: Surface) -> None:
    assert surface.client.delete(f"{_RUNS}/nope").status_code == 404


# --- labels ------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="a run is renamed after the work has shown what it is"
)
def test_a_run_is_renamed_after_the_work_has_shown_what_it_is(surface: Surface) -> None:
    """FR-070: the title is a label, so correcting it moves nothing else."""
    run = create_run(surface.client)
    surface.client.post(f"{_RUNS}/{run['id']}/signals", json={"signal": "start", "version": 1})
    before = surface.client.get(f"{_RUNS}/{run['id']}").json()["run"]
    events_before = surface.client.get(f"{_RUNS}/{run['id']}/events").json()["items"]

    response = surface.client.patch(
        f"{_RUNS}/{run['id']}",
        json={"title": "Ship the collections page", "description": "One repository, design first"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Ship the collections page"
    assert body["description"] == "One repository, design first"
    # Everything the event log owns is exactly as it was, including the version:
    # a label edit is outside the lock cycle because it moves the run nowhere.
    assert body["status"] == before["status"]
    assert body["current_stage_key"] == before["current_stage_key"]
    assert body["current_node_key"] == before["current_node_key"]
    assert body["version"] == before["version"]
    events_after = surface.client.get(f"{_RUNS}/{run['id']}/events").json()["items"]
    assert len(events_after) == len(events_before)


def test_a_run_may_not_be_called_nothing(surface: Surface) -> None:
    run = create_run(surface.client)
    response = surface.client.patch(f"{_RUNS}/{run['id']}", json={"title": "   "})
    assert response.status_code == 422
    assert surface.client.get(f"{_RUNS}/{run['id']}").json()["run"]["title"] == run["title"]


def test_relabelling_a_run_another_machine_owns_is_refused(surface: Surface) -> None:
    """FR-012: read-only here means read-only, labels included — two machines
    disagreeing about what one run is called has nothing to reconcile them."""
    run = create_run(surface.client)
    surface.engine.machine.machine_id = "somewhere-else"
    response = surface.client.patch(f"{_RUNS}/{run['id']}", json={"title": "mine now"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_THIS_MACHINE"


def test_retitling_a_run_leaves_the_description_it_was_not_given(surface: Surface) -> None:
    """FR-070: a body that says nothing about the description says nothing —
    it does not say "empty". `--title` on its own must not erase the words
    someone wrote about this delivery a week ago."""
    run = create_run(surface.client)
    first = surface.client.patch(
        f"{_RUNS}/{run['id']}", json={"title": "a", "description": "the words"}
    )
    assert first.status_code == 200, first.text

    second = surface.client.patch(f"{_RUNS}/{run['id']}", json={"title": "b"})
    assert second.status_code == 200, second.text
    got = surface.client.get(f"{_RUNS}/{run['id']}")
    assert got.status_code == 200, got.text
    assert got.json()["run"]["description"] == "the words"

    # An explicit null is the other answer, and still available.
    surface.client.patch(f"{_RUNS}/{run['id']}", json={"title": "b", "description": None})
    assert surface.client.get(f"{_RUNS}/{run['id']}").json()["run"]["description"] is None
