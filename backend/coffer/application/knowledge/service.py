"""The knowledge layer's one service.

Every operation resolves to a filesystem operation over
``~/.coffer/knowledge/``. A collection is one tree of documents that a person
and Coffer's curation pass write together (spec knowledge FR-001). What this
layer adds on top of the directory is the one rule about *how new knowledge
arrives*: every entrance — an upload, an agent's ``coffer__write``, the CLI —
submits **material**, which waits in the collection's hidden inbox until a
pass folds it into the documents (FR-013). With no internal model to fold it,
the material becomes a document of its own on the spot (FR-029).

What it does *not* add is a per-caller view of the corpus. Every enabled
collection is served to every caller, agent or person alike; ``enabled`` is the
whole of the gate, and a disabled collection is simply not registered as far as
this layer is concerned.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from coffer.application.audit_service import AuditService
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
)
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.grep import DEFAULT_MAX_MATCHES, RipgrepSearch

logger = logging.getLogger(__name__)

#: Called when the set of collections changes, so the skill that carries
#: the catalogue can be re-rendered (spec knowledge FR-035).
CatalogueChanged = Callable[[], Awaitable[object]]

#: Whether a curation pass could merge material now — an internal model is
#: configured. When it cannot, material is promoted to a document as it stands
#: rather than waiting for a connection that may never come (FR-029).
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
    ) -> None:
        self._merge_available = merge_available
        self._resources = resources
        self._audit = audit
        self._search = search or RipgrepSearch()
        # Fired when the set of collections changes, so Coffer's own skill —
        # which carries the catalogue — is re-rendered rather than going stale
        # until the next boot or curation pass. Injected, because what renders
        # it lives outside this kind.
        self._on_catalogue_changed = on_catalogue_changed

    # ----- collections -------------------------------------------------

    async def enabled_collections(self) -> list[str]:
        """Every registered, enabled collection, in name order.

        The registry is the authority, not the directory: a folder nobody
        registered is not a collection (FR-008), and a disabled row's folder is
        one Coffer serves to no one until it is switched back on.
        """
        return sorted(r.name for r in await self._enabled_rows())

    async def _enabled_rows(self) -> list[Resource]:
        return await self._resources.list(kind=KIND_KNOWLEDGE, enabled=True)

    async def collection(self, uid: str) -> Resource:
        """One collection's row, by the identity that survives a rename.

        The way anything inside the daemon reaches a collection: a pass, a
        worker and a route all hold the uid and read the directory name off the
        row they get back. Raises ``ResourceNotFound`` for an absent uid, and
        ``CollectionNotFound`` for a row that exists but is switched off —
        which is the same answer :meth:`require_enabled` gives, because
        "disabled" and "not a collection as far as this layer is concerned" are
        one state here (FR-008).
        """
        row = await self._resources.get(uid)
        if not row.enabled or row.kind != KIND_KNOWLEDGE:
            raise CollectionNotFound(row.name)
        return row

    async def require_enabled(self, relpath: str) -> Resource:
        """The collection ``relpath`` names, once confirmed enabled.

        Hands back the **row**, not the name, because almost every caller needs
        both halves of it: the name to build a path with, and the resource
        itself to audit against. Resolving the label here once is what keeps
        the audit trail tied to an identity a rename cannot move, without every
        write path repeating the lookup.
        """
        name = paths.collection_of(relpath)
        for row in await self._enabled_rows():
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

        Deliberate creation is the whole point (FR-008): nothing here is
        reachable from a read or a write, so a typo cannot conjure a collection.
        """
        directory = paths.collection_dir(name)
        if directory.exists():
            raise CollectionExists(name)
        registered = await self._resources.register(
            kind=KIND_KNOWLEDGE,
            name=name,
            config={},
            actor=actor,
            # Deliberately not the description (FR-011): for this kind it lives
            # in the collection's own README, where the person browsing the
            # folder can see and change it. A copy in the row would be written
            # once, read by nothing, and wrong the moment they edited the file.
            allow_lifecycle_kind=True,
        )
        fs.create_collection_dir(name)
        if description:
            paths.readme_path(name).write_text(f"# {name}\n\n{description}\n", encoding="utf-8")
        await self.catalogue_changed()
        return CollectionEntry(
            uid=registered.uid, name=name, description=catalogue.readme_description(name)
        )

    async def catalogue_changed(self) -> None:
        """Tell whoever renders the catalogue that it moved.

        Never raises: the collection has already been created, deleted or
        switched by the time this runs, and a failure to re-render must not
        turn a completed operation into an error the caller sees. The next
        boot renders it anyway.
        """
        if self._on_catalogue_changed is None:
            return
        try:
            await self._on_catalogue_changed()
        except Exception:
            logger.warning("knowledge.catalogue_changed.notify_failed", exc_info=True)

    async def list_collections(self) -> list[CollectionEntry]:
        """The enabled collections, each carrying the uid its routes address.

        The catalogue is generated by walking the directory, so it knows names
        and counts but no identities; the registry knows identities. Joining
        them here — once, over rows already being read for the enabled filter —
        is what lets a caller act on a row it just rendered.
        """
        uid_by_name = {r.name: r.uid for r in await self._enabled_rows()}
        return [
            dataclasses.replace(c, uid=uid_by_name[c.name])
            for c in catalogue.list_collections()
            if c.name in uid_by_name
        ]

    # ----- reading, for the human surfaces -----------------------------

    async def list_level(self, relpath: str) -> CatalogueLevel:
        """One level of one collection, generated by walking the directory.

        This serves the web page and the CLI. It is **not** an agent's
        retrieval path — an agent reads the files themselves at the absolute
        paths its delivered skill carries (FR-033, FR-037).
        """
        await self.require_enabled(relpath)
        return catalogue.list_level(relpath)

    async def read(self, relpath: str) -> KnowledgeFile:
        await self.require_enabled(relpath)
        return fs.read_file(relpath)

    async def catalogue(self) -> list[tuple[CollectionEntry, tuple[FileEntry, ...]]]:
        """Every enabled collection with every document in it.

        The one place the corpus is read all at once. It exists for skill
        rendering (FR-037), where handing the agent the entire catalogue is the
        point — the alternative, a level at a time through a tool, is what 448
        sessions demonstrated an agent never reaches for. One reading serves
        every agent, because every agent is told the same thing.
        """
        enabled = set(await self.enabled_collections())
        return [
            (entry, catalogue.walk_files(paths.collection_dir(entry.name)))
            for entry in catalogue.list_collections()
            if entry.name in enabled
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
        """Add new knowledge to a collection (FR-013).

        The material goes into the collection's inbox for a curation pass to
        fold into the documents. When no pass could — there is no internal
        model — it is promoted to a document of its own immediately, because
        knowledge that sits in a hidden directory waiting for a connection
        nobody configured is knowledge no agent can read (FR-029).
        """
        row = await self.require_enabled(collection)
        name = fs.submit_material(
            row.name, title=title, description=description, body=body, actor=actor_kind
        )
        document: KnowledgeFile | None = None
        if not await self._can_merge():
            document = fs.promote(row.name, name)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_WRITTEN.value,
            resource=row,
            actor=actor,
            details={
                "title": title,
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
        collection = await self.require_enabled(relpath)
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
        """Literal matches among one collection's documents.

        Ripgrep survives the removal of ``coffer__grep`` as an *internal*
        mechanism: it is how a curation pass finds which existing documents a
        new material might belong to (FR-023). It is not reachable by any caller
        outside this process. The inbox is never searched: ripgrep skips hidden
        directories, and material there is not a document yet.
        """
        roots: list[pathlib.Path] = [paths.collection_dir(collection)]
        return await self._search.grep(roots, pattern, max_matches=max_matches)

    # ----- lifecycle ---------------------------------------------------

    async def cleanup_collection(self, name: str) -> None:
        """Remove a collection's directory when its Resource is deleted."""
        fs.remove_collection_dir(name)

    async def move_collection(self, old_name: str, new_name: str) -> None:
        """Move a collection's directory when its Resource is renamed.

        The other half of ``cleanup_collection``: the row's name is this
        layer's directory, so the framework hands the kind both labels and the
        directory follows. Raises ``FileExistsError`` when something already
        occupies the new name on disk — the kind turns that into the same
        collision the framework reports for a taken row (see ``kind.py``).
        """
        fs.rename_collection_dir(old_name, new_name)
