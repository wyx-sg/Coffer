"""Value objects for a collection's history (spec knowledge "Keep every
document's history and undo a pass as a whole", "Follow knowledge changes
across collections").

Every accepted write to a collection is one git commit naming its writer. These
types are what a surface reads back out of that history: one commit as a
:class:`Change`, the documents it touched as :class:`DocumentChange`, one
document's version of it as :class:`DocumentVersion`, and the items still
waiting in an inbox — which are not changes yet — as :class:`WaitingItem`.

Nothing here is persisted by this layer: git is the record, and these are the
shape of an answer read from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: Who made a change. ``user`` — a person, through the page, the CLI or the
#: API; ``agent`` — an agent whose submission became a document on arrival;
#: ``curation`` — Coffer's curation pass; ``sync`` — a change another machine
#: made, applied by vault sync; ``disk`` — a change found in the tree that no
#: Coffer operation made (a person's own editor, an agent's file tools).
WRITER_USER = "user"
WRITER_AGENT = "agent"
WRITER_CURATION = "curation"
WRITER_SYNC = "sync"
WRITER_DISK = "disk"

WRITERS = (WRITER_USER, WRITER_AGENT, WRITER_CURATION, WRITER_SYNC, WRITER_DISK)

#: What the change was. A curation pass is ``pass``; a person's save of a body
#: ``save``; material promoted to a document on arrival ``promote`` (material
#: left waiting in the inbox: ``submit``); the rest name themselves.
OP_SAVE = "save"
OP_DELETE = "delete"
OP_SUBMIT = "submit"
OP_PROMOTE = "promote"
OP_PASS = "pass"
OP_RESTORE = "restore"
OP_UNDO = "undo"
OP_EDIT = "edit"
OP_SYNC = "sync"
OP_CREATE = "create"
OP_RENAME = "rename"
OP_REMOVE = "remove"
OP_BASELINE = "baseline"

#: How a document fared in one change.
ADDED = "added"
MODIFIED = "modified"
REMOVED = "removed"


@dataclass(frozen=True)
class ChangeMeta:
    """What a commit says about itself, written as its trailers.

    ``actor`` is the audit actor of the operation; ``agent`` names an agent —
    the writer itself when ``writer`` is ``agent``, and for a curation pass the
    author of the item it curated (``user`` when a person submitted it).
    """

    writer: str
    operation: str
    summary: str
    actor: str | None = None
    agent: str | None = None
    collection: str | None = None
    item: str | None = None
    status: str | None = None
    restored_from: str | None = None
    undoes: str | None = None


@dataclass(frozen=True)
class DocumentChange:
    """One document a change touched, with its line counts."""

    path: str
    status: str
    added: int = 0
    removed: int = 0


@dataclass(frozen=True)
class Change:
    """One commit of a collection's history."""

    version: str
    time: datetime
    meta: ChangeMeta
    documents: tuple[DocumentChange, ...] = field(default_factory=tuple)

    @property
    def collections(self) -> tuple[str, ...]:
        """The collections this change touched, in first-seen order."""
        seen: list[str] = []
        for doc in self.documents:
            head = doc.path.split("/", 1)[0]
            if head not in seen:
                seen.append(head)
        if not seen and self.meta.collection:
            seen.append(self.meta.collection)
        return tuple(seen)


@dataclass(frozen=True)
class DocumentVersion:
    """One version of one document: the change that produced it."""

    change: Change
    path: str
    #: True when this change removed the document.
    removed: bool = False


@dataclass(frozen=True)
class DocumentDiff:
    """What one change did to one document, as a unified diff."""

    path: str
    status: str
    diff: str
    added: int = 0
    removed: int = 0


@dataclass(frozen=True)
class ChangeDetail:
    """One change in full: every document it touched, each with its diff."""

    change: Change
    diffs: tuple[DocumentDiff, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WaitingItem:
    """An item still waiting in a collection's inbox — not a change yet."""

    collection: str
    path: str
    title: str
    #: Who submitted it: an agent's name, or ``user``.
    submitted_by: str
    submitted_at: str


@dataclass(frozen=True)
class ChangesPage:
    """One page of the recent-changes feed, with the items still waiting."""

    changes: tuple[Change, ...]
    waiting: tuple[WaitingItem, ...]
    next_cursor: str | None = None
