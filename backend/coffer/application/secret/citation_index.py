"""What cites each secret, kept as an index instead of rescanned on every read.

A secret is cited by a resource's config (an MCP server's env or header, a
channel's token, a provider's key) or by a skill file holding its
``coffer://secret/<id>`` URI. Both are the source of truth; this index is a
rebuildable cache of them (``derived/secret-citations.json``, never synced).

It is rebuilt in full at start, and kept current by the ``Changed`` hint every
resource write announces — a skill is a resource, and the vault scanner emits
the same hint for a file edited on disk. Reads (:meth:`resource_citers`,
:meth:`skill_citers`) never scan; :meth:`settled` waits for the updates a write
just scheduled, so a read after a write sees it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Protocol

from coffer.application.runtime.supervisor import spawn
from coffer.domain.reconcile import Changed
from coffer.domain.resource import Resource
from coffer.domain.secrets import SECRET_NAMESPACE, slot_of

_log = logging.getLogger(__name__)

FORMAT = 1
SKILL = "skill"

#: ``skill name -> {uri name -> [relative paths]}`` for one skill, or every skill.
SkillScan = Callable[[str | None], dict[str, dict[str, list[str]]]]
Persist = Callable[[dict[str, Any]], None]


class ResourceSource(Protocol):
    async def list_resources(self) -> list[Resource]: ...

    async def find_resource(self, uid: str) -> Resource | None: ...

    def secret_slots(self, resource: Resource) -> dict[str, str]: ...


class CitationIndex:
    def __init__(
        self,
        source: ResourceSource,
        scan_skills: SkillScan,
        persist: Persist | None = None,
    ) -> None:
        self._source = source
        self._scan_skills = scan_skills
        self._persist = persist
        #: owner -> entries; an owner is ``resource:<uid>`` or ``skill:<name>``.
        self._owners: dict[str, list[dict[str, Any]]] = {}
        self._skill_names: dict[str, str] = {}
        self._by_ref: dict[str, list[dict[str, Any]]] = {}
        self._pending: set[asyncio.Task[None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """The loop the updates run on: hints also arrive from worker threads."""
        self._loop = loop

    # --- building ----------------------------------------------------------------

    def _resource_entries(self, resource: Resource) -> list[dict[str, Any]]:
        stdio = (
            resource.kind == "mcp_server"
            and (resource.config.get("transport") or {}).get("type") == "stdio"
        )
        return [
            {
                "ref": ref,
                "source": "resource",
                "kind": resource.kind,
                "uid": resource.uid,
                "name": resource.name,
                "key": key,
                "slot": slot_of(resource.kind, key),
                "stdio": stdio,
            }
            for key, ref in self._source.secret_slots(resource).items()
        ]

    def _skill_entries(self, scanned: dict[str, dict[str, list[str]]]) -> None:
        for name, uris in scanned.items():
            self._owners[f"{SKILL}:{name}"] = [
                {"ref": SECRET_NAMESPACE + uri, "source": SKILL, "skill": name, "path": path}
                for uri, paths in uris.items()
                for path in paths
            ]

    def _reindex(self) -> None:
        by_ref: dict[str, list[dict[str, Any]]] = {}
        for entries in self._owners.values():
            for entry in entries:
                by_ref.setdefault(entry["ref"], []).append(entry)
        self._by_ref = by_ref
        if self._persist is not None:
            try:
                self._persist({"format": FORMAT, "refs": by_ref})
            except Exception:
                _log.exception("secret.citation_index_persist_failed")

    async def rebuild(self) -> None:
        """Read every resource and skill file once: at start, and whenever the
        cache was missing, unreadable or of another format."""
        self._owners.clear()
        self._skill_names.clear()
        for resource in await self._source.list_resources():
            if resource.kind == SKILL:
                self._skill_names[resource.uid] = resource.name
            self._owners[f"resource:{resource.uid}"] = self._resource_entries(resource)
        self._skill_entries(await asyncio.to_thread(self._scan_skills, None))
        self._reindex()

    # --- keeping it current ----------------------------------------------------------

    def on_changed(self, changed: Changed) -> None:
        """The hint sink: schedule the update for one resource. Safe from any
        thread; the update runs on the event loop."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._schedule(changed)
        else:
            loop.call_soon_threadsafe(self._schedule, changed)

    def _schedule(self, changed: Changed) -> None:
        task = spawn(self._refresh(changed), name="secret-citations-refresh")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def skill_files_changed(self, name: str) -> None:
        """Files under a skill's master folder changed (Coffer's own write, a
        hand edit the vault scanner settled, a sync round): read that folder
        again. Safe from any thread."""
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._schedule_skill, name)

    def _schedule_skill(self, name: str) -> None:
        task = spawn(self._refresh_skill(name), name="secret-citations-skill")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _refresh_skill(self, name: str) -> None:
        try:
            self._owners.pop(f"{SKILL}:{name}", None)
            self._skill_entries(await asyncio.to_thread(self._scan_skills, name))
            self._reindex()
        except Exception:
            _log.exception("secret.citation_index_refresh_failed", extra={"skill": name})

    async def _refresh(self, changed: Changed) -> None:
        try:
            owner = f"resource:{changed.uid}"
            if changed.op == "delete":
                self._owners.pop(owner, None)
                name = self._skill_names.pop(changed.uid, None)
                if name is not None:
                    self._owners.pop(f"{SKILL}:{name}", None)
            else:
                resource = await self._source.find_resource(changed.uid)
                if resource is None:
                    self._owners.pop(owner, None)
                else:
                    self._owners[owner] = self._resource_entries(resource)
                    if resource.kind == SKILL:
                        self._skill_names[resource.uid] = resource.name
                        self._owners.pop(f"{SKILL}:{resource.name}", None)
                        scanned = await asyncio.to_thread(self._scan_skills, resource.name)
                        self._skill_entries(scanned)
            self._reindex()
        except Exception:
            _log.exception("secret.citation_index_refresh_failed", extra={"uid": changed.uid})

    async def settled(self) -> None:
        """Wait for the updates scheduled by the writes so far (bounded: an
        update that does not finish in five seconds is read past, not waited on)."""
        for _ in range(10):
            running = {t for t in self._pending if not t.done()}
            self._pending -= {t for t in self._pending if t.done()}
            if not running:
                return
            try:
                running = {t for t in running if t.get_loop() is asyncio.get_running_loop()}
                if not running:
                    return
                await asyncio.wait(running, timeout=0.5)
            except (RuntimeError, ValueError):
                return

    # --- reading -----------------------------------------------------------------------

    def resource_citers(self) -> dict[str, list[str]]:
        """``{ref: [uid of each resource citing it]}``."""
        return {
            ref: [e["uid"] for e in entries if e["source"] == "resource"]
            for ref, entries in self._by_ref.items()
            if any(e["source"] == "resource" for e in entries)
        }

    def entries(self, ref: str) -> list[dict[str, Any]]:
        return list(self._by_ref.get(ref, []))

    def skill_citers(self, ref: str) -> list[str]:
        """The skills whose files hold the secret's ``coffer://secret/`` URI."""
        return sorted({e["skill"] for e in self._by_ref.get(ref, []) if e["source"] == SKILL})
