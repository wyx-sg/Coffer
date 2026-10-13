"""Wire models for the knowledge changes feed and a collection's description
(spec knowledge "Follow edits across collections in one feed", "Undo a
knowledge delete from its toast").

Each mirrors a value object in ``domain.knowledge.history``. A change is one
vault commit that touched ``knowledge/``, named by its commit id (``version``)
and by the writer its trailers record.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from coffer.application.knowledge.tidy_service import TidyStatus
from coffer.domain.knowledge.history import WRITER_DISK, WRITERS, Change

Writer = Literal["user", "agent", "curation", "sync", "disk", "daemon"]
DocumentStatus = Literal["added", "modified", "removed"]


class DocumentChangeOut(BaseModel):
    """One document a change touched."""

    path: str = Field(description="Knowledge-root-relative document path.")
    status: DocumentStatus
    added: int = Field(description="Lines added.")
    removed: int = Field(description="Lines removed.")


class ChangeOut(BaseModel):
    """One change to knowledge: one commit naming its writer."""

    version: str = Field(
        description="The change's id (its commit), what a restore of a delete takes."
    )
    time: datetime
    writer: Writer = Field(
        description="`user` a person; `agent` an agent whose material became a document on "
        "arrival; `curation` a change Coffer's retired curation pass made, kept in the "
        "history; `sync` another machine's change; `disk` an edit made outside Coffer "
        "(a person's editor, an agent's file tools); `daemon` Coffer adopting an inbox file "
        "as a source, or a layout commit an older version made (operation `layout`)."
    )
    operation: str = Field(
        description="`save`, `delete`, `promote`, `restore`, `edit`, `sync`, `create`, `rename`, "
        "`remove`, `layout`, `baseline` or `tidy` (one tidy an agent did, its report the "
        "summary); a change a retired curation pass made also reads `pass`, `submit` or `undo`."
    )
    summary: str
    actor: str | None = Field(default=None, description="The audit actor of the operation.")
    agent: str | None = Field(
        default=None,
        description="The agent that wrote it (writer `agent`).",
    )
    collections: list[str] = Field(description="The collections the change touched.")
    item: str | None = Field(default=None, description="The item a retired curation pass curated.")
    status: str | None = Field(
        default=None,
        description="A tidy's `reported` (its agent finished it with a report) or `expired` "
        "(Coffer closed it after its collection sat unchanged); a retired curation pass's "
        "outcome status.",
    )
    restored_from: str | None = None
    undoes: str | None = None
    documents: list[DocumentChangeOut]


def change_out(change: Change) -> ChangeOut:
    meta = change.meta
    return ChangeOut(
        version=change.version,
        time=change.time,
        # Any writer the knowledge feed does not name is Coffer acting on the
        # files outside a knowledge operation, which the contract names ``disk``.
        writer=meta.writer if meta.writer in WRITERS else WRITER_DISK,  # type: ignore[arg-type]
        operation=meta.operation,
        summary=meta.summary,
        actor=meta.actor,
        agent=meta.agent,
        collections=list(change.collections),
        item=meta.item,
        status=meta.status,
        restored_from=meta.restored_from,
        undoes=meta.undoes,
        documents=[
            DocumentChangeOut(path=d.path, status=d.status, added=d.added, removed=d.removed)  # type: ignore[arg-type]
            for d in change.documents
        ],
    )


class CollectionDescribeIn(BaseModel):
    """A collection's new description: its README's opening paragraph."""

    # Stripped before the length check: a whitespace-only description is empty.
    description: str = Field(min_length=1, max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True)


class ChangesOut(BaseModel):
    """Recent changes across collections, newest first."""

    changes: list[ChangeOut]
    next_cursor: str | None = Field(
        default=None, description="Pass back as `cursor` for the next page; null on the last."
    )


class TidyStatusOut(BaseModel):
    """Where a collection's tidy stands ("Record a tidy as one change")."""

    collection: str
    running: bool
    started_at: str | None = Field(
        default=None, description="When the open tidy started (ISO 8601, UTC); null when none is."
    )


def tidy_status_out(status: TidyStatus) -> TidyStatusOut:
    started = (
        datetime.fromtimestamp(status.started_at, tz=UTC).isoformat()
        if status.started_at is not None
        else None
    )
    return TidyStatusOut(collection=status.collection, running=status.running, started_at=started)


class TidyFinishIn(BaseModel):
    """The agent's report on the tidy it finished."""

    summary: str = Field(
        default="",
        max_length=20000,
        description="Which sources it integrated or skipped, what it merged, split, corrected "
        "and deleted, and what it left for the person to decide.",
    )


class TidyFinishOut(BaseModel):
    change: ChangeOut | None = Field(
        default=None, description="The tidy's one change; null when it changed nothing."
    )


class UndoIn(BaseModel):
    """Undo a change ("Undo a tidy")."""

    force: bool = Field(
        default=False,
        description="Undo even when a file was edited after the change, discarding those edits.",
    )
