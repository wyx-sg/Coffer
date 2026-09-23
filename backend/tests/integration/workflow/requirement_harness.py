"""One daemon's worth of the workflow layer, wired the way production wires it.

The requirement-scenario tests in this directory need a run to go further than
any one service can take it: a template registered through the resource
framework, a node that opens a real conversation in the run's own directory,
an agent that writes the deliverables its brief names, a gate that holds a
write, and an audit log that is a real table. This module assembles exactly
that, following ``surfaces/http/workflow_wiring.wire_workflow_kind`` step for
step, and replaces only the two things a test cannot run: the agent process
(``AgentStandIn``) and the channels a notification would go out on.

Everything else is the production object — the SQLite repositories, the file
artifact store, the context composer, the node driver, the knowledge service
over a real (per-test) knowledge root, git worktrees for a mounted repository —
so an assertion about what a run did is an assertion about the code that runs.

Every test that uses it runs under ``isolated_workflow_root`` (autouse in this
directory's conftest) and the root conftest's per-test knowledge root, so
nothing here can reach a real ``~/.coffer``.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.application.mcp.tool_class import ResourceToolClassifier
from coffer.application.resource_service import ResourceService
from coffer.application.workflow.advance_worker import driver_for
from coffer.application.workflow.approval_service import ApprovalService
from coffer.application.workflow.compaction import ConversationCompactor
from coffer.application.workflow.context_composer import ContextComposer
from coffer.application.workflow.gate import WorkflowToolGate
from coffer.application.workflow.inputs_service import WorkflowInputsService
from coffer.application.workflow.kind import KIND_WORKFLOW, make_workflow_kind
from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.application.workflow.transcripts import TranscriptMessage
from coffer.domain.chat.events import AgentEvent, TextDelta, TurnDone
from coffer.domain.resource import Kind, Resource
from coffer.domain.workflow.run import NodeAction, RunSignal
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.workflow import inputs as wf_inputs
from coffer.infrastructure.workflow.approvals_repo import WorkflowApprovalRepo
from coffer.infrastructure.workflow.attempts_repo import WorkflowAttemptRepo
from coffer.infrastructure.workflow.repository import WorkflowEventRepo, WorkflowRunRepo
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
from coffer.surfaces.http.workflow_adapters import (
    EarlierTasks,
    KnowledgeInputs,
    WorkflowAudit,
)
from coffer.surfaces.http.workflow_artifact_adapter import FileArtifactStore
from coffer.surfaces.http.workflow_wiring import GitRepoMounts

#: The two-stage template most scenarios run: a task that declared a required
#: deliverable, and one that declared none (so it owes the default report).
TEMPLATE: dict[str, Any] = {
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
                }
            ],
        },
        {
            "key": "coding",
            "name": "Coding",
            "nodes": [{"key": "write_code", "name": "Write the code", "type": "ai"}],
        },
    ],
}

TOKEN = "test-token-workflow-requirement-scenarios"
HEADERS = {"X-Coffer-Token": TOKEN, "X-Coffer-Actor": "user"}

#: One row of the brief's deliverables table:
#: ``| `td.md` | yes | `/abs/path/td.md` |``.
_DELIVERABLE_ROW = re.compile(r"^\| `[^`]+` \| (?:yes|no) \| `(?P<path>[^`]+)` \|$")


def owed_paths(opening: str) -> list[pathlib.Path]:
    """The absolute paths a task's opening message tells it to write."""
    return [
        pathlib.Path(match.group("path"))
        for line in opening.splitlines()
        if (match := _DELIVERABLE_ROW.match(line.strip()))
    ]


def agent_body(path: pathlib.Path) -> str:
    """What the stand-in agent writes into a deliverable — unique per file."""
    return f"AGENT-BODY-{path.parent.parent.name}-{path.parent.name}-{path.name}\n"


@dataclass
class AgentStandIn:
    """``TurnPlatformPort`` with an agent that does what its brief says.

    It is the one piece of the node's path that is not production code, and it
    is deliberately literal: it opens a conversation where it is told to, and
    on the turn that carries a brief it writes every deliverable at exactly the
    path the brief named. ``write_deliverables=False`` is an agent that forgot.
    """

    write_deliverables: bool = True
    conversations: list[dict[str, Any]] = field(default_factory=list)
    turns: list[tuple[str, str]] = field(default_factory=list)

    def known_agents(self) -> tuple[str, ...]:
        return ("claude_code",)

    async def create_conversation(
        self,
        *,
        agent_key: str,
        cwd: str,
        run_context: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> str:
        conversation_id = f"conv-{len(self.conversations) + 1}"
        self.conversations.append(
            {"id": conversation_id, "agent_key": agent_key, "cwd": cwd, "run_context": run_context}
        )
        return conversation_id

    async def start_turn(self, conversation_id: str, text: str) -> asyncio.Queue[AgentEvent | None]:
        self.turns.append((conversation_id, text))
        if self.write_deliverables:
            for path in owed_paths(text):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(agent_body(path), encoding="utf-8")
        queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        queue.put_nowait(TextDelta(text=f"reply {len(self.turns)}"))
        queue.put_nowait(TurnDone(prompt_tokens=None, completion_tokens=None, stop_reason="end"))
        queue.put_nowait(None)
        return queue

    async def transcript(self, conversation_id: str) -> list[TranscriptMessage]:
        return []

    async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None:
        return None

    def interrupt(self, conversation_id: str) -> None:
        return None

    def opening_of(self, conversation_id: str) -> str:
        """The first message a conversation was sent — the task's brief."""
        return next(text for conv, text in self.turns if conv == conversation_id)


class _NoSkills:
    async def instructions(self, skill_name: str) -> str | None:
        return None


class _NoSummariser:
    async def summarise(self, text: str, *, hint: str) -> str | None:
        return None


class _Quiet:
    """``NotifyPort`` with no channel bound — a supported vault."""

    async def announce(self, run_id: str, text: str) -> None:
        return None

    async def request_approval(self, run_id: str, approval_id: str, preview: str) -> None:
        return None


class _Machine:
    def current(self) -> str:
        return "machine-a"


@dataclass
class Daemon:
    """The workflow layer of one daemon, over one throwaway database."""

    kinds: dict[str, Kind]
    audit: AuditService
    resources: ResourceService
    knowledge: KnowledgeService
    runs: WorkflowRunService
    nodes: WorkflowNodeService
    inputs: WorkflowInputsService
    approvals: ApprovalService
    gate: WorkflowToolGate
    run_repo: WorkflowRunRepo
    events: WorkflowEventRepo
    attempts: WorkflowAttemptRepo
    approval_repo: WorkflowApprovalRepo
    artifacts: FileArtifactStore
    agent: AgentStandIn

    async def template(self, config: dict[str, Any], name: str = "delivery") -> Resource:
        """Register a template the way the developer does: as a resource."""
        return await self.resources.register(
            kind=KIND_WORKFLOW, name=name, config=config, actor="user"
        )

    async def started_run(self, template: Resource, title: str = "Ship it") -> Any:
        run = await self.runs.create_run(template_uid=template.uid, title=title)
        result = await self.runs.signal(run.id, RunSignal.START, version=run.version)
        return result.run

    async def start(self, run_id: str, node_key: str) -> Any:
        """Start a task at the run's current version, as the advancer does."""
        run = await self.run_repo.get_run(run_id)
        assert run is not None
        return await self.nodes.act(run_id, node_key, NodeAction.START, version=run.version)

    async def act(self, run_id: str, node_key: str, action: NodeAction, **extra: Any) -> Any:
        run = await self.run_repo.get_run(run_id)
        assert run is not None
        return await self.nodes.act(run_id, node_key, action, version=run.version, **extra)

    async def drive_to_the_end(self, run_id: str) -> list[str]:
        """Start whatever is next until nothing is; answer the order taken."""
        taken: list[str] = []
        while (position := await self.nodes.next_position(run_id)) is not None:
            taken.append(position.node_key)
            await self.start(run_id, position.node_key)
            assert len(taken) < 20, f"the run never finished: {taken}"
        return taken


async def build_daemon(tmp_path: pathlib.Path, *, agent: AgentStandIn | None = None) -> Any:
    """Wire the layer the way ``wire_workflow_kind`` does; yield it; dispose."""
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'daemon.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)

    audit = AuditService(SqlAlchemyAuditRepo(sm))
    # Exactly the kind the composition root registers: held to its scope by
    # reading the registered agent rows.
    kinds: dict[str, Kind] = {
        KIND_WORKFLOW: make_workflow_kind(agents=lambda: resources.list(kind="agent")),
        "agent": make_agent_kind(),
    }
    resources = ResourceService(kinds=kinds, repo=SqlAlchemyResourceRepo(sm), audit=audit)
    knowledge = KnowledgeService(resources=resources, audit=audit)
    kinds[KIND_KNOWLEDGE] = make_knowledge_kind(knowledge)

    run_repo = WorkflowRunRepo(sm)
    events = WorkflowEventRepo(sm)
    attempts = WorkflowAttemptRepo(sm)
    approval_repo = WorkflowApprovalRepo(sm)
    artifacts = FileArtifactStore()
    audit_port = WorkflowAudit(audit)
    stand_in = agent or AgentStandIn()
    composer = ContextComposer(
        skills=_NoSkills(),
        knowledge=KnowledgeInputs(knowledge),
        artifacts=artifacts,
        earlier=EarlierTasks(runs=run_repo, attempts=attempts),
    )
    runs = WorkflowRunService(
        runs=run_repo,
        events=events,
        attempts=attempts,
        approvals=approval_repo,
        artifacts=artifacts,
        machine=_Machine(),
        audit=audit_port,
        templates=resources,
        default_agent="claude_code",
    )
    nodes = WorkflowNodeService(
        runs=run_repo,
        events=events,
        attempts=attempts,
        artifacts=artifacts,
        machine=_Machine(),
        audit=audit_port,
        default_agent="claude_code",
    )
    nodes.bind_dispatcher(
        driver_for(
            nodes,
            platform=stand_in,
            composer=composer,
            compactor=ConversationCompactor(conversations=stand_in, summariser=_NoSummariser()),
        )
    )
    approvals = ApprovalService(
        approvals=approval_repo,
        events=events,
        audit=audit_port,
        notify=_Quiet(),
        tool_class=ResourceToolClassifier(resources),
    )
    # ``max_wait_seconds=0``: the call is held, nobody decides inside the
    # window, and it comes back refused — the approval it raised stays pending.
    gate = WorkflowToolGate(
        approvals=approvals,
        tool_class=ResourceToolClassifier(resources),
        audit=audit_port,
        max_wait_seconds=0,
    )
    inputs = WorkflowInputsService(
        runs=run_repo,
        events=events,
        attempts=attempts,
        artifacts=artifacts,
        uploads=wf_inputs,
        repos=GitRepoMounts(),
        machine=_Machine(),
    )
    daemon = Daemon(
        kinds=kinds,
        audit=audit,
        resources=resources,
        knowledge=knowledge,
        runs=runs,
        nodes=nodes,
        inputs=inputs,
        approvals=approvals,
        gate=gate,
        run_repo=run_repo,
        events=events,
        attempts=attempts,
        approval_repo=approval_repo,
        artifacts=artifacts,
        agent=stand_in,
    )
    return daemon, engine


async def http_client(daemon: Daemon) -> AsyncIterator[httpx.AsyncClient]:
    """The five workflow routers over ``daemon``, in the test's own event loop."""
    deps.set_workflow_run_service(daemon.runs)
    deps.set_workflow_node_service(daemon.nodes)
    deps.set_workflow_approval_service(daemon.approvals)
    deps.set_workflow_event_repo(daemon.events)
    deps.set_workflow_attempt_repo(daemon.attempts)
    deps.set_workflow_artifact_store(daemon.artifacts)
    deps.set_workflow_machine_id(_Machine())
    deps.set_workflow_knowledge_input(KnowledgeInputs(daemon.knowledge))
    deps.set_workflow_inputs_service(daemon.inputs)
    app = FastAPI()
    err_handlers.register(app)
    for router in (runs_router, nodes_router, inputs_router, artifacts_router, approvals_router):
        app.include_router(router)
    set_active_token(TOKEN)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://localhost", headers=HEADERS
    ) as client:
        yield client


def tree(root: pathlib.Path) -> dict[str, bytes]:
    """Every file under ``root``, by relative path, with its bytes."""
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
