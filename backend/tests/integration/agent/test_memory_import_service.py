"""Integration tests for AgentMemoryImportService with fake reader + sink.

Exercises the orchestration only — confirm-agent → resolve-path → read facts →
add each → organize + store_name — against an in-memory reader/sink so the suite
needs no real git project or internal LLM. The composition-root wiring (real
MemoryService sink + OrganizerService) is covered by the route smoke test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.agent.memory_import_service import (
    AgentMemoryImportService,
    ImportResult,
)
from coffer.domain.errors import MemoryRejected, ResourceNotFound, ScopeUnresolved
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.native_memory_import import ParsedNativeFact

pytestmark = pytest.mark.asyncio


class _FakeAgents:
    def __init__(self, *, name: str) -> None:
        self._name = name

    async def get(self, name: str) -> Resource:
        if name != self._name:
            raise ResourceNotFound("agent", name)
        now = datetime(2026, 6, 21, tzinfo=UTC)
        return Resource(
            id=1,
            kind="agent",
            name=name,
            description=None,
            config={"type": "claude_code", "config_dir": "/x"},
            enabled=True,
            created_at=now,
            updated_at=now,
        )


class _FakeReader:
    def __init__(self, *, facts: list[ParsedNativeFact], project_path: str | None) -> None:
        self._facts = facts
        self._project_path = project_path

    def read_facts(self, memory_dir: str) -> list[ParsedNativeFact]:
        return list(self._facts)

    def resolve_project_path(self, memory_dir: str) -> str | None:
        return self._project_path


class _FakeSink:
    def __init__(
        self,
        *,
        store_name: str | None = "project-X",
        raise_scope_unresolved: bool = False,
        organize_raises: bool = False,
        reject_names: set[str] | None = None,
    ) -> None:
        self.added: list[dict] = []
        self.organize_calls = 0
        self._store_name = store_name
        self._raise_scope = raise_scope_unresolved
        self._organize_raises = organize_raises
        self._reject_names = reject_names or set()

    async def add(
        self,
        *,
        project_path: str,
        name: str,
        description: str,
        body: str,
        origin_session_id: str | None,
    ) -> None:
        if self._raise_scope:
            raise ScopeUnresolved(project_path)
        if name in self._reject_names:
            raise MemoryRejected("too_long", f"fact {name!r} exceeds the store limit")
        self.added.append(
            {
                "project_path": project_path,
                "name": name,
                "description": description,
                "body": body,
                "origin_session_id": origin_session_id,
            }
        )

    async def organize(self, *, project_path: str) -> bool:
        self.organize_calls += 1
        if self._organize_raises:
            raise RuntimeError("organizer blew up")
        return True

    async def store_name(self, *, project_path: str) -> str | None:
        return self._store_name


def _facts() -> list[ParsedNativeFact]:
    return [
        ParsedNativeFact(
            name="Alpha",
            description="a",
            body="abody",
            origin_session_id="s1",
        ),
        ParsedNativeFact(name="Beta", description="b", body="bbody", origin_session_id=None),
    ]


def _svc(reader: _FakeReader, sink: _FakeSink) -> AgentMemoryImportService:
    return AgentMemoryImportService(agent_service=_FakeAgents(name="cc"), reader=reader, sink=sink)


async def test_import_adds_facts_organizes_and_reports() -> None:
    sink = _FakeSink()
    reader = _FakeReader(facts=_facts(), project_path="/real/proj")
    svc = _svc(reader, sink)

    result = await svc.import_store(name="cc", memory_dir="/x/projects/-real-proj/memory")

    assert result == ImportResult(
        imported=2, skipped=0, store="project-X", project_path="/real/proj", organized=True
    )
    assert len(sink.added) == 2
    first = sink.added[0]
    assert first["project_path"] == "/real/proj"
    assert first["name"] == "Alpha"
    assert first["origin_session_id"] == "s1"
    assert sink.organize_calls == 1


async def test_import_skips_rejected_facts_and_keeps_going() -> None:
    # One over-length fact is rejected by the sink → skip it, import the rest,
    # and still organize. A single bad fact must not abort the whole batch.
    sink = _FakeSink(reject_names={"Alpha"})
    reader = _FakeReader(facts=_facts(), project_path="/real/proj")
    svc = _svc(reader, sink)

    result = await svc.import_store(name="cc", memory_dir="/x")

    assert result.imported == 1
    assert result.skipped == 1
    assert result.store == "project-X"
    assert result.organized is True
    assert [a["name"] for a in sink.added] == ["Beta"]
    assert sink.organize_calls == 1


async def test_import_unknown_agent_raises() -> None:
    sink = _FakeSink()
    reader = _FakeReader(facts=_facts(), project_path="/real/proj")
    svc = _svc(reader, sink)
    with pytest.raises(ResourceNotFound):
        await svc.import_store(name="ghost", memory_dir="/x")


async def test_import_scope_unresolved_aborts_with_zero() -> None:
    # The resolved path is not a git project → the sink raises ScopeUnresolved on
    # the first add → abort: imported 0, store None, organized False, skipped=#files.
    sink = _FakeSink(raise_scope_unresolved=True)
    reader = _FakeReader(facts=_facts(), project_path="/real/proj")
    svc = _svc(reader, sink)

    result = await svc.import_store(name="cc", memory_dir="/x")

    assert result == ImportResult(
        imported=0, skipped=2, store=None, project_path="/real/proj", organized=False
    )
    assert sink.added == []
    assert sink.organize_calls == 0


async def test_import_unresolved_path_returns_zero() -> None:
    # Reader can't recover a project path → nothing to import.
    sink = _FakeSink()
    reader = _FakeReader(facts=_facts(), project_path=None)
    svc = _svc(reader, sink)

    result = await svc.import_store(name="cc", memory_dir="/x")

    assert result == ImportResult(
        imported=0, skipped=2, store=None, project_path=None, organized=False
    )
    assert sink.added == []
    assert sink.organize_calls == 0


async def test_import_no_facts_returns_zero_no_organize() -> None:
    sink = _FakeSink()
    reader = _FakeReader(facts=[], project_path="/real/proj")
    svc = _svc(reader, sink)

    result = await svc.import_store(name="cc", memory_dir="/x")

    assert result == ImportResult(
        imported=0, skipped=0, store=None, project_path="/real/proj", organized=False
    )
    assert sink.organize_calls == 0


async def test_import_organize_exception_swallowed_keeps_import() -> None:
    # An exception during organize must NOT lose the imported inbox items:
    # imported stays >0, only organized flips to False.
    sink = _FakeSink(organize_raises=True)
    reader = _FakeReader(facts=_facts(), project_path="/real/proj")
    svc = _svc(reader, sink)

    result = await svc.import_store(name="cc", memory_dir="/x")

    assert result.imported == 2
    assert result.organized is False
    assert result.store == "project-X"
    assert result.project_path == "/real/proj"
