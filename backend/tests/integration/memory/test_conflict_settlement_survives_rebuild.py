"""A hand-settled conflict stays settled across a rebuild (spec memory FR-041).

Integration rather than unit because it walks the real seam this scenario is
about: ``MemoryService.aggregate`` (writing facts to the real file-backed
store), ``organise_partition`` (flagging a conflict via a faked model),
``OverrideRepository`` (the developer's settlement, in a real SQLite file —
the one thing this layer keeps in a database), and ``overrides.apply`` (the
pure re-stamp every read goes through). ``ResourceService``/``AuditService``
and the reader stay fake, same shape as
``tests/unit/memory/test_aggregate.py``'s — nothing here needs the real
Claude Code/Codex parsers, only two facts that disagree.

The read side of a settled conflict is exercised directly against
``overrides.apply`` rather than through ``compose_context``, so this test
stays about the memory layer's own persistence guarantee (FR-041) and not
about delivery's separate budget/layering rules (FR-050/FR-051), which
``tests/unit/memory/test_context.py`` already covers.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.organise import organise_partition
from coffer.application.memory.overrides import Override, apply
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.reader import RawFact, SourceFile
from coffer.domain.provider.config import ProviderConfig, ResolvedConnection
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.memory import store
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.memory_overrides_repo import OverrideRepository

_PARTITION = "coffer"

# --------------------------------------------------------------------------- #
# Fakes — resources/audit/reader (mirrors tests/unit/memory/test_aggregate.py) #
# --------------------------------------------------------------------------- #


class _FakeResources:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], Resource] = {}
        self._next_id = 1

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return [
            r
            for r in self._rows.values()
            if (kind is None or r.kind == kind) and (enabled is None or r.enabled == enabled)
        ]

    async def get(self, ref: ResourceRef) -> Resource:
        row = self._rows.get((ref.kind, ref.name))
        if row is None:
            raise ResourceNotFound(ref.kind, ref.name)
        return row

    async def register(self, *, kind, name, config, actor, description=None, **_kw):  # type: ignore[no-untyped-def]
        now = datetime.now(tz=UTC)
        row = Resource(
            id=self._next_id,
            kind=kind,
            name=name,
            description=description,
            config=config,
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self._next_id += 1
        self._rows[(kind, name)] = row
        return row

    async def update_scope(self, ref: ResourceRef, scope, *, actor: str) -> Resource:  # type: ignore[no-untyped-def]
        row = await self.get(ref)
        row.scope = scope
        return row

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        await self.get(ref)
        del self._rows[(ref.kind, ref.name)]
        if ref.kind == KIND_MEMORY:
            store.delete_partition(ref.name)

    def add_agent(self, name: str, agent_type: str, config_dir: str) -> None:
        now = datetime.now(tz=UTC)
        self._rows[("agent", name)] = Resource(
            id=self._next_id,
            kind="agent",
            name=name,
            description=None,
            config={"type": agent_type, "config_dir": config_dir},
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self._next_id += 1


class _FakeAudit:
    async def record(self, event_type, *, ref=None, actor="system", details=None):  # type: ignore[no-untyped-def]
        pass


@dataclass
class _FakeReader:
    _sources: dict[str, list[SourceFile]] = field(default_factory=dict)
    _content: dict[str, tuple[RawFact, ...]] = field(default_factory=dict)

    def set_sources(self, config_dir: str, sources: list[SourceFile]) -> None:
        self._sources[config_dir] = sources

    def set_content(self, path: str, result: tuple[RawFact, ...]) -> None:
        self._content[path] = result

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        return tuple(self._sources.get(config_dir, []))

    def read(self, source: SourceFile) -> tuple[RawFact, ...]:
        return self._content.get(source.path, ())


def _resolver(resource: Resource) -> AgentSource:
    return AgentSource(
        agent=resource.name,
        agent_type=resource.config["type"],
        config_dir=resource.config["config_dir"],
    )


def _raw(title: str, body: str, *, project_root: str) -> RawFact:
    return RawFact(
        title=title,
        description=body,
        type="project",
        body=body,
        anchor=title,
        project_root=project_root,
    )


# --------------------------------------------------------------------------- #
# Fakes — organise's model/completion (mirrors tests/unit/memory/test_organise.py) #
# --------------------------------------------------------------------------- #


class _Model:
    def __init__(self, connection: ResolvedConnection) -> None:
        self._connection = connection

    async def get_default(self) -> ResolvedConnection:
        return self._connection


class _FakeCompletion:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete(self, *, system, user, model, credential_resolver):  # type: ignore[no-untyped-def]
        return self._responses.pop(0) if self._responses else "{}"


@pytest.fixture
def fake_connection() -> ResolvedConnection:
    return ResolvedConnection(
        config=ProviderConfig(
            protocol="openai",
            base_url="https://example.invalid/v1",
            credential_ref="provider/test",
        ),
        model="agnes-2.0-flash",
    )


@pytest.fixture
async def sm(tmp_path: pathlib.Path) -> AsyncIterator[async_sessionmaker]:  # type: ignore[type-arg]
    """A fresh empty vault database per test (mirrors test_overrides_repo.py)."""
    db = tmp_path / "coffer.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield session_maker(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a hand-settled conflict stays settled across a rebuild",
)
async def test_settled_conflict_survives_a_rebuild(
    sm: async_sessionmaker,  # type: ignore[type-arg]
    fake_connection: ResolvedConnection,
) -> None:
    resources = _FakeResources()
    resources.add_agent("claude-code", "claude_code", "/cc")
    reader = _FakeReader()
    source_a = SourceFile(path="/cc/projects/coffer/memory/a.md", digest="da")
    source_b = SourceFile(path="/cc/projects/coffer/memory/b.md", digest="db")
    reader.set_sources("/cc", [source_a, source_b])
    reader.set_content(
        source_a.path, (_raw("Says X", "The project uses X.", project_root="/home/dev/coffer"),)
    )
    reader.set_content(
        source_b.path,
        (_raw("Says not X", "The project does not use X.", project_root="/home/dev/coffer"),),
    )

    service = MemoryService(
        resources=resources,
        audit=_FakeAudit(),
        agent_source_resolver=_resolver,
        readers={"claude_code": reader},
    )

    # 1. Aggregate: two plain, unrelated-looking facts land in "coffer".
    first = await service.aggregate()
    assert first.sources_read == 2
    facts = store.list_facts(_PARTITION)
    assert len(facts) == 2
    fact_a = next(f for f in facts if f.title == "Says X")
    fact_b = next(f for f in facts if f.title == "Says not X")

    # 2. Organise: a faked model flags the pair as a conflict, written to disk.
    completion = _FakeCompletion([f'{{"conflicts": [["{fact_a.key}", "{fact_b.key}"]]}}'])
    organise_result = await organise_partition(
        _PARTITION,
        models=_Model(fake_connection),
        completion=completion,
        credential_resolver=lambda ref: "k",
    )
    assert organise_result.conflicts == 1
    flagged_a = store.read_fact(_PARTITION, fact_a.slug)
    flagged_b = store.read_fact(_PARTITION, fact_b.slug)
    assert flagged_a.conflicts_with == (fact_b.key,)
    assert flagged_b.conflicts_with == (fact_a.key,)

    # 3. The developer settles it, in favour of fact_a — recorded as one
    # override, keyed by fact_a's own stable key.
    repo = OverrideRepository(sm)
    await repo.set(
        Override(fact_key=fact_a.key, conflict_choice=fact_a.key),
        actor="dev",
    )

    def _settled_both_sides() -> None:
        applied = apply(store.list_facts(_PARTITION), overrides)
        by_key = {f.key: f for f in applied.facts}
        assert by_key[fact_a.key].conflicts_with == ()
        assert by_key[fact_b.key].conflicts_with == ()
        assert by_key[fact_a.key].proposed is False
        assert by_key[fact_b.key].proposed is False

    overrides = await repo.all()
    _settled_both_sides()

    # 4. Rebuild: aggregation re-runs. Nothing changed on disk (same digests),
    # so it reuses the already-organised facts rather than re-reading — the
    # tree is rewritten, not the developer's decision, which never lived in a
    # fact file to begin with (FR-070: the override is the only thing this
    # layer keeps in a database).
    second = await service.aggregate()
    assert second.sources_skipped == 2
    assert second.sources_read == 0

    # 5. The settlement is still in force on BOTH sides after the rebuild —
    # re-reading the override from its own table and re-applying it to
    # whatever aggregation just produced, exactly as a real compose_context
    # call would on the next turn.
    overrides = await repo.all()
    _settled_both_sides()
