"""The one thing the layer adds on top of a directory: authorization.

A collection is a Resource so that it can be narrowed to some agents (spec
knowledge FR-012). These tests hold the service to that: what an agent may not
see must be absent from its catalogue and unreadable by name — and reported as
absent rather than forbidden, because naming a collection the caller may not
have is itself a disclosure.

The grep half of the same boundary lives in the integration tier: it spawns
ripgrep, and a unit test may not reach for a binary.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.knowledge.errors import CollectionNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs


class _Resources:
    """Just enough ResourceService for the service's authorization question."""

    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows
        self.registered: list[tuple[str, str]] = []

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return [r for r in self._rows if kind in (None, r.kind)]

    async def register(self, **kwargs):  # type: ignore[no-untyped-def]
        self.registered.append((kwargs["kind"], kwargs["name"]))


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


def _resource(name: str, scope: list[str] | None) -> Resource:
    from datetime import UTC, datetime

    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        kind=KIND_KNOWLEDGE,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
        scope=scope,
    )


@pytest.fixture
def service(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    for name in ("shopee", "personal"):
        fs.create_collection_dir(name)
        fs.write_file(directory=name, title=f"{name} note", description="d", body="登录态 body")
    resources = _Resources([_resource("shopee", ["claude-code"]), _resource("personal", None)])
    return KnowledgeService(resources=resources, audit=_Audit())


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection outside an agent's scope is absent from its catalogue"
)
async def test_catalogue_shows_only_what_the_agent_may_see(service) -> None:  # type: ignore[no-untyped-def]
    allowed = await service.list_collections(agent="claude-code")
    assert {c.name for c in allowed} == {"shopee", "personal"}

    other = await service.list_collections(agent="codex")
    assert {c.name for c in other} == {"personal"}


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="knowledge", scenario="a collection outside an agent's scope cannot be read"
)
async def test_reading_outside_scope_reports_not_found(service) -> None:  # type: ignore[no-untyped-def]
    assert (await service.read("shopee/shopee-note.md", agent="claude-code")).title
    with pytest.raises(CollectionNotFound):
        await service.read("shopee/shopee-note.md", agent="codex")
    with pytest.raises(CollectionNotFound):
        await service.list_level("shopee", agent="codex")
