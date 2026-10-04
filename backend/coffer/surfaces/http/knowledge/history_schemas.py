"""Wire models for a collection's history (spec knowledge "Keep every
document's history", "Follow edits across
collections in one feed").

Each mirrors a value object in ``domain.knowledge.history``. A change is one
vault commit that touched ``knowledge/``, named by its commit id (``version``)
and by the writer its trailers record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.knowledge.history import (
    WRITER_DISK,
    WRITERS,
    Change,
    DocumentDiff,
    DocumentVersion,
)

Writer = Literal["user", "agent", "curation", "sync", "disk"]
DocumentStatus = Literal["added", "modified", "removed"]


class DocumentChangeOut(BaseModel):
    """One document a change touched."""

    path: str = Field(description="Knowledge-root-relative document path.")
    status: DocumentStatus
    added: int = Field(description="Lines added.")
    removed: int = Field(description="Lines removed.")


class ChangeOut(BaseModel):
    """One change to knowledge: one commit naming its writer."""

    version: str = Field(description="The change's id (its commit), what diff and restore take.")
    time: datetime
    writer: Writer = Field(
        description="`user` a person; `agent` an agent whose material became a document on "
        "arrival; `curation` a change Coffer's retired curation pass made, kept in the "
        "history; `sync` another machine's change; `disk` an edit made outside Coffer "
        "(a person's editor, an agent's file tools)."
    )
    operation: str = Field(
        description="`save`, `delete`, `promote`, `restore`, `edit`, `sync`, `create`, `rename`, "
        "`remove` or `baseline`; a change a retired curation pass made also reads "
        "`pass`, `submit` or `undo`."
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
        default=None, description="A retired curation pass's outcome status."
    )
    restored_from: str | None = None
    undoes: str | None = None
    documents: list[DocumentChangeOut]


def change_out(change: Change) -> ChangeOut:
    meta = change.meta
    return ChangeOut(
        version=change.version,
        time=change.time,
        # The vault's ``daemon`` writer (a layout upgrade touching knowledge)
        # is not a knowledge writer; it is Coffer acting on the files outside
        # any knowledge operation, which the contract names ``disk``.
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


class DocumentVersionOut(BaseModel):
    """One version of a document: the change that made it."""

    change: ChangeOut
    removed: bool = Field(description="True when this change removed the document.")


class DocumentHistoryOut(BaseModel):
    """A document's versions, newest first."""

    path: str
    versions: list[DocumentVersionOut]


def history_out(path: str, versions: list[DocumentVersion]) -> DocumentHistoryOut:
    return DocumentHistoryOut(
        path=path,
        versions=[
            DocumentVersionOut(change=change_out(v.change), removed=v.removed) for v in versions
        ],
    )


class DocumentDiffOut(BaseModel):
    """What one change did to one document, as a unified diff."""

    path: str
    status: DocumentStatus
    diff: str = Field(description="A unified diff; empty when the change made no textual change.")
    added: int
    removed: int


def diff_out(diff: DocumentDiff) -> DocumentDiffOut:
    return DocumentDiffOut(
        path=diff.path,
        status=diff.status,  # type: ignore[arg-type]
        diff=diff.diff,
        added=diff.added,
        removed=diff.removed,
    )


class VersionDiffOut(DocumentDiffOut):
    """One version's diff of one document."""

    version: str


class VersionBodyOut(BaseModel):
    """A document's body as one version left it, for Compare with current."""

    path: str
    version: str
    body: str


class CollectionDescribeIn(BaseModel):
    """A collection's new description: its README's opening paragraph."""

    # Stripped before the length check: a whitespace-only description is empty.
    description: str = Field(min_length=1, max_length=2000)
    model_config = ConfigDict(str_strip_whitespace=True)


class VersionRestoreIn(BaseModel):
    """Put one version of a document back, as a new change."""

    path: str = Field(min_length=1, description="Knowledge-root-relative document path.")
    version: str = Field(min_length=4, description="The version to restore.")


class ChangesOut(BaseModel):
    """Recent changes across collections, newest first."""

    changes: list[ChangeOut]
    next_cursor: str | None = Field(
        default=None, description="Pass back as `cursor` for the next page; null on the last."
    )
