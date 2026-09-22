"""What satisfies the workflow engine's ports, built where two kinds may meet.

Every one of these is a bridge from a `coffer.application.workflow` Protocol to
something owned by another kind — the turn platform, the skill store, the
knowledge layer, a channel, the audit log, this machine's identity. They live at
the composition root because that is the only layer allowed to see both sides;
the engine itself imports none of them, which is what the cross-kind fence in
``backend/pyproject.toml`` enforces.

They are deliberately thin. If an adapter here starts making decisions, the
decision belongs in the engine behind a port, not in the wiring.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.channel.service import ChannelService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.service import SkillService
from coffer.application.workflow.commands import template_of
from coffer.application.workflow.task_index import EarlierTask
from coffer.application.workflow.transcripts import TranscriptMessage
from coffer.domain.chat.events import AgentEvent
from coffer.domain.chat.message import Role, TextBlock
from coffer.domain.errors import CofferError
from coffer.domain.workflow.run import ADHOC_KEY_PREFIX
from coffer.infrastructure.chat.persistence import MessageRepo
from coffer.infrastructure.sync.identity import resolve_identity

#: Re-exported: which file an adapter lives in is this package's business, not
#: the composition root's.
from coffer.surfaces.http.workflow_artifact_adapter import FileArtifactStore

__all__ = [
    "ChatTurnPlatform",
    "EarlierTasks",
    "FileArtifactStore",
    "KnowledgeInputs",
    "ThisMachine",
    "WorkflowAudit",
    "WorkflowNotify",
    "conversation_env_lookup",
]

logger = logging.getLogger(__name__)

#: The environment variable the MCP shim reads its run identity out of. The
#: shim stamps it into the ``initialize`` handshake, the gateway captures it,
#: and the gate attributes a tool call back to the node that made it (FR-035).
RUN_CONTEXT_ENV = "COFFER_RUN_CONTEXT"


#: What a workflow task's conversation is owned by. One string, read by nobody
#: but the chat list's "is this mine" test — a name rather than a boolean so a
#: second surface that grows conversations of its own can say which it is.
CONVERSATION_OWNER = "workflow"


class ChatTurnPlatform:
    """``TurnPlatformPort`` over the conversation service and the orchestrator."""

    def __init__(
        self,
        *,
        chat: ChatService,
        orchestrator: TurnOrchestrator,
        messages: MessageRepo,
        registry: AgentProviderRegistry,
    ) -> None:
        self._chat = chat
        self._orchestrator = orchestrator
        # The registry, so a task can be ASSIGNED an agent that exists: the
        # chat service resolves one at creation and raises then, which is far
        # too late for a choice made before the task starts (FR-071).
        self._registry = registry
        # Compaction deletes messages, and deleting is the one thing the chat
        # SERVICE does not expose — it has no business doing so for an ordinary
        # conversation. The composition root may reach the repo; this is why.
        self._messages = messages

    def known_agents(self) -> tuple[str, ...]:
        return tuple(self._registry.agent_keys())

    async def create_conversation(
        self,
        *,
        agent_key: str,
        cwd: str,
        run_context: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> str:
        # ``run_context`` is not passed here on purpose: it reaches the agent
        # through the environment at turn time, looked up from the attempt row
        # by ``conversation_env_lookup``. Carrying it in the conversation's
        # config as well would be a second copy of the same fact, and the copy
        # that matters is the one that survives a restart.
        # ``owner`` is how it stays out of the developer's own chat list while
        # staying an ordinary conversation everywhere else (FR-030): this one
        # belongs to a run, and the chat layer needs to know nothing more.
        # ``model`` and ``effort`` go in beside the working directory because
        # that is where a conversation keeps them (FR-071) — the pickers on a
        # task's page write the same two fields once it is running, so a task
        # that was assigned a model opens already set to it rather than being
        # corrected a moment later.
        config: dict[str, Any] = {"cwd": cwd}
        if model is not None:
            config["model"] = model
        if effort is not None:
            config["effort"] = effort
        conv = await self._chat.create_conversation(
            agent_key=agent_key, agent_config=config, owner=CONVERSATION_OWNER
        )
        return conv.id

    async def start_turn(self, conversation_id: str, text: str) -> asyncio.Queue[AgentEvent | None]:
        return await self._orchestrator.start_turn(conversation_id, text)

    async def transcript(self, conversation_id: str) -> Sequence[TranscriptMessage]:
        """The conversation, oldest first, as the composer will quote it."""
        out: list[TranscriptMessage] = []
        for message in await self._chat.list_messages(conversation_id):
            text = "\n".join(
                block.text for block in message.content if isinstance(block, TextBlock)
            ).strip()
            if text:
                out.append(TranscriptMessage(role=str(message.role), text=text))
        return out

    async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None:
        """Replace everything before the last ``keep_last`` messages with one
        summary that STAYS in the conversation (FR-049).

        The summary is appended BEFORE the old messages are deleted. Ordered
        the other way, an interruption between the two steps would leave the
        conversation with a hole and no account of it — which is the one thing
        compaction must never do.
        """
        messages = await self._chat.list_messages(conversation_id)
        if len(messages) <= keep_last:
            return
        doomed = messages[: len(messages) - keep_last]
        await self._chat.append_message(
            conversation_id,
            role=Role.ASSISTANT,
            content=[TextBlock(text=summary)],
        )
        for message in doomed:
            await self._messages.delete_message(message.id)

    def interrupt(self, conversation_id: str) -> None:
        self._orchestrator.interrupt_turn(conversation_id)


class EarlierTasks:
    """``EarlierTasksPort`` — what the run did before this attempt (FR-029).

    Answers with the LATEST attempt of each task. An earlier attempt is
    superseded by definition — the run reopened that task because what it
    produced was not right — and listing both would offer the next task a
    choice between an answer and a discarded one.

    It reaches for two things the composer cannot: the attempt rows, which say
    what became of each task, and the run's frozen template, which says what
    each task is CALLED. A name is worth the lookup: the index is read by an
    agent that has to act on it, and `draft_td` is a key where "Draft the
    technical design" is an instruction.
    """

    def __init__(self, *, runs: Any, attempts: Any) -> None:
        self._runs = runs
        self._attempts = attempts

    async def earlier(self, run_id: str, before_attempt_id: str) -> list[EarlierTask]:
        rows = sorted(
            await self._attempts.list_attempts(run_id),
            key=lambda row: (row.started_at or row.id, row.id),
        )
        names = await self._names(run_id)
        # Dict rather than list: keyed by task, each assignment overwrites the
        # attempt before it, and insertion order keeps the tasks themselves in
        # the order the run first reached them.
        latest: dict[str, EarlierTask] = {}
        for row in rows:
            if row.id == before_attempt_id:
                break
            latest[row.node_key] = EarlierTask(
                node_key=row.node_key,
                name=names.get(row.node_key) or _adhoc_name(row.node_key),
                attempt=row.attempt,
                status=row.status,
                failure_reason=row.failure_reason,
            )
        return list(latest.values())

    async def _names(self, run_id: str) -> dict[str, str]:
        """What the frozen template calls each of its tasks, or nothing.

        A run whose snapshot will not parse still gets an index — the keys are
        readable on their own, and refusing to open a task over a display name
        would be the context layer deciding a run is over.
        """
        run = await self._runs.get_run(run_id)
        if run is None:
            return {}
        try:
            template = template_of(run)
        except CofferError:
            logger.warning("workflow.index.template_unreadable", extra={"run_id": run_id})
            return {}
        return {node.key: node.name for _stage, node in template.ordered_nodes()}


def _adhoc_name(node_key: str) -> str:
    """A readable name for a task the template never had (FR-028).

    Its real name lives on the event that recorded it, which this adapter does
    not read; the key was slugged from that name, so un-slugging it gets close
    enough to be useful and is never wrong about which task it is.
    """
    return node_key.removeprefix(ADHOC_KEY_PREFIX).replace("-", " ").strip() or node_key


class SkillText:
    """``SkillTextPort`` — a node's bound skill, as the text it opens with."""

    def __init__(self, skills: SkillService) -> None:
        self._skills = skills

    async def instructions(self, skill_name: str) -> str | None:
        try:
            skill = await self._skills.get_skill(skill_name)
        except CofferError:
            # A template naming a skill that has since been deleted must still
            # run, saying so, rather than stalling the whole delivery (FR-029).
            logger.warning("workflow.skill.missing", extra={"skill": skill_name})
            return None
        path = self._skills.master_path(skill.name) + "/SKILL.md"
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            logger.warning("workflow.skill.unreadable", extra={"skill": skill_name})
            return None


class KnowledgeInputs:
    """``KnowledgeInputPort`` — a mounted collection, named rather than inlined."""

    def __init__(self, knowledge: KnowledgeService) -> None:
        self._knowledge = knowledge

    async def describe(self, collection: str) -> str | None:
        for entry in await self._knowledge.list_collections():
            if entry.name == collection:
                # Two lanes, counted apart, because they answer different
                # questions for a task: how much material a person put in, and
                # how much of it an agent can currently read.
                return entry.description or (
                    f"{entry.source_count} source(s), {entry.topic_count} topic(s)"
                )
        return None

    async def create_collection(self, name: str) -> str:
        await self._knowledge.create_collection(name, actor="workflow", description=None)
        return name


class WorkflowNotify:
    """``NotifyPort`` — an approval reaches the developer where they are (FR-039).

    Two deliveries, and the first is the one that must not fail: the run's main
    thread is the record, so it is written before anything leaves the machine.
    Channel delivery is best-effort on purpose — a vault with no channel bound
    is a supported vault, and a channel that is down must not stop a run from
    asking for a decision it can still be given from the web UI or the CLI.

    Every enabled channel gets the message. There is no per-run channel setting
    and inventing one here would be a product decision made in the wiring; a
    vault with several channels bound has said it wants to hear on all of them.
    """

    def __init__(
        self,
        *,
        chat: ChatService,
        channels: ChannelService,
        resources: ResourceService,
        runs: Any,
    ) -> None:
        self._chat = chat
        self._channels = channels
        self._resources = resources
        self._runs = runs

    async def announce(self, run_id: str, text: str) -> None:
        await self._post(run_id, text)

    async def request_approval(self, run_id: str, approval_id: str, preview: str) -> None:
        await self._post(
            run_id,
            f"Waiting on you — approval `{approval_id}`.\n\n{preview}\n\n"
            f"`coffer workflow approve {approval_id}` or reject it with a reason.",
        )

    async def _post(self, run_id: str, text: str) -> None:
        run = await self._runs.get_run(run_id)
        if run is not None:
            # The record first, and not best-effort: if this raises, the run
            # has not asked for a decision and the caller should hear about it.
            await self._chat.append_message(
                run.main_conversation_id,
                role=Role.ASSISTANT,
                content=[TextBlock(text=text)],
            )
        for resource in await self._resources.list(kind="channel", enabled=True):
            try:
                await self._channels.notify(resource.name, text, actor="workflow")
            except Exception:
                logger.warning(
                    "workflow.notify.channel_failed",
                    extra={"channel": resource.name, "run": run_id},
                    exc_info=True,
                )


class WorkflowAudit:
    """``AuditPort`` over the vault-wide audit service."""

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    async def record(
        self,
        event_type: str,
        *,
        actor: str,
        subject_kind: str | None = None,
        subject_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        subject = (subject_kind, subject_name) if subject_kind and subject_name else None
        await self._audit.record(event_type, subject=subject, actor=actor, details=detail or {})


class ThisMachine:
    """``MachineIdPort`` — the run's owner (FR-012)."""

    def current(self) -> str:
        return resolve_identity().machine_id


def conversation_env_lookup(attempts: Any) -> Any:
    """Build the per-conversation environment a node's agent process runs with.

    Returns ``None`` for any conversation that is not a node's — which is every
    ordinary chat — so nothing about those turns changes. For a node's, it
    yields the run identity the gate needs, derived from the attempt ROW rather
    than from a map built when the conversation was created: after a daemon
    restart the map would be empty, and the next turn on that conversation (a
    node in review being given feedback) would run ungated.
    """

    async def lookup(conversation_id: str) -> dict[str, str] | None:
        attempt = await attempts.attempt_by_conversation(conversation_id)
        if attempt is None:
            return None
        return {RUN_CONTEXT_ENV: f"{attempt.run_id}/{attempt.id}"}

    return lookup
