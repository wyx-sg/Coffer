"""``coffer__write`` — the layer's only MCP tool (spec knowledge FR-033).

Three things are worth pinning about it. It writes into ``sources/`` and never
into the curated lane, so an agent cannot reach past curation by naming a path.
When it is given a name that is not a collection, it answers with the ones that
are: a model that reached for the tool without having opened the delivered
skill gets a correction instead of a dead end, and it discloses nothing the
skill would not have. And the session's agent identity reaches the audit entry
and nothing else — it narrows no collection, because every enabled collection
is writable by every agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs


class _Resources:
    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self._rows = [
            Resource(
                id=i,
                # A uid a test can spell, and deliberately not the name: a
                # lookup that worked because the two matched would prove
                # nothing about addressing a collection by identity.
                uid=f"uid-{i}",
                kind=KIND_KNOWLEDGE,
                name=name,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=None,
            )
            for i, name in enumerate(names, start=1)
        ]

    async def get(self, uid):  # type: ignore[no-untyped-def]
        for row in self._rows:
            if row.uid == uid:
                return row
        raise ResourceNotFound(uid)

    def uid_of(self, name: str) -> str:
        """The uid a test knows the collection by its name — the resolution a
        person's CLI or the web page does before anything inside the daemon
        is handed an identity."""
        return next(r.uid for r in self._rows if r.name == name)

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

    async def can_merge() -> bool:
        return True

    service = KnowledgeService(
        resources=_Resources(["shopee", "personal"]),
        audit=audit,
        merge_available=can_merge,
    )
    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(registry, knowledge_service=service)
    tools = {t.name: t for t in registry.list()}
    assert set(tools) == {"write"}, "the layer exposes one tool and no retrieval"
    return tools["write"].handler, audit


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="written material waits in the inbox, or becomes a document with no model",
)
@pytest.mark.anyio
async def test_a_write_waits_in_the_inbox_and_is_audited(handler) -> None:  # type: ignore[no-untyped-def]
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
    assert answer["status"] == "pending"
    # No path is handed back while it waits: the material becomes part of
    # whichever document curation merges it into, and an agent that reported
    # an inbox path to the user would be reporting an address that vanishes.
    assert "path" not in answer
    assert "curation" in answer["note"]
    assert fs.inbox_items("shopee") == ("session-ownership.md",)
    assert audit.events == ["knowledge_written"]


@pytest.mark.anyio
async def test_with_no_model_a_write_is_a_document_at_once(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    fs.create_collection_dir("shopee")
    registry = BuiltinToolRegistry()
    register_knowledge_builtin_tools(
        registry,
        knowledge_service=KnowledgeService(resources=_Resources(["shopee"]), audit=_Audit()),
    )
    write = {t.name: t for t in registry.list()}["write"].handler
    answer = await write(
        {"collection": "shopee", "title": "Session ownership", "description": "d", "body": "b"}
    )
    assert answer["status"] == "written"
    assert answer["path"] == "shopee/session-ownership.md"
    assert fs.inbox_items("shopee") == ()
    assert fs.read_file(answer["path"]).body.strip() == "b"


@pytest.mark.anyio
async def test_an_unknown_collection_names_the_real_ones(handler) -> None:  # type: ignore[no-untyped-def]
    write, _ = handler
    with pytest.raises(ValueError) as raised:
        await write(
            {
                "agent": "codex",
                "collection": "nowhere",
                "title": "t",
                "description": "d",
            }
        )
    message = str(raised.value)
    assert "nowhere" in message  # it named the collection, so it is quoted back
    # Both real ones, and to either agent: the correction is the same list the
    # delivered skill already carries, and it does not vary by caller.
    assert "shopee" in message
    assert "personal" in message


@pytest.mark.anyio
async def test_every_agent_may_write_every_collection(handler) -> None:  # type: ignore[no-untyped-def]
    """No agent axis is left: the identity in ``agent`` reaches the audit entry
    and narrows nothing, so two different agents write the same collections."""
    write, _ = handler
    for agent in ("claude-code", "codex"):
        for collection in ("shopee", "personal"):
            answer = await write(
                {
                    "agent": agent,
                    "collection": collection,
                    "title": f"{agent} in {collection}",
                    "description": "d",
                }
            )
            assert answer["status"] == "pending"
            assert answer["collection"] == collection


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
