"""The secret citation index and the one-time move to minted ids, wired.

Called once from the lifespan after every kind has registered its secret
destinations (spec secret "Keep an index of what cites each secret" and "Move
every secret to a fixed id once").
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import pathlib
from typing import Any

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.guide_render import GUIDE_SKILL_NAME
from coffer.application.resource_service import ResourceService
from coffer.application.secret.citation_index import CitationIndex
from coffer.application.secret.ref_migration import RefMigrator
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.domain.vault.layout import SKILLS
from coffer.domain.vault.writes import CommitResult
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.secret.plaintext_findings import rewrite_secret_uris
from coffer.infrastructure.secret.plaintext_scan import skill_citations
from coffer.infrastructure.skill.master_store import default_master_root
from coffer.infrastructure.sync.local_state import JsonRemoteStore
from coffer.infrastructure.vault.home import derived_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.surfaces.http.event_wiring import EventStream
from coffer.surfaces.http.secret_boundary_wiring import optional_secret_boundary
from coffer.surfaces.http.secret_notes_wiring import get_secret_notes

_log = logging.getLogger(__name__)
_index: CitationIndex | None = None


def get_citation_index() -> CitationIndex:
    """The running daemon's index (tests nudge it after writing a skill folder by hand)."""
    if _index is None:
        raise RuntimeError("citation index not initialised")
    return _index


class _Source:
    def __init__(self, resources: ResourceService) -> None:
        self._resources = resources

    async def list_resources(self) -> list[Resource]:
        return await self._resources.list()

    async def find_resource(self, uid: str) -> Resource | None:
        try:
            return await self._resources.get(uid)
        except ResourceNotFound:
            return None

    def secret_slots(self, resource: Resource) -> dict[str, str]:
        return self._resources.secret_slots(resource)


class _SyncRemoteCiter:
    """The sync remote's push token, cited from a machine-local setting."""

    def __init__(self) -> None:
        self._store = JsonRemoteStore()

    def ref(self) -> str | None:
        remote = self._store.get()
        return remote.secret_ref if remote is not None else None

    def repoint(self, new: str) -> None:
        remote = self._store.get()
        if remote is not None:
            self._store.put(dataclasses.replace(remote, secret_ref=new))


def _persist(doc: dict[str, Any]) -> None:
    path = derived_root() / "secret-citations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc), encoding="utf-8")
    tmp.replace(path)


async def wire_secret_index(
    resources: ResourceService,
    store: EncryptedSecretStore,
    audit: AuditService,
    events: EventStream,
) -> CitationIndex:
    """Build the index, keep it current from the hint stream, install it on the
    resource service, then move old refs to minted ids."""
    notes = get_secret_notes()
    index = CitationIndex(
        _Source(resources),
        lambda only: skill_citations(default_master_root(), only),
        _persist,
    )
    index.bind_loop(asyncio.get_running_loop())
    resources.secret_hooks.index = index
    global _index
    _index = index
    events.late_sinks.append(index.on_changed)
    await index.rebuild()

    def on_commit(result: CommitResult) -> None:
        for path in result.paths:
            parts = path.split("/")
            if len(parts) > 2 and parts[0] == SKILLS:
                index.skill_files_changed(parts[1])

    vault_writer().add_listener(on_commit)

    def owns(ref: str, uid: str) -> bool:
        note = notes.get(ref)
        # Released only by the resource it was minted for, and only when no
        # other resource and no skill file cites it any more.
        others = [u for u in index.resource_citers().get(ref, []) if u != uid]
        return bool(
            note is not None
            and note.created_for == uid
            and not others
            and not index.skill_citers(ref)
        )

    resources.secret_hooks.owns = owns

    def rebind(old: str, new: str) -> None:
        boundary = optional_secret_boundary()
        if boundary is not None:
            boundary.rebind(old, new)

    migrator = RefMigrator(
        resources,
        store,
        notes,
        index,
        audit,
        rewrite_uris=lambda old, new: rewrite_secret_uris(
            pathlib.Path(default_master_root()), old, new, frozenset({GUIDE_SKILL_NAME})
        ),
        rebind=rebind,
        extras=[_SyncRemoteCiter()],
    )
    try:
        if await migrator.run():
            await index.rebuild()
    except Exception:
        _log.exception("secret.migrate_failed")
    return index
