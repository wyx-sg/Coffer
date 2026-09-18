"""One engine, all fakes — the fixture every test in this package drives.

The template below is the smallest one that can still exercise everything the
spec asks of the engine: two stages so there is a "next node", a feedback edge
so the loop can be taken, a required artifact so completion can be blocked, and
an attempt ceiling low enough that a test can reach it in three moves.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from coffer.application.workflow.inputs_service import WorkflowInputsService
from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.domain.workflow.run import RunInput, RunSignal

from .fakes import (
    FakeApprovalRepo,
    FakeArtifactStore,
    FakeAttemptRepo,
    FakeAudit,
    FakeEventRepo,
    FakeInputStore,
    FakeMachine,
    FakeRepoMounts,
    FakeRunRepo,
    FakeTemplates,
    FakeTurnPlatform,
    RecordingDispatcher,
    clock,
)

TEMPLATE: dict[str, Any] = {
    "description": "Two stages, one edge",
    "stages": [
        {
            "key": "design",
            "name": "Tech Design",
            "nodes": [
                {
                    "key": "draft_td",
                    "name": "Draft the technical design",
                    "type": "ai",
                    "artifacts": [{"name": "td.md", "required": True}],
                    "approval": "never",
                }
            ],
        },
        {
            "key": "coding",
            "name": "Coding",
            "nodes": [
                {
                    "key": "write_code",
                    "name": "Write the code",
                    "type": "ai",
                    "approval": "never",
                    "on_failure": {"action": "retry", "times": 1},
                }
            ],
        },
    ],
    "edges": [
        {
            "from_stage": "coding",
            "to_stage": "design",
            "reason": "design_issue",
            "attempt_ceiling": 3,
        }
    ],
}


@dataclass
class Engine:
    """Both services over one set of fakes, plus the fakes themselves."""

    runs: WorkflowRunService
    nodes: WorkflowNodeService
    inputs: WorkflowInputsService
    run_repo: FakeRunRepo
    events: FakeEventRepo
    attempts: FakeAttemptRepo
    approvals: FakeApprovalRepo
    artifacts: FakeArtifactStore
    turns: FakeTurnPlatform
    audit: FakeAudit
    machine: FakeMachine
    dispatcher: RecordingDispatcher
    templates: FakeTemplates
    uploads: FakeInputStore
    repos: FakeRepoMounts

    async def create(self, template: str = "delivery", **kwargs: Any) -> Any:
        return await self.runs.create_run(
            template=template,
            title=kwargs.pop("title", "Ship the thing"),
            **kwargs,
        )

    async def started(self, **kwargs: Any) -> Any:
        """A run in ``running`` — the state most tests actually start from."""
        run = await self.create(**kwargs)
        result = await self.runs.signal(run.id, RunSignal.START, version=run.version)
        return result.run

    def types(self, run_id: str) -> list[str]:
        return self.events.types_for(run_id)

    async def latest(self, run_id: str) -> Any:
        return await self.run_repo.get_run(run_id)


def build_engine(
    templates: dict[str, dict[str, Any]] | None = None,
    *,
    machine_id: str = "machine-a",
    known_agents: tuple[str, ...] = (),
) -> Engine:
    run_repo = FakeRunRepo()
    events = FakeEventRepo()
    attempts = FakeAttemptRepo()
    approvals = FakeApprovalRepo()
    artifacts = FakeArtifactStore()
    turns = FakeTurnPlatform()
    audit = FakeAudit()
    machine = FakeMachine(machine_id)
    dispatcher = RecordingDispatcher()
    uploads = FakeInputStore()
    repo_mounts = FakeRepoMounts()
    template_source = FakeTemplates(templates or {"delivery": TEMPLATE})
    return Engine(
        runs=WorkflowRunService(
            runs=run_repo,
            events=events,
            attempts=attempts,
            approvals=approvals,
            artifacts=artifacts,
            machine=machine,
            audit=audit,
            templates=template_source,
            default_agent="claude_code",
            clock=clock,
        ),
        nodes=WorkflowNodeService(
            runs=run_repo,
            events=events,
            attempts=attempts,
            artifacts=artifacts,
            machine=machine,
            audit=audit,
            default_agent="claude_code",
            # Empty by default: "not checked here", so a test that says nothing
            # about agents drives the engine without an agent registry behind it.
            known_agents=lambda: known_agents,
            dispatcher=dispatcher,
            clock=clock,
        ),
        inputs=WorkflowInputsService(
            runs=run_repo,
            events=events,
            attempts=attempts,
            artifacts=artifacts,
            uploads=uploads,
            repos=repo_mounts,
            machine=machine,
            clock=clock,
        ),
        run_repo=run_repo,
        events=events,
        attempts=attempts,
        approvals=approvals,
        artifacts=artifacts,
        turns=turns,
        audit=audit,
        machine=machine,
        dispatcher=dispatcher,
        templates=template_source,
        uploads=uploads,
        repos=repo_mounts,
    )


@pytest.fixture
def engine() -> Engine:
    return build_engine()


def with_template(**overrides: Any) -> dict[str, Any]:
    """The default template with top-level fields replaced."""
    return {**TEMPLATE, **overrides}


def with_ceiling(ceiling: int) -> dict[str, Any]:
    """The default template with EVERY task and every route capped at
    ``ceiling``. The number is per-task now (FR-026), so a test that wants one
    limit for the whole flow has to say it on each of them."""
    return {
        **TEMPLATE,
        "stages": [
            {**stage, "nodes": [{**node, "attempt_ceiling": ceiling} for node in stage["nodes"]]}
            for stage in TEMPLATE["stages"]
        ],
        "edges": [{**edge, "attempt_ceiling": ceiling} for edge in TEMPLATE["edges"]],
    }


def inputs(*refs: RunInput) -> Sequence[RunInput]:
    return refs
