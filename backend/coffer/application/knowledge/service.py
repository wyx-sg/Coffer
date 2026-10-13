"""The knowledge layer's one service.

Every operation resolves to a filesystem operation over ``~/.coffer/vault/knowledge/``
(spec knowledge "Store each collection as one tree of Markdown files"). New knowledge
arrives as **material**, which becomes a source under ``sources/`` on the spot ("Promote
submitted material at once"); a file dropped into a hidden ``.inbox/`` is promoted by the
next sweep. Every collection is served to every caller ("Serve every collection to every
agent"); a **linked folder** is only read (``infrastructure/knowledge/linked.py``).
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.recording import recording, writer_of
from coffer.application.resource_service import ResourceService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.config import linked_folder
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
    CollectionIsLinked,
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
from coffer.infrastructure.knowledge import (
    assets,
    catalogue,
    collection_files,
    fs,
    inbox,
    linked,
    paths,
    source_imports,
    wiki_reads,
)
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
        """Every registered collection, linked folders included, in name order: the
        registry is the authority, not the directory ("Create collections only deliberately")."""
        return sorted(r.name for r in await self.all_rows())

    async def all_rows(self) -> list[Resource]:
        """Every collection, the linked folders included."""
        return await self._resources.list(kind=KIND_KNOWLEDGE)

    async def collection_rows(self) -> list[Resource]:  # the sweep walks these directories
        """The collections Coffer keeps, under the knowledge root. A linked
        folder is left out: nothing Coffer runs may write into it (ADR
        linked-knowledge-folders-are-read-only-and-machine-local)."""
        return [r for r in await self.all_rows() if linked_folder(r.config) is None]

    async def linked_rows(self) -> list[Resource]:
        return [r for r in await self.all_rows() if linked_folder(r.config) is not None]

    async def owned_collection(self, uid: str) -> Resource:
        """:meth:`collection`, refused for a linked folder: what a write, a
        tidy, a check or the history asks for."""
        row = await self.collection(uid)
        if linked_folder(row.config) is not None:
            raise CollectionIsLinked(row.name)
        return row

    async def collection(self, uid: str) -> Resource:
        """One collection's row, by the identity that survives a rename. Raises
        ``ResourceNotFound`` for an absent uid, ``CollectionNotFound`` for another kind."""
        row = await self._resources.get(uid)
        if row.kind != KIND_KNOWLEDGE:
            raise CollectionNotFound(row.name)
        return row

    async def require_collection(self, relpath: str) -> Resource:
        """The registered collection ``relpath`` names: its row, so a write has both
        the name for its path and the identity a rename cannot move for its audit."""
        row = await self.find_collection(relpath)
        if linked_folder(row.config) is not None:
            raise CollectionIsLinked(row.name)
        return row

    async def find_collection(self, relpath: str) -> Resource:
        """The collection ``relpath`` names, a linked folder included: what a read asks
        for. A collection Coffer keeps wins a name both hold (only a sync does that)."""
        name = paths.collection_of(relpath)
        rows = [r for r in await self.all_rows() if r.name == name]
        rows.sort(key=lambda r: linked_folder(r.config) is not None)
        if not rows:
            raise CollectionNotFound(name)
        return rows[0]

    async def create_collection(
        self,
        name: str,
        *,
        actor: str,
        description: str | None = None,
    ) -> CollectionEntry:
        """Register a collection and create its directory and README — only ever on
        purpose (see "Create collections only deliberately")."""
        directory = paths.collection_dir(name)
        if directory.exists() or name in await self.collection_names():
            raise CollectionExists(name)
        registered = await self.register_row(name, actor=actor)
        meta = CommitMeta(WRITER_USER, OP_CREATE, f"Create collection {name}", actor=actor)
        async with recording(self.history, meta) as tx:
            fs.create_collection_dir(name)
            readme = collection_files.default_readme(name, description)
            paths.readme_path(name).write_text(readme, encoding="utf-8")
            tx.touch(name)
        await self.catalogue_changed()
        return CollectionEntry(
            uid=registered.uid,
            name=name,
            description=catalogue.readme_description(name),
            folder_path=str(paths.collection_dir(name)),
        )

    async def register_row(
        self, name: str, *, actor: str, config: dict[str, object] | None = None
    ) -> Resource:
        """The collection's ``resources`` row; its description lives in the README.
        ``config`` names a linked folder (``linking.py``)."""
        return await self._resources.register(
            kind=KIND_KNOWLEDGE,
            name=name,
            config=config or {},
            actor=actor,
            allow_lifecycle_kind=True,
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
        owned = [
            dataclasses.replace(c, uid=row_by_name[c.name].uid)
            for c in catalogue.list_collections()
            if c.name in row_by_name
        ]
        return owned + await self._linked_entries()

    async def _linked_entries(self) -> list[CollectionEntry]:
        owned = await self._owned_names()
        rows = sorted(await self.linked_rows(), key=lambda r: r.name)
        return [
            await asyncio.to_thread(
                linked.collection_entry, r.uid, r.name, linked_folder(r.config) or ""
            )
            for r in rows
            if r.name not in owned
        ]

    async def _owned_names(self) -> set[str]:
        return {r.name for r in await self.collection_rows()}

    # ----- reading, for the human surfaces -----------------------------

    async def list_level(self, relpath: str) -> CatalogueLevel:
        """One level of one collection, for the page and the CLI — never an agent's
        retrieval path (see "Expose exactly one knowledge tool")."""
        row = await self.find_collection(relpath)
        folder = linked_folder(row.config)
        if folder is not None:
            return await asyncio.to_thread(linked.list_level, row.name, folder, relpath)
        return catalogue.list_level(relpath)

    async def read(self, relpath: str) -> KnowledgeFile:
        """A document, for the human surfaces. A hidden path, the inbox included,
        is refused by the path guard."""
        row = await self.find_collection(relpath)
        folder = linked_folder(row.config)
        if folder is not None:
            return await asyncio.to_thread(linked.read_file, row.name, folder, relpath)
        file = fs.read_file(relpath)
        return await asyncio.to_thread(wiki_reads.describe, file)

    async def check(self, uid: str) -> CollectionEntry:
        """One collection's entry with its mechanical findings (spec knowledge
        "Check a collection mechanically on every read"). Computed on every call
        from the files; nothing is stored. A linked folder has no wiki rules
        to check, so it is refused."""
        row = await self.owned_collection(uid)
        directory = paths.collection_dir(row.name)
        if not directory.is_dir():
            raise CollectionNotFound(row.name)
        entry = await asyncio.to_thread(catalogue.collection_entry, directory)
        return dataclasses.replace(entry, uid=row.uid)

    async def files(self, uid: str) -> tuple[FileEntry, ...]:
        """Every file of one collection with its title, type and waiting mark,
        for the collection page's Contents (spec knowledge "Show a collection's
        contents by page type"). Read off disk on every call; a linked
        folder's Markdown files, each with its title."""
        row = await self.collection(uid)
        folder = linked_folder(row.config)
        if folder is not None:
            return await asyncio.to_thread(linked.walk_files, row.name, folder)
        directory = paths.collection_dir(row.name)
        if not directory.is_dir():
            raise CollectionNotFound(row.name)
        return await asyncio.to_thread(catalogue.walk_files, directory)

    async def catalogue(self) -> list[tuple[CollectionEntry, tuple[FileEntry, ...]]]:
        """Every registered collection with every document in it, linked
        folders after the collections Coffer keeps.

        The one place the corpus is read all at once, for skill rendering (see
        "Merge the manual and the catalogue in the skill body"): one reading
        serves every agent, because every agent is told the same thing.
        """
        registered = await self._owned_names()
        owned = [
            (entry, catalogue.walk_files(paths.collection_dir(entry.name)))
            for entry in catalogue.list_collections()
            if entry.name in registered
        ]
        shared = [
            (entry, linked.walk_files(entry.name, entry.folder_path))
            for entry in await self._linked_entries()
        ]
        return owned + shared

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
        extra: Mapping[str, Any] | None = None,
        files: Mapping[str, bytes] | None = None,
        supersede: Sequence[str] = (),
    ) -> Submission:
        """Add new material to a collection ("Promote submitted material at once"):
        a source under ``sources/`` on the spot, waiting until an agent compiles it.
        ``extra`` adds frontmatter keys; ``files`` (knowledge-root-relative path to
        bytes, an upload's pictures) land in the same commit, as does marking each
        source in ``supersede`` replaced by the new one (a page imported again)."""
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
            for relpath, data in (files or {}).items():
                tx.touch(relpath)
                assets.write_bytes(relpath, data)
            name = inbox.submit_material(
                row.name,
                title=title,
                description=description,
                body=body,
                actor=actor_kind,
                extra=extra,
            )
            tx.touch(f"{row.name}/{paths.INBOX_DIR_NAME}/{name}")
            document = inbox.promote(row.name, name)
            tx.touch(document.path)
            for older in supersede:
                tx.touch(older)
                source_imports.mark_superseded(older, PurePosixPath(document.path).stem)
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
        # Only ever handed a collection Coffer keeps: ``kind.py`` leaves a
        # linked folder's files alone when its row is deleted.
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
