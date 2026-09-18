"""The knowledge layer's one service.

Every operation resolves to a filesystem operation over
``~/.coffer/knowledge/``. What this layer adds on top of the directory is
**which lane a caller may write** (FR-013, FR-021) — which is why every write
here names its lane. Nothing in this module can write ``topics/``; that belongs
to ``application.knowledge.curate``.

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
    UnsafeKnowledgePath,
)
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import catalogue, fs, paths
from coffer.infrastructure.knowledge.grep import DEFAULT_MAX_MATCHES, RipgrepSearch

logger = logging.getLogger(__name__)

#: Called when the set of collections changes, so the skill that carries
#: the catalogue can be re-rendered (spec knowledge FR-035).
CatalogueChanged = Callable[[], Awaitable[object]]

KIND_KNOWLEDGE = "knowledge"


class KnowledgeService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        search: RipgrepSearch | None = None,
        on_catalogue_changed: CatalogueChanged | None = None,
    ) -> None:
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
        """Register a collection, create its directory and both lanes.

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
        """One level of one lane, generated by walking the directory.

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
        """Every enabled collection with its whole ``topics/`` lane.

        The one place the corpus is read all at once. It exists for skill
        rendering (FR-037), where handing the agent the entire catalogue is the
        point — the alternative, a level at a time through a tool, is what 448
        sessions demonstrated an agent never reaches for. One reading serves
        every agent, because every agent is told the same thing.
        """
        enabled = set(await self.enabled_collections())
        return [
            (entry, catalogue.walk_files(paths.topics_dir(entry.name)))
            for entry in catalogue.list_collections()
            if entry.name in enabled
        ]

    # ----- writing the sources lane ------------------------------------

    async def write_source(
        self,
        *,
        title: str,
        description: str,
        body: str,
        collection: str | None = None,
        folder: str | None = None,
        relpath: str | None = None,
        actor_kind: str = ACTOR_AGENT,
        actor: str,
    ) -> KnowledgeFile:
        """Create a source in a collection, or replace the one at ``relpath``.

        ``collection`` plus an optional ``folder`` is what a caller names; the
        ``sources/`` segment is this layer's, not theirs, so no surface has to
        spell it and no caller can aim at the other lane by spelling it wrong.
        """
        if relpath is not None:
            target = await self.require_enabled(relpath)
            paths.require_lane(relpath, expected=paths.SOURCES_DIR_NAME)
            directory = None
        elif collection:
            target = await self.require_enabled(collection)
            directory = paths.lane_relpath(
                target.name, paths.SOURCES_DIR_NAME, *(folder or "").strip("/").split("/")
            )
        else:
            raise UnsafeKnowledgePath("", "a write needs a collection or a path")
        written = fs.write_file(
            directory=directory or "",
            title=title,
            description=description,
            body=body,
            actor=actor_kind,
            relpath=relpath,
        )
        await self._audit.record(
            AuditEventType.KNOWLEDGE_WRITTEN.value,
            resource=target,
            actor=actor,
            details={"path": written.path},
        )
        return written

    async def delete_source(self, relpath: str, *, actor: str) -> None:
        """Remove a source. A person's action — no agent-facing tool deletes."""
        collection = await self.require_enabled(relpath)
        paths.require_lane(relpath, expected=paths.SOURCES_DIR_NAME)
        fs.delete_file(relpath)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_DELETED.value,
            resource=collection,
            actor=actor,
            details={"path": relpath},
        )

    # ----- candidate selection, for curation ---------------------------

    async def match_topics(
        self,
        pattern: str,
        *,
        collection: str,
        max_matches: int = DEFAULT_MAX_MATCHES,
    ) -> GrepOutcome:
        """Literal matches inside one collection's ``topics/`` lane.

        Ripgrep survives the removal of ``coffer__grep`` as an *internal*
        mechanism: it is how a curation pass finds which existing documents a
        new source might belong to (FR-023). It is not reachable by any caller
        outside this process.
        """
        roots: list[pathlib.Path] = [paths.topics_dir(collection)]
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
