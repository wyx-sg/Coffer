"""Value objects for a collection's history (spec knowledge "Keep every
document's history and undo a pass as a whole", "Follow knowledge changes
across collections").

Knowledge lives inside the vault repository under ``knowledge/``, so its
history is the vault's history of that directory: every accepted write is one
vault commit naming its writer (ADR
every-vault-write-is-a-validated-commit-naming-its-writer), and its trailers are
the vault's :class:`~coffer.domain.vault.writers.CommitMeta`. These types are
what a surface reads back out of it, with every path knowledge-root-relative:
one commit as a :class:`Change`, the documents it touched as
:class:`DocumentChange`, one document's version of it as
:class:`DocumentVersion`, and the items still waiting in an inbox — which are
not changes yet — as :class:`WaitingItem`.

Nothing here is persisted by this layer: git is the record, and these are the
shape of an answer read from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from coffer.domain.vault.history import ADDED, MODIFIED, REMOVED
from coffer.domain.vault.writers import (
    OP_BASELINE,
    OP_CREATE,
    OP_DELETE,
    OP_EDIT,
    OP_RENAME,
    OP_RESTORE,
    OP_SYNC,
    WRITER_AGENT,
    WRITER_CURATION,
    WRITER_DISK,
    WRITER_SYNC,
    WRITER_USER,
    CommitMeta,
)

#: The vault's writers a knowledge change names. ``user`` — a person, through
#: the page, the CLI or the API; ``agent`` — an agent whose submission became a
#: document on arrival; ``curation`` — Coffer's curation pass; ``sync`` — a
#: change another machine made, applied by vault sync; ``disk`` — a change
#: found in the tree that no Coffer operation made (a person's own editor, an
#: agent's file tools).
WRITERS = (WRITER_USER, WRITER_AGENT, WRITER_CURATION, WRITER_SYNC, WRITER_DISK)

#: What the change was — knowledge's own operation words beside the vault's.
#: A curation pass is ``pass``; a person's save of a body ``save``; material
#: promoted to a document on arrival ``promote`` (material left waiting in the
#: inbox: ``submit``); the rest name themselves.
OP_SAVE = "save"
OP_SUBMIT = "submit"
OP_PROMOTE = "promote"
OP_PASS = "pass"
OP_UNDO = "undo"
OP_REMOVE = "remove"


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
    meta: CommitMeta
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


__all__ = [
    "ADDED",
    "MODIFIED",
    "OP_BASELINE",
    "OP_CREATE",
    "OP_DELETE",
    "OP_EDIT",
    "OP_PASS",
    "OP_PROMOTE",
    "OP_REMOVE",
    "OP_RENAME",
    "OP_RESTORE",
    "OP_SAVE",
    "OP_SUBMIT",
    "OP_SYNC",
    "OP_UNDO",
    "REMOVED",
    "WRITERS",
    "WRITER_AGENT",
    "WRITER_CURATION",
    "WRITER_DISK",
    "WRITER_SYNC",
    "WRITER_USER",
    "Change",
    "ChangeDetail",
    "ChangesPage",
    "DocumentChange",
    "DocumentDiff",
    "DocumentVersion",
    "WaitingItem",
]
