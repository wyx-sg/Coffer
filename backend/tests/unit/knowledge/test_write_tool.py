"""``coffer__write`` — the layer's only MCP tool (spec knowledge FR-033).

Two things are worth pinning about it. It writes into ``sources/`` and never
into the curated lane, so an agent cannot reach past curation by naming a path.
And when it is given a collection the caller may not write, it answers with the
ones they may: a model that reached for the tool without having opened the
delivered skill gets a correction instead of a dead end, and it discloses
nothing the skill would not have (FR-010).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.infrastructure.knowledge import fs, paths


class _Resources:
    def __init__(self, rows: list[tuple[str, Scope | None]]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
                kind=KIND_KNOWLEDGE,
                name=name,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=scope,
            )
            for i, (name, scope) in enumerate(rows, start=1)
        ]

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return list(self._rows)


class _Audit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append(event_type)


@pytest.fixture
def handler(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    fs.create_collection_dir("personal")
    audit = _Audit()
    service = KnowledgeService(
        resources=_Resources([("shopee", Scope(agents=["claude-code"])), ("personal", None)]),
        audit=audit,
    )
    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(registry, knowledge_service=service)
    tools = {t.name: t for t in registry.list()}
    assert set(tools) == {"write"}, "the layer exposes one tool and no retrieval"
    return tools["write"].handler, audit


@pytest.mark.anyio
async def test_a_write_lands_in_sources_and_is_audited(handler) -> None:  # type: ignore[no-untyped-def]
    write, audit = handler
    answer = await write(
        {
            "agent": "claude-code",
            "collection": "shopee",
            "title": "Session ownership",
            "description": "Which service owns login state.",
            "body": "account.session owns it.",
        }
    )
    assert answer["path"] == "shopee/sources/session-ownership.md"
    assert paths.lane_of(answer["path"]) == "sources"
    # The answer says plainly that the file will not stay where it landed —
    # otherwise an agent would report the path back to the user as an address.
    assert "curation" in answer["note"]
    assert audit.events == ["knowledge_written"]


@pytest.mark.anyio
async def test_an_unavailable_collection_names_the_available_ones(handler) -> None:  # type: ignore[no-untyped-def]
    write, _ = handler
    with pytest.raises(ValueError) as raised:
        await write(
            {
                "agent": "codex",
                "collection": "shopee",
                "title": "t",
                "description": "d",
            }
        )
    message = str(raised.value)
    # `codex` is not activated for `shopee`, so it is told neither that the
    # collection exists nor that it is forbidden — only what it may write.
    assert "shopee" in message  # it named the collection, so it is quoted back
    assert "personal" in message
    assert "forbidden" not in message.lower()


@pytest.mark.anyio
async def test_a_caller_with_nothing_is_told_so(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=KnowledgeService(resources=_Resources([]), audit=_Audit()),
    )
    write = {t.name: t for t in registry.list()}["write"].handler
    with pytest.raises(ValueError, match="You have none"):
        await write({"collection": "anything", "title": "t", "description": "d"})


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["collection", "title", "description"])
async def test_the_three_required_fields_are_required(handler, missing: str) -> None:  # type: ignore[no-untyped-def]
    write, _ = handler
    args: dict[str, Any] = {
        "agent": "claude-code",
        "collection": "shopee",
        "title": "t",
        "description": "d",
    }
    del args[missing]
    with pytest.raises(ValueError, match=missing):
        await write(args)
