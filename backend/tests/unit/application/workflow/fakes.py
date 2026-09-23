"""In-memory stand-ins for every port the workflow engine reaches through.

No database, no agent, no filesystem: the point of this tier is that a whole
run — advance, review, retry, loop, ceiling — can be driven in
milliseconds, which is only true if none of these touch anything real. They are
plain classes rather than mocks so a test reads as "given this state" instead of
"given these call expectations".
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from coffer.application.workflow.ports import RunProjectionValue
from coffer.application.workflow.task_index import EarlierTask
from coffer.application.workflow.transcripts import TranscriptMessage
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def clock() -> datetime:
    return NOW


@dataclass
class FakeRun:
    id: str
    template_ref: str | None
    template_snapshot: dict[str, Any]
    title: str
    workdir: str
    machine_id: str
    status: str
    current_stage_key: str | None = None
    current_node_key: str | None = None
    version: int = 1
    tokens_spent: int = 0
    description: str | None = None
    inputs: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = NOW
    updated_at: datetime | None = NOW


@dataclass
class FakeEvent:
    id: str
    run_id: str
    sequence: int
    event_type: str
    actor: dict[str, Any]
    stage_key: str | None
    node_key: str | None
    payload: dict[str, Any]
    created_at: datetime


@dataclass
class FakeAttempt:
    id: str
    run_id: str
    stage_key: str
    node_key: str
    attempt: int
    status: str = "pending"
    conversation_id: str | None = None
    instructions: str | None = None
    agent: str | None = None
    model: str | None = None
    effort: str | None = None
    summary: str | None = None
    failure_reason: str | None = None
    tokens: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class FakeApproval:
    id: str
    run_id: str
    attempt_id: str | None
    kind: str
    tool_name: str | None
    payload: dict[str, Any]
    status: str
    expires_at: datetime
    created_at: datetime
    decided_by: str | None = None
    decided_surface: str | None = None
    comment: str | None = None
    decided_at: datetime | None = None


class FakeRunRepo:
    def __init__(self) -> None:
        self.rows: dict[str, FakeRun] = {}

    async def create_run(
        self,
        *,
        run_id: str,
        title: str,
        workdir: str,
        machine_id: str,
        template_snapshot: dict[str, Any],
        template_ref: str | None = None,
        status: str = "draft",
        inputs: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> FakeRun:
        row = FakeRun(
            id=run_id,
            template_ref=template_ref,
            template_snapshot=template_snapshot,
            title=title,
            workdir=workdir,
            machine_id=machine_id,
            status=status,
            inputs=list(inputs or []),
            created_at=now or NOW,
            updated_at=now or NOW,
        )
        self.rows[run_id] = row
        return row

    async def get_run(self, run_id: str) -> FakeRun | None:
        row = self.rows.get(run_id)
        # A copy, because the services hold the row they read across awaits and
        # a shared object would hide a missed re-read.
        return None if row is None else _copy(row)

    async def set_inputs(
        self,
        run_id: str,
        inputs: list[Any],
        *,
        now: datetime | None = None,
    ) -> FakeRun | None:
        row = self.rows.get(run_id)
        if row is None:
            return None
        row.inputs = list(inputs)
        row.updated_at = now or NOW
        return _copy(row)

    async def set_label(
        self,
        run_id: str,
        *,
        title: str,
        description: str | None,
        now: datetime | None = None,
    ) -> FakeRun | None:
        row = self.rows.get(run_id)
        if row is None:
            return None
        # Neither the version nor the projection moves: a label is not state
        # the event log owns.
        row.title = title
        row.description = description
        row.updated_at = now or NOW
        return _copy(row)

    async def list_runs(
        self, *, status: str | None = None, limit: int | None = None
    ) -> list[FakeRun]:
        rows = [_copy(r) for r in self.rows.values() if status is None or r.status == status]
        return rows if limit is None else rows[:limit]

    async def update_run_projection(
        self,
        run_id: str,
        expected_version: int,
        projection: RunProjectionValue,
        *,
        now: datetime | None = None,
    ) -> FakeRun | None:
        row = self.rows.get(run_id)
        if row is None or row.version != expected_version:
            return None
        row.status = projection.status
        row.current_stage_key = projection.current_stage_key
        row.current_node_key = projection.current_node_key
        row.tokens_spent = projection.tokens_spent
        row.version = expected_version + 1
        row.updated_at = now or NOW
        return _copy(row)

    async def delete_run(self, run_id: str) -> None:
        self.rows.pop(run_id, None)


class FakeEventRepo:
    def __init__(self) -> None:
        self.rows: list[FakeEvent] = []

    async def append_event(
        self,
        *,
        event_id: str,
        run_id: str,
        event_type: str,
        actor: dict[str, Any],
        stage_key: str | None = None,
        node_key: str | None = None,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> FakeEvent:
        sequence = 1 + max((row.sequence for row in self.rows if row.run_id == run_id), default=0)
        row = FakeEvent(
            id=event_id,
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            actor=actor,
            stage_key=stage_key,
            node_key=node_key,
            payload=payload or {},
            created_at=now or NOW,
        )
        self.rows.append(row)
        return row

    async def list_events(
        self, run_id: str, *, after_sequence: int | None = None, limit: int | None = None
    ) -> list[FakeEvent]:
        rows = sorted(
            (
                row
                for row in self.rows
                if row.run_id == run_id
                and (after_sequence is None or row.sequence > after_sequence)
            ),
            key=lambda row: row.sequence,
        )
        return rows if limit is None else rows[:limit]

    def types_for(self, run_id: str) -> list[str]:
        """The run's event types in order — what most assertions compare."""
        ordered = sorted(
            (row for row in self.rows if row.run_id == run_id), key=lambda row: row.sequence
        )
        return [row.event_type for row in ordered]


class FakeAttemptRepo:
    def __init__(self) -> None:
        self.rows: dict[str, FakeAttempt] = {}

    async def insert_attempt(
        self,
        *,
        attempt_id: str,
        run_id: str,
        stage_key: str,
        node_key: str,
        attempt: int,
        status: str = "pending",
        conversation_id: str | None = None,
        instructions: str | None = None,
        started_at: datetime | None = None,
    ) -> FakeAttempt:
        for row in self.rows.values():
            if (row.run_id, row.node_key, row.attempt) == (run_id, node_key, attempt):
                raise AssertionError(f"duplicate attempt {node_key}#{attempt}")
        row = FakeAttempt(
            id=attempt_id,
            run_id=run_id,
            stage_key=stage_key,
            node_key=node_key,
            attempt=attempt,
            status=status,
            conversation_id=conversation_id,
            instructions=instructions,
            started_at=started_at,
        )
        self.rows[attempt_id] = row
        return row

    async def update_attempt(
        self,
        attempt_id: str,
        *,
        status: str | None = None,
        conversation_id: str | None = None,
        summary: str | None = None,
        failure_reason: str | None = None,
        instructions: str | None = None,
        tokens: int | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> FakeAttempt | None:
        row = self.rows.get(attempt_id)
        if row is None:
            return None
        for name, value in (
            ("status", status),
            ("conversation_id", conversation_id),
            ("summary", summary),
            ("failure_reason", failure_reason),
            ("instructions", instructions),
            ("tokens", tokens),
            ("started_at", started_at),
            ("finished_at", finished_at),
        ):
            if value is not None:
                setattr(row, name, value)
        return _copy(row)

    async def set_assignment(
        self,
        attempt_id: str,
        *,
        agent: str | None,
        model: str | None,
        effort: str | None,
    ) -> FakeAttempt | None:
        row = self.rows.get(attempt_id)
        if row is None:
            return None
        # Verbatim, including None: clearing an override is a real choice.
        row.agent, row.model, row.effort = agent, model, effort
        return _copy(row)

    async def latest_attempt(self, run_id: str, node_key: str) -> FakeAttempt | None:
        rows = [
            row for row in self.rows.values() if row.run_id == run_id and row.node_key == node_key
        ]
        if not rows:
            return None
        return _copy(max(rows, key=lambda row: row.attempt))

    async def list_attempts(self, run_id: str) -> list[FakeAttempt]:
        return [
            _copy(row)
            for row in sorted(
                (row for row in self.rows.values() if row.run_id == run_id),
                key=lambda row: (row.node_key, row.attempt),
            )
        ]


class FakeApprovalRepo:
    def __init__(self) -> None:
        self.rows: dict[str, FakeApproval] = {}

    async def create_approval(
        self,
        *,
        approval_id: str,
        run_id: str,
        kind: str,
        payload: dict[str, Any],
        expires_at: datetime,
        attempt_id: str | None = None,
        tool_name: str | None = None,
        now: datetime | None = None,
    ) -> FakeApproval:
        row = FakeApproval(
            id=approval_id,
            run_id=run_id,
            attempt_id=attempt_id,
            kind=kind,
            tool_name=tool_name,
            payload=payload,
            status="pending",
            expires_at=expires_at,
            created_at=now or NOW,
        )
        self.rows[approval_id] = row
        return row

    async def get_approval(self, approval_id: str) -> FakeApproval | None:
        return self.rows.get(approval_id)

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        decided_by: str | None = None,
        decided_surface: str | None = None,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> FakeApproval | None:
        row = self.rows.get(approval_id)
        if row is None:
            return None
        row.status = status
        row.decided_by = decided_by
        row.decided_surface = decided_surface
        row.comment = comment
        row.decided_at = now or NOW
        return row

    async def list_approvals(self, run_id: str, *, status: str | None = None) -> list[FakeApproval]:
        return [
            row
            for row in self.rows.values()
            if row.run_id == run_id and (status is None or row.status == status)
        ]

    async def expire_due_approvals(self, *, now: datetime | None = None) -> list[FakeApproval]:
        moment = now or NOW
        expired = []
        for row in self.rows.values():
            if row.status == "pending" and row.expires_at <= moment:
                row.status = "expired"
                expired.append(row)
        return expired

    async def supersede_pending(
        self, run_id: str, *, now: datetime | None = None
    ) -> list[FakeApproval]:
        superseded = []
        for row in self.rows.values():
            if row.run_id == run_id and row.status == "pending":
                row.status = "superseded"
                superseded.append(row)
        return superseded


@dataclass
class FakeArtifact:
    name: str
    node_key: str
    attempt: int
    path: str
    size: int = 1
    modified_at: datetime = NOW


class FakeArtifactStore:
    """Artifacts as a list, because what the engine asks of the store is "what
    is there for this node and attempt" and nothing else."""

    def __init__(self) -> None:
        self.entries: dict[str, list[FakeArtifact]] = {}
        self.catalogues: dict[str, str] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.promoted: list[tuple[str, str, str | None]] = []

    def add(self, run_id: str, node_key: str, attempt: int, name: str) -> None:
        self.entries.setdefault(run_id, []).append(
            FakeArtifact(
                name=name, node_key=node_key, attempt=attempt, path=f"{node_key}/{attempt}/{name}"
            )
        )

    def run_dir(self, run_id: str) -> str:
        return f"/fake/workflows/{run_id}"

    def workspace_dir(self, run_id: str) -> str:
        return f"/fake/workflows/{run_id}/workspace"

    def ensure_run_dirs(self, run_id: str) -> None:
        self.created.append(run_id)

    def list_artifacts(self, run_id: str) -> Sequence[FakeArtifact]:
        return tuple(self.entries.get(run_id, ()))

    def write_catalogue(self, run_id: str, markdown: str) -> None:
        self.catalogues[run_id] = markdown

    def read_catalogue(self, run_id: str) -> str:
        return self.catalogues.get(run_id, "")

    def collect_run_files(
        self, run_id: str, destination: str, *, references: str | None = None
    ) -> int:
        # The references text is RECORDED rather than discarded: whether the
        # route built one out of the run's inputs is the half of promotion this
        # seam can prove, and the copying itself is proved against the real
        # store.
        self.promoted.append((run_id, destination, references))
        return len(self.entries.get(run_id, ())) + (0 if references is None else 1)

    def delete_run_dir(self, run_id: str) -> None:
        self.deleted.append(run_id)


class FakeTurnPlatform:
    def __init__(self) -> None:
        self.conversations: list[dict[str, Any]] = []
        self.transcripts: dict[str, list[TranscriptMessage]] = {}
        self.compactions: list[tuple[str, int, str]] = []

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
            {
                "id": conversation_id,
                "agent_key": agent_key,
                "cwd": cwd,
                "run_context": run_context,
                "model": model,
                "effort": effort,
            }
        )
        return conversation_id

    async def start_turn(self, conversation_id: str, text: str) -> Any:
        raise AssertionError("no test in this tier runs a turn")

    async def transcript(self, conversation_id: str) -> Sequence[TranscriptMessage]:
        return list(self.transcripts.get(conversation_id, ()))

    async def compact(self, conversation_id: str, *, keep_last: int, summary: str) -> None:
        self.compactions.append((conversation_id, keep_last, summary))

    def interrupt(self, conversation_id: str) -> None:
        return None


class FakeSummariser:
    """``SummariserPort``. ``text=None`` is "no internal connection"."""

    def __init__(self, text: str | None = "A summary.") -> None:
        self.text = text
        self.asked: list[str] = []

    async def summarise(self, text: str, *, hint: str) -> str | None:
        self.asked.append(text)
        return self.text


class FakeEarlierTasks:
    """``EarlierTasksPort`` — the run's earlier tasks, canned."""

    def __init__(self, items: Sequence[EarlierTask] = ()) -> None:
        self.items = list(items)
        self.asked: list[tuple[str, str]] = []

    async def earlier(self, run_id: str, before_attempt_id: str) -> Sequence[EarlierTask]:
        self.asked.append((run_id, before_attempt_id))
        return list(self.items)


class FakeInputStore:
    """``InputStorePort`` over a dict, with the real store's ref rules."""

    def __init__(self) -> None:
        self.files: dict[tuple[str, str], bytes] = {}

    def write_input(
        self,
        run_id: str,
        filename: str,
        content: bytes,
        *,
        taken: frozenset[str] = frozenset(),
    ) -> tuple[str, int, str]:
        name = pathlib.PurePosixPath(filename.replace("\\", "/")).name
        candidate = name
        counter = 2
        while candidate in taken:
            stem = pathlib.PurePosixPath(name).stem
            suffix = pathlib.PurePosixPath(name).suffix
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        self.files[(run_id, candidate)] = content
        # The third value is where the NODE is told the file is — absolute,
        # because an upload lands beside the working directory, not inside it.
        return candidate, len(content), f"/runs/{run_id}/inputs/{candidate}"

    def delete_input(self, run_id: str, ref: str) -> None:
        self.files.pop((run_id, ref), None)


@dataclass(frozen=True)
class FakeMountedRepo:
    path: str
    mount: str


class FakeRepoMounts:
    """``RepoMountPort`` — records what was mounted and what was given back."""

    def __init__(self, *, fail: Exception | None = None, mount: str = "worktree") -> None:
        self.fail = fail
        self.mount_kind = mount
        self.mounted: dict[str, str] = {}
        self.unmounted: list[tuple[str, str, str]] = []

    async def mount(
        self, run_id: str, source: str, *, taken: frozenset[str] = frozenset()
    ) -> FakeMountedRepo:
        if self.fail is not None:
            raise self.fail
        name = source.rstrip("/").rsplit("/", 1)[-1]
        counter = 2
        while name in taken:
            name = f"{source.rstrip('/').rsplit('/', 1)[-1]}-{counter}"
            counter += 1
        path = f"/fake/workflows/{run_id}/workspace/{name}"
        self.mounted[path] = source
        return FakeMountedRepo(path=path, mount=self.mount_kind)

    async def unmount(self, run_id: str, *, source: str, path: str, mount: str) -> None:
        self.mounted.pop(path, None)
        self.unmounted.append((source, path, mount))


class FakeAudit:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    async def record(
        self,
        event_type: str,
        *,
        actor: str,
        subject_kind: str | None = None,
        subject_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.records.append(
            (
                event_type,
                {
                    "actor": actor,
                    "subject_kind": subject_kind,
                    "subject_name": subject_name,
                    "detail": detail or {},
                },
            )
        )

    def types(self) -> list[str]:
        return [event_type for event_type, _ in self.records]


class FakeMachine:
    def __init__(self, machine_id: str = "machine-a") -> None:
        self.machine_id = machine_id

    def current(self) -> str:
        return self.machine_id


class FakeTemplates:
    """``ResourceService.get``'s shape, over a dict of configs keyed by NAME.

    The real service is addressed by uid, so this is too — but a test that had
    to invent a uid for every fixture would read about identity rather than
    about runs. ``uid_of`` derives a stable one from the name, which keeps the
    fixtures legible while the code under test still only ever holds a uid.
    """

    def __init__(self, configs: dict[str, dict[str, Any]]) -> None:
        self.configs = configs
        #: Workflows switched off. Enabled is what decides whether new runs may
        #: start, so a fake that could not be switched off could not
        #: exercise the refusal.
        self.disabled: set[str] = set()

    def disable(self, name: str) -> None:
        self.disabled.add(name)

    @staticmethod
    def uid_of(name: str) -> str:
        """The uid this fake gives the template called ``name``."""
        return f"wfuid-{name}"

    async def get(self, uid: str) -> Resource:
        name = uid.removeprefix("wfuid-")
        config = self.configs.get(name) if uid.startswith("wfuid-") else None
        if config is None:
            raise ResourceNotFound(uid)
        return Resource(
            id=1,
            uid=uid,
            kind="workflow",
            name=name,
            description=None,
            config=config,
            enabled=name not in self.disabled,
            created_at=NOW,
            updated_at=NOW,
        )


class RecordingDispatcher:
    """Stands in for the driver: records the dispatch and does nothing else."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, dispatch: Any) -> None:
        self.calls.append(dispatch)

    @property
    def last(self) -> Any:
        return self.calls[-1]


def approval_expiry(minutes: int = 30) -> datetime:
    return NOW + timedelta(minutes=minutes)


def new_id() -> str:
    return uuid4().hex


def _copy[T](row: T) -> T:
    from dataclasses import replace

    return replace(row)  # type: ignore[type-var]
