"""The knowledge layer's one service.

Every operation resolves to a filesystem operation over ``~/.coffer/vault/knowledge/``. A
collection is one tree of documents that a person and the agents write together (spec
knowledge "Store each collection as one tree of Markdown files"). What this layer adds on
top of the directory is the one rule about *how new knowledge arrives*: an upload
submits **material**, which becomes a document at the collection root on the spot
(see "Promote submitted material at once"). A file an agent drops into a collection's
hidden ``.inbox/`` is promoted the same way by the next sweep.

What it does *not* add is a gate of any kind on the corpus. Every registered
collection is served to every caller, agent or person alike (see "Serve every
collection to every agent"): the kind cannot be switched off, so a collection
leaves an agent's view only by being deleted.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.recording import recording, writer_of
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.entry import (
    ACTOR_AGENT,
    CatalogueLevel,
    CollectionEntry,
    FileEntry,
    KnowledgeFile,
    Submission,
)
from coffer.domain.knowledge.errors import (
    CollectionExists,
    CollectionNotFound,
)
from coffer.domain.knowledge.history import (
    OP_CREATE,
    OP_DELETE,
    OP_PROMOTE,
    OP_REMOVE,
    OP_RENAME,
    WRITER_USER,
)
from coffer.domain.resource import Resource
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge import catalogue, fs, inbox, paths, wiki
from coffer.infrastructure.knowledge.history import KnowledgeHistory

logger = logging.getLogger(__name__)

#: Called when the set of collections changes, so the skill that carries
#: the catalogue can be re-rendered (spec knowledge "Deliver the guide as the shared-master link").
CatalogueChanged = Callable[[], Awaitable[object]]


KIND_KNOWLEDGE = "knowledge"


class KnowledgeService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        on_catalogue_changed: CatalogueChanged | None = None,
        history: KnowledgeHistory | None = None,
        announce: Callable[[str], None] | None = None,
    ) -> None:
        # Told a collection's uid when its files change outside a resource write.
        self._announce = announce
        # Every write below is one commit naming its writer (see "Commit every
        # knowledge write naming its writer"); None records nothing.
        self.history = history
        self._resources = resources
        self._audit = audit
        # Fired when the set of collections changes, so Coffer's own skill —
        # which carries the catalogue — is re-rendered rather than going stale
        # until the next boot or sweep. Injected, because what renders
        # it lives outside this kind.
        self._on_catalogue_changed = on_catalogue_changed

    def announce(self, collection_uid: str) -> None:
        """Say that a collection's documents changed."""
        if self._announce is not None:
            self._announce(collection_uid)

    @property
    def audit(self) -> AuditService:
        """The audit port, for the sweep that records what it adopted."""
        return self._audit

    # ----- collections -------------------------------------------------

    async def collection_names(self) -> list[str]:
        """Every registered collection, in name order.

        The registry is the authority, not the directory: a folder nobody registered is
        not a collection (see "Create collections only deliberately"), and every one is
        served whether or not its row is enabled (see "Serve every collection to every agent").
        """
        return sorted(r.name for r in await self.collection_rows())

    async def collection_rows(self) -> list[Resource]:  # the sweep walks these directories
        return await self._resources.list(kind=KIND_KNOWLEDGE)

    async def collection(self, uid: str) -> Resource:
        """One collection's row, by the identity that survives a rename.

        The way anything inside the daemon reaches a collection: the
        sweep and a route all hold the uid and read the directory name off the
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
        for row in await self.collection_rows():
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
        meta = CommitMeta(WRITER_USER, OP_CREATE, f"Create collection {name}", actor=actor)
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
        row_by_name = {r.name: r for r in await self.collection_rows()}
        return [
            dataclasses.replace(c, uid=row_by_name[c.name].uid)
            for c in catalogue.list_collections()
            if c.name in row_by_name
        ]

    # ----- reading, for the human surfaces -----------------------------

    async def list_level(self, relpath: str) -> CatalogueLevel:
        """One level of one collection, for the page and the CLI — never an agent's
        retrieval path (see "Expose exactly one knowledge tool")."""
        await self.require_collection(relpath)
        return catalogue.list_level(relpath)

    async def read(self, relpath: str) -> KnowledgeFile:
        """A document, for the human surfaces. A hidden path, the inbox included,
        is refused by the path guard."""
        await self.require_collection(relpath)
        file = fs.read_file(relpath)
        return await asyncio.to_thread(wiki.describe, file)

    async def check(self, uid: str) -> CollectionEntry:
        """One collection's entry with its mechanical findings (spec knowledge
        "Check a collection mechanically on every read"). Computed on every call
        from the files; nothing is stored."""
        row = await self.collection(uid)
        directory = paths.collection_dir(row.name)
        if not directory.is_dir():
            raise CollectionNotFound(row.name)
        entry = await asyncio.to_thread(catalogue.collection_entry, directory)
        return dataclasses.replace(entry, uid=row.uid)

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
        original: tuple[str, bytes] | None = None,
    ) -> Submission:
        """Add new material to a collection (see "Promote submitted
        material at once").

        The material becomes a source under the collection's ``sources/`` on the
        spot, with ``original`` — an upload's own file name and bytes — kept
        beside it ("Keep every upload as a source with its original"). It waits
        there until the person's agent compiles it into pages.
        """
        row = await self.require_collection(collection)
        meta = CommitMeta(
            writer_of(actor_kind),
            OP_PROMOTE,
            f"Add {title}",
            actor=actor,
            agent=actor if actor_kind == ACTOR_AGENT else None,
            collection=row.name,
        )
        async with recording(self.history, meta) as tx:
            name = inbox.submit_material(
                row.name, title=title, description=description, body=body, actor=actor_kind
            )
            tx.touch(f"{row.name}/{paths.INBOX_DIR_NAME}/{name}")
            document, kept = inbox.promote(row.name, name, original=original)
            tx.touch(document.path)
            if kept is not None:
                tx.touch(kept)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_WRITTEN.value,
            resource=row,
            actor=actor,
            details={
                "title": title,
                "path": document.path,
                "description": description,
                "bytes": len(body.encode("utf-8")),
                "writer": actor_kind,
            },
        )
        self.announce(row.uid)
        # A new document is a new entry in the catalogue the skill carries.
        await self.catalogue_changed()
        return Submission(collection=row.name, title=title, document=document)

    async def delete_document(self, relpath: str, *, actor: str) -> None:
        """Remove a document. A person's action — no agent-facing tool deletes."""
        collection = await self.require_collection(relpath)
        async with recording(
            self.history, CommitMeta(WRITER_USER, OP_DELETE, f"Delete {relpath}", actor=actor)
        ) as tx:
            tx.touch(relpath)
            fs.delete_file(relpath)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_DELETED.value,
            resource=collection,
            actor=actor,
            details={"path": relpath},
        )

    # ----- lifecycle ---------------------------------------------------

    async def cleanup_collection(self, name: str) -> None:
        """Remove a collection's directory when its Resource is deleted."""
        async with recording(
            self.history,
            CommitMeta(WRITER_USER, OP_REMOVE, f"Remove collection {name}", collection=name),
        ) as tx:
            tx.touch(name)
            fs.remove_collection_dir(name)

    async def move_collection(self, old_name: str, new_name: str) -> None:
        """Move a collection's directory when its Resource is renamed; raises
        ``FileExistsError`` when the new name is taken on disk (see ``kind.py``)."""
        meta = CommitMeta(WRITER_USER, OP_RENAME, f"Rename collection {old_name} to {new_name}")
        async with recording(self.history, meta) as tx:
            tx.touch(old_name)
            fs.rename_collection_dir(old_name, new_name)
            tx.touch(new_name)
