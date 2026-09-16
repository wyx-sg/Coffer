"""Fakes the memory unit tier shares: resources, audit, readers, completions.

Every file under here drives the real ``infrastructure.memory`` store against
``COFFER_MEMORY_ROOT``, which the suite-wide ``_isolated_memory_root`` fixture
in ``backend/tests/conftest.py`` pins to that test's own ``tmp_path`` — so no
test here can reach a developer's real ``~/.coffer/memory``, and none of them
reads a real ``~/.claude`` or ``~/.codex`` either: a reader is either a fake or
is handed a fixture ``config_dir`` built under ``tmp_path``.

What is faked and what is not is deliberate. ``ResourceService`` and
``AuditService`` are fakes because a database is the integration tier's
business and nothing about aggregation's own decisions needs one. The
**store** is real, because "what is on disk after a pass" is the whole of what
these tests assert. The completion port is always a fake, and two of the
shapes below (:class:`NoModelSelector`, :class:`ExplodingCompletion`) exist to
make FR-024's "no model is called" a structural assertion rather than a
hopeful one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.note import TYPE_PROJECT
from coffer.domain.memory.reader import RawEntry, SourceFile
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.memory import store


class FakeResources:
    """Just enough ``ResourceService`` for the two passes' database half."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Resource] = {}
        self._next_id = 1

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return [
            r
            for r in self.rows.values()
            if (kind is None or r.kind == kind) and (enabled is None or r.enabled == enabled)
        ]

    async def get(self, ref: ResourceRef) -> Resource:
        row = self.rows.get((ref.kind, ref.name))
        if row is None:
            raise ResourceNotFound(ref.kind, ref.name)
        return row

    async def register(
        self,
        *,
        kind: str,
        name: str,
        config: dict[str, Any],
        actor: str,
        description: str | None = None,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        now = datetime.now(tz=UTC)
        row = Resource(
            id=self._next_id,
            kind=kind,
            name=name,
            description=description,
            config=dict(config),
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self._next_id += 1
        self.rows[(kind, name)] = row
        return row

    async def update_config(
        self,
        ref: ResourceRef,
        new_config: dict[str, Any],
        actor: str,
        description: str | None = None,
        *,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
        row = await self.get(ref)
        row.config = dict(new_config)
        return row

    async def update_scope(self, ref: ResourceRef, scope: Scope, *, actor: str) -> Resource:
        row = await self.get(ref)
        row.scope = scope
        return row

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        await self.get(ref)
        del self.rows[(ref.kind, ref.name)]
        # Stands in for the one line of wiring the real ``ResourceService``
        # does through the kind's ``on_delete`` hook.
        if ref.kind == KIND_MEMORY:
            store.delete_partition(ref.name)

    def add_agent(
        self, name: str, agent_type: str, config_dir: str, *, enabled: bool = True
    ) -> Resource:
        now = datetime.now(tz=UTC)
        row = Resource(
            id=self._next_id,
            kind="agent",
            name=name,
            description=None,
            config={"type": agent_type, "config_dir": config_dir},
            enabled=enabled,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self._next_id += 1
        self.rows[("agent", name)] = row
        return row


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    async def record(
        self,
        event_type: str,
        *,
        ref: ResourceRef | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append((event_type, actor, details or {}))


def agent_source_resolver(resource: Resource) -> AgentSource:
    return AgentSource(
        agent=resource.name,
        agent_type=resource.config["type"],
        config_dir=resource.config["config_dir"],
    )


@dataclass
class FakeReader:
    """A ``MemoryReader`` whose sources and parse results a test controls."""

    agent_type: str
    sources_by_dir: dict[str, list[SourceFile]] = field(default_factory=dict)
    content: dict[str, Any] = field(default_factory=dict)
    read_paths: list[str] = field(default_factory=list)
    explode_on_read: bool = False

    def set_source(self, config_dir: str, path: str, digest: str, entries: Any) -> SourceFile:
        """Register one source file and what reading it produces.

        ``entries`` is a tuple of :class:`RawEntry`, or an exception instance
        the read raises — which is how FR-005's isolation is exercised.
        """
        source = SourceFile(path=path, digest=digest)
        self.sources_by_dir.setdefault(config_dir, []).append(source)
        self.content[path] = entries
        return source

    def set_digest(self, config_dir: str, path: str, digest: str) -> None:
        """Change an already-registered source's digest, as an agent editing
        its own memory file would."""
        for i, source in enumerate(self.sources_by_dir.get(config_dir, [])):
            if source.path == path:
                self.sources_by_dir[config_dir][i] = SourceFile(path=path, digest=digest)

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        return tuple(self.sources_by_dir.get(config_dir, []))

    def read(self, source: SourceFile) -> tuple[RawEntry, ...]:
        if self.explode_on_read:
            raise AssertionError(f"source {source.path} must not be read again")
        self.read_paths.append(source.path)
        result = self.content.get(source.path, ())
        if isinstance(result, Exception):
            raise result
        return tuple(result)


def raw_entry(
    title: str,
    body: str,
    *,
    type: str = TYPE_PROJECT,
    project_root: str = "",
    anchor: str = "",
    description: str = "",
    search_terms: Sequence[str] = (),
) -> RawEntry:
    return RawEntry(
        title=title,
        description=description or body,
        type=type,
        body=body,
        anchor=anchor or title,
        project_root=project_root,
        search_terms=tuple(search_terms),
    )


def memory_service(
    resources: FakeResources,
    readers: dict[str, Any],
    *,
    audit: FakeAudit | None = None,
    completion: Any = None,
    model_selector: Any = None,
) -> MemoryService:
    return MemoryService(
        resources=resources,  # type: ignore[arg-type]
        audit=audit or FakeAudit(),  # type: ignore[arg-type]
        agent_source_resolver=agent_source_resolver,
        readers=readers,
        completion=completion,
        model_selector=model_selector,
    )


# --- the internal-engine seam ------------------------------------------------


class NoModelSelector:
    """No internal connection configured — FR-024's path."""

    async def get_default(self) -> None:
        return None


class StubModelSelector:
    """An internal connection is configured; its value is opaque here."""

    def __init__(self, connection: Any = "internal-connection") -> None:
        self._connection = connection

    async def get_default(self) -> Any:
        return self._connection


class ScriptedCompletion:
    """Answers queued responses in order; ``"{}"`` once the queue is empty."""

    def __init__(self, responses: Sequence[str]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, *, system: str, user: str, model: Any, credential_resolver: Any
    ) -> str:
        self.calls.append({"system": system, "user": user, "model": model})
        return self._responses.pop(0) if self._responses else "{}"


class ExplodingCompletion:
    """Raises if it is called at all — FR-024 asserted structurally."""

    async def complete(
        self, *, system: str, user: str, model: Any, credential_resolver: Any
    ) -> str:
        raise AssertionError("no model may be called without an internal connection")
