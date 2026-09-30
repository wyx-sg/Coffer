"""The knowledge layer's one service.

Every operation resolves to a filesystem operation over ``~/.coffer/knowledge/``. A
collection is one tree of documents that a person and Coffer's curation pass write
together (spec knowledge "Store each collection as one tree of Markdown files"). What
this layer adds on top of the directory is the one rule about *how new knowledge
arrives*: every entrance — an upload, an agent's ``coffer__write``, the CLI — submits
**material**, which waits in the collection's hidden inbox until a pass folds it into
the documents (see "Submit every entrance's input as material"). With no internal model
to fold it, the material becomes a document of its own on the spot (see "Promote
material directly when no model is configured").

What it does *not* add is a gate of any kind on the corpus. Every registered
collection is served to every caller, agent or person alike (see "Serve every
collection to every agent"): the kind cannot be switched off, so a collection
leaves an agent's view only by being deleted.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.recording import recording, writer_of
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.entry import (
    ACTOR_AGENT,
    CatalogueLevel,
    CollectionEntry,
    FileEntry,
    GrepOutcome,
    KnowledgeFile,
)
from coffer.domain.knowledge.errors import (
    CollectionExists,
    CollectionNotFound,
    KnowledgeFileNotFound,
)
from coffer.domain.knowledge.history import (
    OP_CREATE,
    OP_DELETE,
    OP_PROMOTE,
    OP_REMOVE,
    OP_RENAME,
    OP_SAVE,
    OP_SUBMIT,
    WRITER_USER,
    ChangeMeta,
)
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, inbox, paths
from coffer.infrastructure.knowledge.grep import DEFAULT_MAX_MATCHES, RipgrepSearch
from coffer.infrastructure.knowledge.history import KnowledgeHistory

logger = logging.getLogger(__name__)

#: Called when the set of collections changes, so the skill that carries
#: the catalogue can be re-rendered (spec knowledge "Deliver the guide as the shared-master link").
CatalogueChanged = Callable[[], Awaitable[object]]

#: Whether a curation pass could merge material now — an internal model is configured.
#: When it cannot, material is promoted to a document as it stands rather than waiting
#: for a connection that may never come (see "Promote material directly when no model is
#: configured").
MergeAvailable = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class Submission:
    """What became of one piece of submitted material.

    ``document`` is set when the material was promoted on the spot, and is the
    document it became; ``pending`` is the inbox item's name when it waits for
    a pass instead. Exactly one of the two is set.
    """

    collection: str
    title: str
    document: KnowledgeFile | None = None
    pending: str | None = None


KIND_KNOWLEDGE = "knowledge"


class KnowledgeService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        search: RipgrepSearch | None = None,
        on_catalogue_changed: CatalogueChanged | None = None,
        merge_available: MergeAvailable | None = None,
        history: KnowledgeHistory | None = None,
    ) -> None:
        self._merge_available = merge_available
        # Every write below is one commit naming its writer (see "Keep every
        # document's history and undo a pass as a whole"); None records nothing.
        self.history = history
        self._resources = resources
        self._audit = audit
        self._search = search or RipgrepSearch()
        # Fired when the set of collections changes, so Coffer's own skill —
        # which carries the catalogue — is re-rendered rather than going stale
        # until the next boot or curation pass. Injected, because what renders
        # it lives outside this kind.
        self._on_catalogue_changed = on_catalogue_changed

    # ----- collections -------------------------------------------------

    async def collection_names(self) -> list[str]:
        """Every registered collection, in name order.

        The registry is the authority, not the directory: a folder nobody registered is
        not a collection (see "Create collections only deliberately"). Whether a row is
        stored enabled is not consulted — every collection is served (see "Serve every
        collection to every agent").
        """
        return sorted(r.name for r in await self._rows())

    async def _rows(self) -> list[Resource]:
        return await self._resources.list(kind=KIND_KNOWLEDGE)

    async def collection(self, uid: str) -> Resource:
        """One collection's row, by the identity that survives a rename.

        The way anything inside the daemon reaches a collection: a pass, a
        worker and a route all hold the uid and read the directory name off the
        row they get back. Raises ``ResourceNotFound`` for an absent uid, and
        ``CollectionNotFound`` for a row of another kind.
        """
        row = await self._resources.get(uid)
        if row.kind != KIND_KNOWLEDGE:
            raise CollectionNotFound(row.name)
        return row

    async def require_collection(self, relpath: str) -> Resource:
        """The registered collection ``relpath`` names.

        Hands back the **row**, not the name, because almost every caller needs
        both halves of it: the name to build a path with, and the resource
        itself to audit against. Resolving the label here once is what keeps
        the audit trail tied to an identity a rename cannot move, without every
        write path repeating the lookup.
        """
        name = paths.collection_of(relpath)
        for row in await self._rows():
            if row.name == name:
                return row
        raise CollectionNotFound(name)

    async def create_collection(
        self,
        name: str,
        *,
        actor: str,
        description: str | None = None,
    ) -> CollectionEntry:
        """Register a collection and create its directory.

        Deliberate creation is the whole point (see "Create collections only
        deliberately"): nothing here is reachable from a read or a write, so a typo
        cannot conjure a collection.
        """
        directory = paths.collection_dir(name)
        if directory.exists():
            raise CollectionExists(name)
        registered = await self.register_row(name, actor=actor)
        meta = ChangeMeta(WRITER_USER, OP_CREATE, f"Create collection {name}", actor=actor)
        async with recording(self.history, meta) as tx:
            fs.create_collection_dir(name)
            if description:
                readme = paths.readme_path(name)
                readme.write_text(f"# {name}\n\n{description}\n", encoding="utf-8")
            tx.touch(name)
        await self.catalogue_changed()
        return CollectionEntry(
            uid=registered.uid,
            name=name,
            description=catalogue.readme_description(name),
            folder_path=str(paths.collection_dir(name)),
        )

    async def register_row(self, name: str, *, actor: str) -> Resource:
        """The collection's ``resources`` row — without its description, which
        lives in the README (see "Read a collection's description from its README")."""
        return await self._resources.register(
            kind=KIND_KNOWLEDGE, name=name, config={}, actor=actor, allow_lifecycle_kind=True
        )

    async def catalogue_changed(self) -> None:
        """Every registered collection with every document in it — the one read of
        the whole corpus, for the skill (see "Merge the manual and the catalogue
        in the skill body")."""
        if self._on_catalogue_changed is None:
            return
        try:
            await self._on_catalogue_changed()
        except Exception:
            logger.warning("knowledge.catalogue_changed.notify_failed", exc_info=True)

    async def list_collections(self) -> list[CollectionEntry]:
        """The registered collections joined with the catalogue walk, each carrying
        the uid its routes address; a folder nobody registered is left out."""
        row_by_name = {r.name: r for r in await self._rows()}
        return [
            dataclasses.replace(c, uid=row_by_name[c.name].uid)
            for c in catalogue.list_collections()
            if c.name in row_by_name
        ]

    # ----- reading, for the human surfaces -----------------------------

    async def list_level(self, relpath: str) -> CatalogueLevel:
        """One level of one collection (or its ``.inbox``, see "Hide dot-prefixed
        entries except the inbox"), for the page and the CLI — never an agent's
        retrieval path (see "Expose exactly one knowledge tool")."""
        in_inbox = paths.inbox_parts(relpath)
        if in_inbox is not None:
            collection, item = in_inbox
            await self.require_collection(collection)
            if item is not None:
                raise KnowledgeFileNotFound(relpath)
            return catalogue.list_inbox(collection)
        await self.require_collection(relpath)
        return catalogue.list_level(relpath)

    async def read(self, relpath: str) -> KnowledgeFile:
        """A document, or an item waiting in a collection's inbox (read-only)."""
        in_inbox = paths.inbox_parts(relpath)
        if in_inbox is not None:
            collection, item = in_inbox
            await self.require_collection(collection)
            if item is None:
                raise KnowledgeFileNotFound(relpath)
            return inbox.read_material(collection, item)
        await self.require_collection(relpath)
        return fs.read_file(relpath)

    async def save_document(
        self, relpath: str, body: str, *, expected_fingerprint: str, actor: str
    ) -> KnowledgeFile:
        """Replace a document's body from the web UI, keeping its frontmatter.

        See "Save a document edited in the web UI". ``require_collection`` runs
        the path through the guard first, so an inbox item — or anything else
        hidden — is refused before the file is looked at.
        """
        collection = await self.require_collection(relpath)
        meta = ChangeMeta(WRITER_USER, OP_SAVE, f"Edit {relpath}", actor=actor)
        async with recording(self.history, meta) as tx:
            saved = fs.save_body(relpath, body, expected_fingerprint=expected_fingerprint)
            tx.touch(relpath)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_EDITED.value,
            resource=collection,
            actor=actor,
            details={"path": relpath},
        )
        return saved

    async def catalogue(self) -> list[tuple[CollectionEntry, tuple[FileEntry, ...]]]:
        """Every registered collection with every document in it.

        The one place the corpus is read all at once. It exists for skill rendering (see
        "Merge the manual and the catalogue in the skill body"), where handing the agent
        the entire catalogue is the point — the alternative, a level at a time through a
        tool, is what 448 sessions demonstrated an agent never reaches for. One reading
        serves every agent, because every agent is told the same thing.
        """
        registered = set(await self.collection_names())
        return [
            (entry, catalogue.walk_files(paths.collection_dir(entry.name)))
            for entry in catalogue.list_collections()
            if entry.name in registered
        ]

    # ----- new knowledge arriving ---------------------------------------

    async def submit(
        self,
        *,
        collection: str,
        title: str,
        description: str,
        body: str,
        actor_kind: str = ACTOR_AGENT,
        actor: str,
    ) -> Submission:
        """Add new knowledge to a collection (see "Submit every entrance's input as
        material").

        The material goes into the collection's inbox for a curation pass to fold into
        the documents. When no pass could — there is no internal model — it is promoted
        to a document of its own immediately, because knowledge that sits in a hidden
        directory waiting for a connection nobody configured is knowledge no agent can
        read (see "Promote material directly when no model is configured").
        """
        row = await self.require_collection(collection)
        can_merge = await self._can_merge()
        meta = ChangeMeta(
            writer_of(actor_kind),
            OP_SUBMIT if can_merge else OP_PROMOTE,
            f"{'Submit' if can_merge else 'Add'} {title}",
            actor=actor,
            agent=actor if actor_kind == ACTOR_AGENT else None,
            collection=row.name,
        )
        document: KnowledgeFile | None = None
        async with recording(self.history, meta) as tx:
            name = inbox.submit_material(
                row.name, title=title, description=description, body=body, actor=actor_kind
            )
            tx.touch(f"{row.name}/{paths.INBOX_DIR_NAME}/{name}")
            if not can_merge:
                document = inbox.promote(row.name, name)
                tx.touch(document.path)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_WRITTEN.value,
            resource=row,
            actor=actor,
            details={
                "title": title,
                # The inbox item, so a pass can name the agent who wrote it.
                "item": name,
                "path": document.path if document else None,
                "pending": document is None,
            },
        )
        if document is not None:
            return Submission(collection=row.name, title=title, document=document)
        return Submission(collection=row.name, title=title, pending=name)

    async def _can_merge(self) -> bool:
        if self._merge_available is None:
            return False
        try:
            return await self._merge_available()
        except Exception:
            # Unable to tell is treated as unable to merge: promoting keeps the
            # material readable, and a later edit is still curated by a sweep.
            logger.warning("knowledge.merge_available_failed", exc_info=True)
            return False

    async def delete_document(self, relpath: str, *, actor: str) -> None:
        """Remove a document. A person's action — no agent-facing tool deletes."""
        collection = await self.require_collection(relpath)
        async with recording(
            self.history, ChangeMeta(WRITER_USER, OP_DELETE, f"Delete {relpath}", actor=actor)
        ) as tx:
            tx.touch(relpath)
            fs.delete_file(relpath)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_DELETED.value,
            resource=collection,
            actor=actor,
            details={"path": relpath},
        )

    # ----- candidate selection, for curation ---------------------------

    async def match_documents(
        self,
        pattern: str,
        *,
        collection: str,
        max_matches: int = DEFAULT_MAX_MATCHES,
    ) -> GrepOutcome:
        """Literal matches among one collection's documents — curation's candidate
        selection (see "Assemble a pass from a bounded context"); the inbox is
        never searched, and no caller outside this process reaches it."""
        roots: list[pathlib.Path] = [paths.collection_dir(collection)]
        return await self._search.grep(roots, pattern, max_matches=max_matches)

    # ----- lifecycle ---------------------------------------------------

    async def cleanup_collection(self, name: str) -> None:
        """Remove a collection's directory when its Resource is deleted."""
        async with recording(
            self.history,
            ChangeMeta(WRITER_USER, OP_REMOVE, f"Remove collection {name}", collection=name),
        ) as tx:
            tx.touch(name)
            fs.remove_collection_dir(name)

    async def move_collection(self, old_name: str, new_name: str) -> None:
        """Move a collection's directory when its Resource is renamed; raises
        ``FileExistsError`` when the new name is taken on disk (see ``kind.py``)."""
        meta = ChangeMeta(WRITER_USER, OP_RENAME, f"Rename collection {old_name} to {new_name}")
        async with recording(self.history, meta) as tx:
            tx.touch(old_name)
            tx.touch(new_name)
            fs.rename_collection_dir(old_name, new_name)
