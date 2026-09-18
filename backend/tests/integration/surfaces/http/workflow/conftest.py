"""The workflow HTTP surface over the engine's own in-memory fakes.

The five routers are mounted on a bare app with the app-wide error handlers, and
the composition root's ``set_*`` calls are made here with the real services from
``tests.unit.application.workflow.conftest.build_engine`` — real
``WorkflowRunService``, ``WorkflowNodeService``, ``WorkflowInputsService`` and
``ApprovalService`` over fake repositories. That is the point of this tier: the
guards a route answers ``409`` for (a stale version, a terminal run, a run this
machine does not own) are the engine's real ones, so these tests prove the
mapping rather than a fake's impression of it.

Mounting the routers rather than booting ``create_app()`` is deliberate: the
production wiring of this kind is being written at the composition root, and a
surface test that waited for it would be testing the wiring, not the surface.
The neighbouring chat suite takes the same shape for the same reason.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from coffer.application.workflow.approval_service import ApprovalService
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.workflow import (
    approvals_router,
    artifacts_router,
    inputs_router,
    nodes_router,
    runs_router,
)
from coffer.surfaces.http.workflow import dependencies as deps
from tests.unit.application.workflow.conftest import TEMPLATE, Engine, build_engine
from tests.unit.application.workflow.fakes import FakeTemplates, clock

_TOKEN = "test-token-workflow-routes"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}


class FakeKnowledgeInput:
    """The knowledge seam: a collection is a name and a destination path."""

    def __init__(self) -> None:
        self.created: list[str] = []

    async def describe(self, collection: str) -> str | None:
        return None

    async def create_collection(self, name: str) -> str:
        self.created.append(name)
        return f"/fake/knowledge/{name}"


class FakeNotify:
    def __init__(self) -> None:
        self.announced: list[tuple[str, str]] = []
        self.requested: list[tuple[str, str, str]] = []

    async def announce(self, run_id: str, text: str) -> None:
        self.announced.append((run_id, text))

    async def request_approval(self, run_id: str, approval_id: str, preview: str) -> None:
        self.requested.append((run_id, approval_id, preview))


class FakeToolClass:
    def __init__(self) -> None:
        self.remembered: list[tuple[str, str, str]] = []

    async def classify(self, server_name: str, tool: str) -> str | None:
        return None

    async def remember(self, server_name: str, tool: str, write_class: str) -> None:
        self.remembered.append((server_name, tool, write_class))


class Surface:
    """Everything a test needs: the client, the engine behind it, and the
    stand-ins the routes were handed."""

    def __init__(
        self,
        client: TestClient,
        engine: Engine,
        *,
        approvals: ApprovalService,
        knowledge: FakeKnowledgeInput,
        notify: FakeNotify,
        tool_class: FakeToolClass,
    ) -> None:
        self.client = client
        self.engine = engine
        self.approvals = approvals
        self.knowledge = knowledge
        self.notify = notify
        self.tool_class = tool_class


@pytest.fixture
def surface() -> Iterator[Surface]:
    engine = build_engine()
    notify = FakeNotify()
    tool_class = FakeToolClass()
    approvals = ApprovalService(
        approvals=engine.approvals,
        events=engine.events,
        audit=engine.audit,
        notify=notify,
        tool_class=tool_class,
        clock=clock,
    )
    knowledge = FakeKnowledgeInput()

    deps.set_workflow_run_service(engine.runs)
    deps.set_workflow_node_service(engine.nodes)
    deps.set_workflow_approval_service(approvals)
    deps.set_workflow_event_repo(engine.events)
    deps.set_workflow_attempt_repo(engine.attempts)
    deps.set_workflow_artifact_store(engine.artifacts)
    deps.set_workflow_machine_id(engine.machine)
    deps.set_workflow_knowledge_input(knowledge)
    deps.set_workflow_inputs_service(engine.inputs)

    app = FastAPI()
    err_handlers.register(app)
    for router in (runs_router, nodes_router, inputs_router, artifacts_router, approvals_router):
        app.include_router(router)
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as client:
        yield Surface(
            client,
            engine,
            approvals=approvals,
            knowledge=knowledge,
            notify=notify,
            tool_class=tool_class,
        )


# --- the moves every test makes ---------------------------------------------


def create_run(client: TestClient, **body: Any) -> dict[str, Any]:
    # The route takes the template's uid; the fake registry derives one from
    # the name these tests are written in terms of.
    payload = {
        "template_uid": FakeTemplates.uid_of("delivery"),
        "title": "Ship it",
        **body,
    }
    response = client.post("/api/v1/workflow/runs", json=payload)
    assert response.status_code == 201, response.text
    run: dict[str, Any] = response.json()
    return run


def signal(client: TestClient, run_id: str, name: str, version: int) -> Any:
    return client.post(
        f"/api/v1/workflow/runs/{run_id}/signals",
        json={"version": version, "signal": name},
    )


def started_run(client: TestClient) -> dict[str, Any]:
    """A run in ``running`` — where most of the surface's interest begins."""
    run = create_run(client)
    response = signal(client, run["id"], "start", run["version"])
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


def detail(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/workflow/runs/{run_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def node_of(payload: dict[str, Any], node_key: str) -> dict[str, Any]:
    for stage in payload["stages"]:
        for node in stage["nodes"]:
            if node["key"] == node_key:
                return node
    raise AssertionError(f"{node_key} is not in the run's detail")


def act(
    client: TestClient, run_id: str, node_key: str, action: str, version: int, **extra: Any
) -> Any:
    return client.post(
        f"/api/v1/workflow/runs/{run_id}/nodes/{node_key}/actions",
        json={"version": version, "action": action, **extra},
    )


def code_of(response: Any) -> str:
    body: dict[str, Any] = response.json()
    return str(body["error"]["code"])


__all__ = [
    "TEMPLATE",
    "Surface",
    "act",
    "code_of",
    "create_run",
    "detail",
    "node_of",
    "signal",
    "started_run",
    "surface",
]
