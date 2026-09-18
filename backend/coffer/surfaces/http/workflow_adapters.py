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
import pathlib
import shutil
from collections.abc import Sequence
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.channel.service import ChannelService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.resource_service import ResourceService
from coffer.application.skill.service import SkillService
from coffer.application.workflow.transcripts import TaskTranscript, TranscriptMessage
from coffer.domain.chat.events import AgentEvent
from coffer.domain.chat.message import Role, TextBlock
from coffer.domain.errors import CofferError
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.chat.persistence import MessageRepo
from coffer.infrastructure.sync.identity import resolve_identity
from coffer.infrastructure.workflow import artifacts as wf_artifacts
from coffer.infrastructure.workflow import files as wf_files
from coffer.infrastructure.workflow import paths as wf_paths

__all__ = [
    "ChatTurnPlatform",
    "FileArtifactStore",
    "KnowledgeInputs",
    "TaskTranscripts",
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


class ChatTurnPlatform:
    """``TurnPlatformPort`` over the conversation service and the orchestrator."""

    def __init__(
        self, *, chat: ChatService, orchestrator: TurnOrchestrator, messages: MessageRepo
    ) -> None:
        self._chat = chat
        self._orchestrator = orchestrator
        # Compaction deletes messages, and deleting is the one thing the chat
        # SERVICE does not expose — it has no business doing so for an ordinary
        # conversation. The composition root may reach the repo; this is why.
        self._messages = messages

    async def create_conversation(
        self, *, agent_key: str, cwd: str, run_context: str | None = None
    ) -> str:
        # ``run_context`` is not passed here on purpose: it reaches the agent
        # through the environment at turn time, looked up from the attempt row
        # by ``conversation_env_lookup``. Carrying it in the conversation's
        # config as well would be a second copy of the same fact, and the copy
        # that matters is the one that survives a restart.
        conv = await self._chat.create_conversation(agent_key=agent_key, agent_config={"cwd": cwd})
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


class TaskTranscripts:
    """``TaskTranscriptsPort`` — what the run's earlier tasks said (FR-029).

    This is what replaced the run's main thread. There is no conversation
    belonging to the run, so "what has been said so far" is the concatenation
    of the tasks that came before this one — which is also why a correction the
    developer types into any task reaches every task that opens afterwards.
    """

    def __init__(self, *, chat: ChatService, attempts: Any) -> None:
        self._chat = chat
        self._attempts = attempts

    async def transcripts(self, run_id: str, before_attempt_id: str) -> list[TaskTranscript]:
        rows = sorted(
            await self._attempts.list_attempts(run_id),
            key=lambda row: (row.started_at or row.id, row.id),
        )
        out: list[TaskTranscript] = []
        for row in rows:
            if row.id == before_attempt_id:
                break
            if not row.conversation_id:
                # A manual node opens no conversation; it has nothing to quote.
                continue
            messages = tuple(
                TranscriptMessage(role=str(m.role), text=text)
                for m in await self._chat.list_messages(row.conversation_id)
                if (
                    text := "\n".join(b.text for b in m.content if isinstance(b, TextBlock)).strip()
                )
            )
            if messages:
                out.append(
                    TaskTranscript(node_key=row.node_key, attempt=row.attempt, messages=messages)
                )
        return out


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
        resource_kind: str | None = None,
        resource_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        ref = (
            ResourceRef(kind=resource_kind, name=resource_name)
            if resource_kind and resource_name
            else None
        )
        await self._audit.record(event_type, ref=ref, actor=actor, details=detail or {})


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


class FileArtifactStore:
    """``ArtifactStorePort`` over the run directory's module-level functions.

    The infrastructure exposes functions rather than a class — path handling has
    no state worth holding — so the object the engine's port wants is assembled
    here. ``delete_run_dir`` is the one operation with no function behind it,
    because deleting a tree is the only thing in this file that is destructive
    and it belongs beside the guard that decides what a run directory is.
    """

    def run_dir(self, run_id: str) -> str:
        return str(wf_paths.run_dir(run_id))

    def workspace_dir(self, run_id: str) -> str:
        """The run's own working directory — what every node's conversation
        runs in, and what a mounted repository is checked out into (FR-053)."""
        return str(wf_paths.workspace_dir(run_id))

    def ensure_run_dirs(self, run_id: str) -> None:
        wf_artifacts.ensure_run_dirs(run_id)

    def list_artifacts(self, run_id: str) -> Sequence[wf_artifacts.ArtifactEntry]:
        return wf_artifacts.list_artifacts(run_id)

    def write_catalogue(self, run_id: str, markdown: str) -> None:
        path = wf_paths.catalog_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")

    def read_catalogue(self, run_id: str) -> str:
        try:
            return wf_paths.catalog_path(run_id).read_text(encoding="utf-8")
        except OSError:
            # Absent is not an error: the catalogue is generated, and a run that
            # has produced nothing has nothing to describe.
            return ""

    def collect_run_files(
        self, run_id: str, destination: str, *, references: str | None = None
    ) -> int:
        return wf_artifacts.collect_run_files(
            run_id, pathlib.Path(destination), references=references
        )

    def read_file(self, run_id: str, rel_path: str) -> wf_files.RunFile | None:
        return wf_files.read_file(run_id, rel_path)

    def read_bytes(self, run_id: str, rel_path: str) -> tuple[bytes, str] | None:
        return wf_files.read_bytes(run_id, rel_path)

    def delete_run_dir(self, run_id: str) -> None:
        shutil.rmtree(wf_paths.run_dir(run_id), ignore_errors=True)
