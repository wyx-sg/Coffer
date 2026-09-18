"""The seams the workflow engine reaches everything else through.

The engine touches four other kinds — the turn platform to run a node, the
gateway to let a node reach the outside world, the knowledge layer to mount an
input and to keep a finished run's output, and a channel to put an approval in
front of the developer. It imports none of them. Each is a Protocol here that
the composition root satisfies with the real thing, which is what keeps the
cross-kind fence in ``backend/pyproject.toml`` true rather than aspirational.

Two shapes appear repeatedly and are worth naming up front:

* **Rows are structural.** The persistence layer returns its own ORM objects,
  which application code may not import, so the row Protocols describe the
  attributes the engine reads and nothing more.
* **A turn is a queue.** Starting a node's work hands back an event queue that
  ends in ``None``; the driver drains it — the chat platform's own shape
  (``TurnOrchestrator.start_turn``), reused rather than wrapped.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from coffer.application.workflow.port_repos import (
    ApprovalRepoPort,
    AttemptRepoPort,
    EventRepoPort,
    RunRepoPort,
)
from coffer.application.workflow.port_rows import (
    ApprovalRow,
    AttemptRow,
    EventRow,
    RunProjectionValue,
    RunRow,
)
from coffer.application.workflow.transcripts import TranscriptMessage
from coffer.domain.chat.events import AgentEvent

__all__ = [
    "ApprovalRepoPort",
    "ApprovalRow",
    "ArtifactEntry",
    "ArtifactStorePort",
    "AttemptRepoPort",
    "AttemptRow",
    "AuditPort",
    "ConversationPort",
    "EventRepoPort",
    "EventRow",
    "KnowledgeInputPort",
    "MachineIdPort",
    "NotifyPort",
    "RunProjectionValue",
    "RunRepoPort",
    "RunRow",
    "SkillTextPort",
    "SummariserPort",
    "ToolClassPort",
    "TurnPlatformPort",
]


# ---------------------------------------------------------------------------
# The turn platform — how a node does its work
# ---------------------------------------------------------------------------


class ConversationPort(Protocol):
    """Reading one conversation back, and compacting it (FR-049).

    Narrower than ``TurnPlatformPort`` on purpose: ``compaction`` needs to read
    a conversation and rewrite its oldest end, and nothing else, so that is all
    it is handed. The real platform satisfies both.
    """

    async def transcript(self, conversation_id: str) -> Sequence[TranscriptMessage]:
        """Every message of the conversation, oldest first."""
        ...

    async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None:
        """Replace everything before the last ``keep_last`` messages with one
        summary message that STAYS in the conversation (FR-049).

        One call rather than a delete and an append: a process that dies
        between the two would leave a node with a hole where its history was,
        which is the exact failure FR-049 forbids."""
        ...


class TurnPlatformPort(ConversationPort, Protocol):
    """One node's conversation, from the engine's side.

    A run has no conversation of its own (FR-030) — every conversation this
    port opens belongs to one task, and what the developer says inside one
    reaches later tasks by being part of the transcript they open with, not by
    being copied anywhere.
    """

    async def create_conversation(
        self, *, agent_key: str, cwd: str, run_context: str | None = None
    ) -> str:
        """Open a conversation and return its id.

        ``run_context`` is stamped into the agent process's environment so the
        gateway can attribute that agent's tool calls back to this run's node
        (FR-035)."""
        ...

    async def start_turn(self, conversation_id: str, text: str) -> asyncio.Queue[AgentEvent | None]:
        """Start the node's turn now; the queue ends with ``None``."""
        ...

    def interrupt(self, conversation_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Everything else the engine borrows
# ---------------------------------------------------------------------------


class ArtifactEntry(Protocol):
    """One artifact, as the store reports it.

    Read-only properties rather than plain attributes: the concrete entry is a
    FROZEN dataclass, which a Protocol declaring mutable attributes would not
    be satisfied by — and the engine only ever reads these.
    """

    @property
    def name(self) -> str: ...

    @property
    def node_key(self) -> str: ...

    @property
    def attempt(self) -> int: ...

    @property
    def path(self) -> str: ...

    @property
    def size(self) -> int: ...

    @property
    def modified_at(self) -> datetime: ...


class RunFileView(Protocol):
    """One file under a run's directory, as the preview route reports it.

    Read-only properties, not attributes, and a Protocol rather than a
    dataclass — for the same reason ``MountedRepoValue`` is: the concrete
    value the adapter returns is a FROZEN dataclass, which satisfies neither a
    nominal type of its own nor a Protocol declaring mutable attributes.
    """

    @property
    def path(self) -> str:
        """Relative to the run's own directory."""
        ...

    @property
    def name(self) -> str: ...

    @property
    def size(self) -> int:
        """The file's real size, not the size of what came back."""
        ...

    @property
    def text(self) -> str | None:
        """``None`` when the bytes are not UTF-8 text — a preview that rendered
        a PNG as mojibake would claim to have shown the developer something."""
        ...

    @property
    def truncated(self) -> bool:
        """True when ``text`` is the head of a longer file."""
        ...


class ArtifactStorePort(Protocol):
    def run_dir(self, run_id: str) -> str: ...

    def workspace_dir(self, run_id: str) -> str:
        """The working directory this run's node conversations run in.

        Coffer's, not the caller's (FR-053)."""
        ...

    def ensure_run_dirs(self, run_id: str) -> None: ...

    def list_artifacts(self, run_id: str) -> Sequence[ArtifactEntry]: ...

    def write_catalogue(self, run_id: str, markdown: str) -> None: ...

    def read_catalogue(self, run_id: str) -> str: ...

    def collect_run_files(
        self, run_id: str, destination: str, *, references: str | None = None
    ) -> int:
        """Copy what the run is MADE OF into ``destination`` (FR-043) — its
        artifacts, its uploads and its notes — plus a ``references.md`` when
        the caller supplies one. Returns how many files landed."""
        ...

    def read_file(self, run_id: str, rel_path: str) -> RunFileView | None:
        """One file under the run's directory, for the UI's preview (FR-064).

        ``None`` when there is no such file. Raises when the path is not one
        this run may address — the guard is the store's, not the caller's."""
        ...

    def read_bytes(self, run_id: str, rel_path: str) -> tuple[bytes, str] | None:
        """One file's BYTES and its media type, or ``None`` when it is absent.

        The sibling above answers "show this to a person"; this answers "put
        this in an <img>". Same guard, same size cap, different question — a
        pasted screenshot has no text to preview and is still the thing the
        note is about (FR-069)."""
        ...

    def delete_run_dir(self, run_id: str) -> None: ...


class SkillTextPort(Protocol):
    """A node's bound skill, as the text that goes into its opening message.

    ``None`` when the skill is not registered — a run whose template names a
    skill deleted since must still run, saying so, rather than stalling."""

    async def instructions(self, skill_name: str) -> str | None: ...


class KnowledgeInputPort(Protocol):
    """A mounted knowledge collection, as a line in the node's context.

    Never inlined: a node is an agent with ``coffer__search`` and a
    filesystem, so it is told what is mounted (FR-032)."""

    async def describe(self, collection: str) -> str | None: ...

    async def create_collection(self, name: str) -> str: ...


class NotifyPort(Protocol):
    """Where an approval and a run's progress reach the developer (FR-039).

    A vault with no channel bound still works — the approval is on the task's
    own conversation either way (FR-039) — so every method here is allowed to
    do nothing."""

    async def announce(self, run_id: str, text: str) -> None: ...

    async def request_approval(self, run_id: str, approval_id: str, preview: str) -> None: ...


class AuditPort(Protocol):
    async def record(
        self,
        event_type: str,
        *,
        actor: str,
        resource_kind: str | None = None,
        resource_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None: ...


class SummariserPort(Protocol):
    """One short summary of a long piece of text (FR-048, FR-049).

    The same seam the rest of the vault uses for its own model calls: the
    composition root resolves Coffer's internal-default connection and runs one
    completion on it, exactly as ``application/memory``'s organise pass and
    knowledge's ingestion do.

    ``None`` is a first-class answer — no internal connection configured, or
    the model could not be reached. Every caller degrades honestly on it: what
    would have been summarised is NAMED instead and the context says so, so
    nothing is ever silently dropped (FR-047)."""

    async def summarise(self, text: str, *, hint: str) -> str | None: ...


class MachineIdPort(Protocol):
    """This machine's stable id — the run's owner (FR-012)."""

    def current(self) -> str: ...


class ToolClassPort(Protocol):
    """Whether an upstream tool writes, and the memory of being told so.

    ``classify`` returns ``None`` for a tool nothing has judged yet, which the
    gate treats as write-class (FR-036); ``remember`` records the developer's
    answer on the server that serves the tool, so the same question is asked
    once."""

    async def classify(self, server: str, tool: str) -> str | None: ...

    async def remember(self, server: str, tool: str, write_class: str) -> None: ...
