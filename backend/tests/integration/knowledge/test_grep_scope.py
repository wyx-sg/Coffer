"""Grep, held to the same authorization boundary as the catalogue.

Integration rather than unit because grep IS ripgrep — with no index behind it
(ADR knowledge-is-plain-files) these spawn the real binary, and a unit test may
not reach for one. The catalogue half of the same boundary is a unit test, in
``tests/unit/knowledge/test_grep_and_scope.py``.
"""

from __future__ import annotations

import pytest

from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
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
    spec="knowledge", scenario="grep matches a literal string across a collection"
)
async def test_grep_spans_every_authorized_collection(service) -> None:  # type: ignore[no-untyped-def]
    outcome = await service.grep("登录态", agent="claude-code")
    assert {m.path.split("/")[0] for m in outcome.matches} == {"shopee", "personal"}

    narrowed = await service.grep("登录态", agent="codex")
    assert {m.path.split("/")[0] for m in narrowed.matches} == {"personal"}


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="knowledge", scenario="grep skips hidden directories")
async def test_grep_never_returns_an_archived_revision(service) -> None:  # type: ignore[no-untyped-def]
    """``.history/`` holds what tidy replaced; answering with it would hand back
    content the live file has superseded (FR-052)."""
    written = fs.write_file(
        directory="personal", title="Superseded", description="d", body="登录态 old revision"
    )
    fs.archive(written.path)
    fs.delete_file(written.path)

    outcome = await service.grep("old revision", agent="codex")
    assert outcome.matches == ()
