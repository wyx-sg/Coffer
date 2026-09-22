"""Wiring for the one ``workflow`` kind (spec workflow).

Where this sits in the lifespan is the part worth reading. Workflow is wired
**after** the chat platform and the channel kind, because a node's work is a
conversation and an approval reaches the developer through a channel — both are
ports this module fills. That is also why it is not inside
``kind_wiring.wire_resource_kinds``, which runs before chat exists.

Two things cross that ordering, and each is handled rather than worked around:

* The **gate**. The gateway's session factory is built while the MCP kind is
  wired, long before the gate exists. The factory is handed a
  ``LateBoundToolGate`` there and this module binds the real gate into it. Until
  it does, the holder answers "dispatch" — the same answer as no gate at all.
* The **run identity a node's agent carries**. It has to be in the environment
  when the agent process starts, so the lookup is passed *into* ``wire_chat``.
  It reads the attempt row rather than a map built at conversation time, which
  is what keeps a turn started after a daemon restart gated (FR-035).

Nothing here can fail to build. With no channel bound the notifier delivers to
the run's main thread alone; with no template registered the kind is still
registered and the surfaces still answer.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.engine.resolve import resolve_internal_connection
from coffer.application.mcp.tool_class import ResourceToolClassifier
from coffer.application.workflow.advance_worker import AdvanceWorker, driver_for
from coffer.application.workflow.approval_service import ApprovalService
from coffer.application.workflow.commands import ENGINE_ACTOR
from coffer.application.workflow.compaction import ConversationCompactor
from coffer.application.workflow.context_composer import ContextComposer
from coffer.application.workflow.gate import WorkflowToolGate
from coffer.application.workflow.inputs_service import WorkflowInputsService
from coffer.application.workflow.kind import KIND_WORKFLOW, make_workflow_kind
from coffer.application.workflow.node_service import WorkflowNodeService
from coffer.application.workflow.run_service import WorkflowRunService
from coffer.domain.workflow.run import NodeAction
from coffer.infrastructure.chat.persistence import MessageRepo
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.workflow import inputs as wf_inputs
from coffer.infrastructure.workflow import repos as wf_repos
from coffer.infrastructure.workflow.approvals_repo import WorkflowApprovalRepo
from coffer.infrastructure.workflow.attempts_repo import WorkflowAttemptRepo
from coffer.infrastructure.workflow.repository import WorkflowEventRepo, WorkflowRunRepo
from coffer.surfaces.http.channel_routes import get_channel_service
from coffer.surfaces.http.engine_config_composition import read_internal_engine_model
from coffer.surfaces.http.workflow.dependencies import (
    set_workflow_approval_service,
    set_workflow_artifact_store,
    set_workflow_attempt_repo,
    set_workflow_event_repo,
    set_workflow_inputs_service,
    set_workflow_knowledge_input,
    set_workflow_machine_id,
    set_workflow_node_service,
    set_workflow_run_service,
)
from coffer.surfaces.http.workflow_adapters import (
    ChatTurnPlatform,
    EarlierTasks,
    FileArtifactStore,
    KnowledgeInputs,
    SkillText,
    ThisMachine,
    WorkflowAudit,
    WorkflowNotify,
)
from coffer.surfaces.http.workflow_summariser import LlmSummariser

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from coffer.application.audit_service import AuditService
    from coffer.application.knowledge.service import KnowledgeService
    from coffer.application.mcp.gateway_gate import LateBoundToolGate
    from coffer.application.provider.service import ProviderService
    from coffer.application.resource_service import ResourceService
    from coffer.application.skill.service import SkillService
    from coffer.domain.provider.config import ResolvedConnection
    from coffer.surfaces.http.chat_wiring import ChatWiring

logger = logging.getLogger(__name__)

#: The agent a run's nodes use when neither the run nor the node names one.
#:
#: This is the turn platform's PROVIDER key (``AgentProvider.agent_key``), not
#: an agent resource's name — the two look alike and are not the same thing, and
#: the resource name is what a person types while the provider key is what the
#: registry is indexed by. Getting it wrong fails at the first node with
#: ``UNKNOWN_AGENT`` rather than at startup, which is exactly how it was found.
DEFAULT_RUN_AGENT = "claude_code"


class InternalModel:
    """``ModelSelectorPort`` over ``ProviderService`` — Coffer's internal-default
    connection, resolved per call so one configured after startup is picked up.

    Re-derived here rather than imported from another kind's wiring module,
    whose own equivalent is private: this project's convention is to duplicate
    a few lines rather than let two kinds' wiring modules import each other.
    The PAIRING itself is not duplicated — `engine.resolve` owns it.
    """

    def __init__(self, provider: ProviderService) -> None:
        self._provider = provider

    async def get_default(self) -> ResolvedConnection | None:
        # The model and the connection are paired by `engine.resolve`: the
        # engine decides WHETHER there is one to run on, the provider kind
        # says WHICH. Reading the model per call rather than capturing it
        # means a model chosen after wiring takes effect at once.
        return await resolve_internal_connection(
            read_model=read_internal_engine_model,
            connections=self._provider,
        )


class GitRepoMounts:
    """``RepoMountPort`` over ``infrastructure.workflow.repos``.

    A class rather than the module itself because the module's functions are
    named for what they do to a repo (``mount_repo``) and the port is named for
    what it is to the service (``mount``). Renaming either to make the module
    satisfy the Protocol structurally would make one of the two read worse.
    """

    async def mount(
        self, run_id: str, source: str, *, taken: frozenset[str] = frozenset()
    ) -> wf_repos.MountedRepo:
        return await wf_repos.mount_repo(run_id, source, taken=taken)

    async def unmount(self, run_id: str, *, source: str, path: str, mount: str) -> None:
        await wf_repos.unmount_repo(run_id, source=source, path=path, mount=mount)


@dataclass(frozen=True)
class WorkflowWiring:
    """What the lifespan needs back: the services the surfaces read, and the
    worker it has to stop."""

    run_service: WorkflowRunService
    node_service: WorkflowNodeService
    approval_service: ApprovalService
    artifacts: FileArtifactStore
    attempts: WorkflowAttemptRepo
    worker: AdvanceWorker


def build_attempt_repo(sm: async_sessionmaker[AsyncSession]) -> WorkflowAttemptRepo:
    """The attempt repository, built early.

    It is needed before the rest of this module runs, because ``wire_chat``
    takes the conversation-environment lookup that reads it. Splitting the
    construction out is cheaper than late-binding the lookup, and the repo is
    stateless beyond its session maker.
    """
    return WorkflowAttemptRepo(sm)


def wire_workflow_kind(
    app: FastAPI,
    *,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    chat: ChatWiring,
    knowledge: KnowledgeService,
    skills: SkillService,
    attempts: WorkflowAttemptRepo,
    gate_holder: LateBoundToolGate,
    provider: ProviderService,
    credential_resolver: Callable[[str], str],
) -> WorkflowWiring:
    # 1. Persistence and the run directory.
    runs = WorkflowRunRepo(sm)
    events = WorkflowEventRepo(sm)
    approvals_repo = WorkflowApprovalRepo(sm)
    artifacts = FileArtifactStore()

    # 2. The adapters that bridge to the other kinds (workflow_adapters).
    platform = ChatTurnPlatform(
        chat=chat.chat_service,
        orchestrator=chat.orchestrator,
        messages=MessageRepo(sm),
        registry=chat.registry,
    )
    summariser = LlmSummariser(
        models=InternalModel(provider),
        completion=LangchainLlmCompletion(),
        credential_resolver=credential_resolver,
    )
    audit_port = WorkflowAudit(audit)
    notify = WorkflowNotify(
        chat=chat.chat_service,
        channels=get_channel_service(),
        resources=resource_svc,
        runs=runs,
    )
    composer = ContextComposer(
        skills=SkillText(skills),
        knowledge=KnowledgeInputs(knowledge),
        artifacts=artifacts,
        earlier=EarlierTasks(runs=runs, attempts=attempts),
    )

    # 3. The engine.
    run_service = WorkflowRunService(
        runs=runs,
        events=events,
        attempts=attempts,
        approvals=approvals_repo,
        artifacts=artifacts,
        machine=ThisMachine(),
        audit=audit_port,
        templates=resource_svc,
        default_agent=DEFAULT_RUN_AGENT,
    )
    node_service = WorkflowNodeService(
        runs=runs,
        events=events,
        attempts=attempts,
        artifacts=artifacts,
        machine=ThisMachine(),
        audit=audit_port,
        default_agent=DEFAULT_RUN_AGENT,
        known_agents=platform.known_agents,
    )
    # The driver reports every outcome to the node service, and the node
    # service dispatches through the driver. ``driver_for`` wires all three
    # callbacks at once so two of them cannot land on different objects.
    driver = driver_for(
        node_service,
        platform=platform,
        composer=composer,
        compactor=ConversationCompactor(conversations=platform, summariser=summariser),
    )
    node_service.bind_dispatcher(driver)

    approval_service = ApprovalService(
        approvals=approvals_repo,
        events=events,
        audit=audit_port,
        notify=notify,
        tool_class=ResourceToolClassifier(resource_svc),
    )

    inputs_service = WorkflowInputsService(
        runs=runs,
        events=events,
        attempts=attempts,
        artifacts=artifacts,
        uploads=wf_inputs,
        repos=GitRepoMounts(),
        machine=ThisMachine(),
    )

    # 4. The gate, bound into the holder the gateway was given earlier.
    gate_holder.bind(
        WorkflowToolGate(
            approvals=approval_service,
            tool_class=ResourceToolClassifier(resource_svc),
            audit=audit_port,
        )
    )

    # 5. The kind itself. Scope is read inverted — the agents a template may
    #    drive — so the allowed set is every registered agent (FR-007).
    app.state.kinds[KIND_WORKFLOW] = make_workflow_kind()

    # 6. The advancer. It only ever looks at runs this machine owns, because
    #    ``next_position`` refuses a run owned elsewhere (FR-012).
    async def _due_runs() -> list[str]:
        return [run.id for run in await run_service.list_runs(status="running")]

    async def _advance(run_id: str) -> None:
        position = await node_service.next_position(run_id)
        if position is None:
            return
        run = await run_service.get_run(run_id)
        # The engine's own move, logged as the engine's rather than as the
        # developer's, and carrying the version it just read — the advancer is
        # as subject to the optimistic lock as anyone else (FR-015).
        await node_service.act(
            run_id,
            position.node_key,
            NodeAction.START,
            version=run.version,
            actor=ENGINE_ACTOR,
        )

    worker = AdvanceWorker(due_runs=_due_runs, advance_run=_advance)

    # 7. The HTTP surface's dependency providers. The routes hold no state of
    #    their own; this is the whole of what they can reach.
    set_workflow_run_service(run_service)
    set_workflow_node_service(node_service)
    set_workflow_approval_service(approval_service)
    set_workflow_event_repo(events)
    set_workflow_attempt_repo(attempts)
    set_workflow_artifact_store(artifacts)
    set_workflow_machine_id(ThisMachine())
    set_workflow_knowledge_input(KnowledgeInputs(knowledge))
    set_workflow_inputs_service(inputs_service)

    return WorkflowWiring(
        run_service=run_service,
        node_service=node_service,
        approval_service=approval_service,
        artifacts=artifacts,
        attempts=attempts,
        worker=worker,
    )


async def start_workflow(
    app: FastAPI,
    *,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    chat: ChatWiring,
    knowledge: KnowledgeService,
    skills: SkillService,
    attempts: WorkflowAttemptRepo,
    gate_holder: LateBoundToolGate,
    provider: ProviderService,
    credential_resolver: Callable[[str], str],
) -> WorkflowWiring:
    """Wire the kind, rebuild what a previous run left behind, then advance.

    The order is the point and is why this is one function rather than three
    calls in the lifespan: the projections must be folded back BEFORE the
    advancer starts, or it can pick up a run whose position is stale and start
    the wrong node.
    """
    wiring = wire_workflow_kind(
        app,
        resource_svc=resource_svc,
        audit=audit,
        sm=sm,
        chat=chat,
        knowledge=knowledge,
        skills=skills,
        attempts=attempts,
        gate_holder=gate_holder,
        provider=provider,
        credential_resolver=credential_resolver,
    )
    await rebuild_workflow_projections(wiring.run_service)
    wiring.worker.start()
    return wiring


async def rebuild_workflow_projections(run_service: WorkflowRunService) -> None:
    """Fold every run's events back into its projection at startup (FR-014).

    Best-effort by design: a run whose events cannot be folded is a run with a
    problem, and refusing to start the daemon over it would take the whole
    vault down for one broken record.
    """
    try:
        rebuilt = await run_service.rebuild_all()
    except Exception:
        logger.warning("workflow.rebuild.failed", exc_info=True)
        return
    if rebuilt:
        logger.info("workflow.rebuild.done", extra={"runs": rebuilt})


async def stop_advance_worker(worker: AdvanceWorker) -> None:
    """Stop the advancer at shutdown, tolerating a worker that never started."""
    with contextlib.suppress(Exception):
        await worker.stop()


__all__ = [
    "DEFAULT_RUN_AGENT",
    "WorkflowWiring",
    "build_attempt_repo",
    "rebuild_workflow_projections",
    "start_workflow",
    "stop_advance_worker",
    "wire_workflow_kind",
]
