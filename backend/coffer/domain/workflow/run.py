"""Run, NodeAttempt and Approval — the execution side of a workflow (spec workflow).

A run is **not** a Resource ("Create a run from a template and a title alone"):
it is operational state, it belongs to one machine, and it does not sync. What
travels is the template it froze a snapshot of at creation ("Freeze the template
when a run is created"); everything in this module is the record of one
execution of that snapshot.

The enum values are the strings that go on the wire and into SQLite — they are
the same tokens ``contracts/api.openapi.yaml`` enumerates, so a status read out
of the database, sent over HTTP and compared here is one vocabulary rather than
three that agree by habit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    """A run's six statuses (spec workflow "Keep a run to six statuses").

    "Waiting for the developer" is deliberately absent: waiting is a property
    of a node, never of a run. A run whose node sits in review is still
    ``running`` — it has not stopped, it has arrived somewhere.
    """

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


#: Statuses from which no mutating command is ever accepted again (spec workflow
#: "Keep a run to six statuses", "Accept the run signals start, pause, resume
#: and abort"). ``failed`` is **not** here: a failed run is recoverable — the
#: developer retries the node that failed and resumes — whereas a completed run
#: has nowhere left to go and an aborted one was ended on purpose.
TERMINAL_RUN_STATUSES: frozenset[RunStatus] = frozenset({RunStatus.COMPLETED, RunStatus.ABORTED})


class NodeStatus(StrEnum):
    """A node attempt's seven statuses (spec workflow "Keep a node to seven
    statuses").

    ``waiting_review`` and ``waiting_approval`` are both "stopped at the
    developer", kept apart because the thing being decided differs: the node's
    own output versus a prepared external write.
    """

    PENDING = "pending"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


#: Node statuses that will never change again on their own attempt. A retry
#: does not reopen one of these — it inserts ``attempt + 1`` (spec workflow
#: "Keep every attempt when a node is retried").
TERMINAL_NODE_STATUSES: frozenset[NodeStatus] = frozenset(
    {NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.FAILED}
)


class RunSignal(StrEnum):
    """The four commands that act on a run as a whole (spec workflow "Accept
    the run signals start, pause, resume and abort").

    Node lifecycle actions are not signals — they are about a node, they have
    their own route, and mixing the two vocabularies is how a surface ends up
    accepting ``skip`` for a run.
    """

    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    ABORT = "abort"


class NodeAction(StrEnum):
    """The six commands that act on one node (spec workflow "Accept the node
    actions start, feedback, complete, retry, skip and restore")."""

    START = "start"
    FEEDBACK = "feedback"
    COMPLETE = "complete"
    RETRY = "retry"
    SKIP = "skip"
    RESTORE = "restore"


class ApprovalKind(StrEnum):
    """What a pending approval stands in front of.

    One value, and the enum is kept for the honesty of saying so: an approval
    is always a write-class upstream call the gateway is holding (spec
    workflow "Refuse an unapproved write-class tool call made for a run").

    There was a second, ``node_action``, for a task whose declared policy is
    ``always``. Nothing ever constructed it. A task's work is a conversation,
    and a conversation has no single exact payload to put in front of someone
    before it runs — so the value described an approval that could not be
    built, while the decision that task's policy really asks for (stop when
    the turn ends, and let the developer say whether the run goes on) is a node
    STATUS and was there all along. What its writes needed was decided at the
    gateway while it ran, where a payload exists.
    """

    TOOL_CALL = "tool_call"


class ApprovalStatus(StrEnum):
    """An approval's lifecycle.

    ``superseded`` is what aborting a run does to its pending approvals — they
    were neither decided nor left to expire, and recording them as either would
    be a lie about what the developer did.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


#: An approval in one of these has been answered for good; a repeated decision
#: returns it unchanged and executes nothing a second time (spec workflow
#: "Make an approval decision idempotent").
TERMINAL_APPROVAL_STATUSES: frozenset[ApprovalStatus] = frozenset(
    {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.SUPERSEDED,
    }
)


class FailureReason(StrEnum):
    """Why an attempt failed — a closed vocabulary, because the reason is read
    by the UI and by the developer deciding whether to retry.

    ``interrupted`` is the one the daemon writes to itself on start-up: a node
    that was mid-turn when the process stopped is reported, not resumed and not
    dropped (spec workflow "Report a node interrupted by a restart as failed").
    """

    INTERRUPTED = "interrupted"
    AGENT_ERROR = "agent_error"
    MISSING_ARTIFACT = "missing_artifact"
    ATTEMPT_CEILING = "attempt_ceiling"


class RunInputKind(StrEnum):
    """What a mounted input points at (spec workflow "List a run's mounted
    inputs to every node"). Inputs are *listed* to a node, never inlined
    wholesale — a knowledge collection can be larger than a context window."""

    KNOWLEDGE = "knowledge"
    FILE = "file"
    #: Something the developer wrote themselves rather than uploaded — a
    #: markdown file under the run's own inputs, editable for as long as the run
    #: lives (spec workflow "Keep the developer's own notes in a run's
    #: context"). It is a file to every reader; the kind exists so the app knows
    #: which rows it may open an editor on.
    NOTE = "note"
    LINK = "link"
    #: An absolute path to a local repository. The run never works in the
    #: developer's own checkout — it is given its own inside the run's working
    #: directory (spec workflow "Give a mounted repository its own checkout").
    REPO = "repo"


#: How a ``repo`` input was actually given to the run. A worktree is the run's
#: own checkout on its own branch; a link is a directory that is not a git
#: repository and could only be pointed at. The difference is recorded because
#: the node's context must be able to say which it got (spec workflow "Give a
#: mounted repository its own checkout") rather than implying an isolation it
#: does not have.
REPO_MOUNT_WORKTREE = "worktree"
REPO_MOUNT_LINK = "link"


@dataclass(frozen=True)
class RunInput:
    """One mounted input: a collection, an uploaded file, a link, or a repo.

    ``size`` is the uploaded file's bytes and is ``None`` for every other kind
    — a collection's size is the knowledge layer's answer, a link's is nobody's
    — and it is carried so the developer can see what a run is dragging around
    without opening the directory.

    ``path`` and ``mount`` belong to a ``repo`` input and are ``None``
    otherwise: where inside the run's working directory its checkout landed, and
    whether that checkout is a git worktree of its own or a link to a directory
    that was not a repository (spec workflow "Give a mounted repository its own
    checkout").
    """

    kind: RunInputKind
    ref: str
    label: str | None = None
    size: int | None = None
    path: str | None = None
    mount: str | None = None


@dataclass(frozen=True)
class Run:
    """One execution of a frozen template snapshot, in one working directory,
    on one machine.

    A run has **no conversation of its own** (spec workflow "Give a run no
    conversation of its own"): every conversation belongs to one task and hangs
    off its attempt.

    ``status``, ``current_stage_key``, ``current_node_key`` and ``tokens_spent``
    are **projections** of the event log ("Rebuild a run from its event log") —
    they are carried here so a list query is one row read, and rebuilt by
    ``events.project`` on daemon start. When they disagree with the events, the
    events win.
    """

    id: str
    template_ref: str
    template_snapshot: dict[str, Any]
    title: str
    workdir: str
    machine_id: str
    status: RunStatus = RunStatus.DRAFT
    current_stage_key: str | None = None
    current_node_key: str | None = None
    version: int = 1
    tokens_spent: int = 0
    inputs: tuple[RunInput, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def owned_by(self, machine_id: str) -> bool:
        """Whether this machine is the one that advances the run (spec workflow
        "Advance a run only on the machine that owns it")."""
        return self.machine_id == machine_id


#: Prefix of an ad-hoc task's node key (spec workflow "Add an ad-hoc task to any
#: stage"). An ad-hoc task is attributed exactly as a template node is, so it
#: needs a key in the same namespace — this prefix is what keeps it from ever
#: colliding with one, since a template node key may not contain ``:``.
ADHOC_KEY_PREFIX = "adhoc:"


def is_adhoc_key(node_key: str) -> bool:
    """Whether a node key names an ad-hoc task rather than a template node."""
    return node_key.startswith(ADHOC_KEY_PREFIX)


@dataclass(frozen=True)
class NodeAttempt:
    """One try at one node.

    A retry never rewrites an attempt — it inserts ``attempt + 1`` (spec
    workflow "Keep every attempt when a node is retried"), so the earlier
    attempt's conversation, output and feedback stay readable. That is also what
    makes an interrupted node honest: its attempt keeps its conversation id and
    simply says it failed.
    """

    id: str
    run_id: str
    stage_key: str
    node_key: str
    attempt: int
    status: NodeStatus = NodeStatus.PENDING
    conversation_id: str | None = None
    instructions: str | None = None
    summary: str | None = None
    failure_reason: FailureReason | None = None
    tokens: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def is_adhoc(self) -> bool:
        return is_adhoc_key(self.node_key)


@dataclass(frozen=True)
class RunProjection:
    """The four columns a fold of a run's events produces (spec workflow
    "Rebuild a run from its event log").

    It lives in the domain because BOTH sides need it and neither may import
    the other: the event fold produces one, the repository writes one. Leaving
    it in the repository made the port's parameter contravariant against a
    concrete class, which no Protocol can satisfy.

    All four, always. A projection is a complete picture of where a run stands,
    so writing it as a patch would let a caller advance the node without
    advancing the status and store a position no fold of the events produces.
    """

    status: str
    current_stage_key: str | None
    current_node_key: str | None
    tokens_spent: int


@dataclass(frozen=True)
class Approval:
    """A decision standing between a prepared external write and its execution.

    ``payload`` is the arguments **verbatim**, never a summary — a decision on
    a summary is not a decision. Credential material never reaches it because
    the gateway injects credentials at dispatch, after the decision.
    """

    id: str
    run_id: str
    kind: ApprovalKind
    payload: dict[str, Any]
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    attempt_id: str | None = None
    tool_name: str | None = None
    decided_by: str | None = None
    decided_surface: str | None = None
    created_at: datetime | None = None
    decided_at: datetime | None = None
    #: What the developer said when they decided. It is kept because a
    #: rejection's reason is the one thing the node can act on — "not this
    #: region" tells it what to do next, where a bare refusal does not.
    comment: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_APPROVAL_STATUSES

    def authorises_at(self, now: datetime) -> bool:
        """Whether this approval authorises its write **right now**.

        Expiry is checked against the clock rather than against ``status``: an
        approval whose ``expires_at`` has passed authorises nothing even if no
        sweep has moved it to ``expired`` yet (spec workflow "Resume or fail a
        held tool call, never drop it"). An approval that has not been approved
        authorises nothing either way.
        """
        return self.status is ApprovalStatus.APPROVED and now < self.expires_at
