"""An agent adds knowledge by writing a Markdown file into a collection's
``.inbox/`` (spec knowledge "Adopt a file dropped into the inbox").

Real git over a real directory, because "written outside Coffer" is decided by
what the vault repository has and has not committed. The registry and the audit
log are in-memory stand-ins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.intake import adopt_dropped_files
from coffer.application.knowledge.recording import settle
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs, inbox, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.history import KnowledgeHistory

pytestmark = pytest.mark.anyio


class _Resources:
    def __init__(self, names: list[str]) -> None:
        now = datetime.now(tz=UTC)
        self.rows = [
            Resource(
                uid=f"uid-{n}",
                kind=KIND_KNOWLEDGE,
                name=n,
                description=None,
                config={},
                enabled=True,
                created_at=now,
                updated_at=now,
                scope=None,
            )
            for n in names
        ]

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return list(self.rows)


@dataclass
class _Entry:
    event_type: str
    actor: str
    details: dict[str, Any] = field(default_factory=dict)


class _Audit:
    def __init__(self) -> None:
        self.entries: list[_Entry] = []

    async def record(
        self, event_type: str, *, resource: Any = None, actor: str, details: Any = None
    ) -> None:
        self.entries.append(_Entry(event_type, actor, dict(details or {})))


def _world(history: KnowledgeHistory | None) -> tuple[KnowledgeService, _Audit]:
    fs.create_collection_dir("shopee")
    if history is not None:
        # The repository exists, with its baseline commit, before any agent writes.
        assert history.available()
    audit = _Audit()
    service = KnowledgeService(
        resources=_Resources(["shopee"]),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        history=history,
    )
    return service, audit


def _drop(collection: str, name: str, text: str) -> None:
    directory = paths.inbox_dir(collection)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def _frontmatter(collection: str, name: str) -> tuple[dict[str, Any], str]:
    return split_frontmatter((paths.inbox_dir(collection) / name).read_text(encoding="utf-8"))


@pytest.mark.acceptance(spec="knowledge", scenario="a bare inbox file is normalised and audited")
async def test_a_bare_inbox_file_is_normalised_and_audited() -> None:
    service, audit = _world(KnowledgeHistory())
    _drop("shopee", "cache-ttl.md", "# Cache TTL\n\nSessions expire after 30 minutes.\n")

    adopted = await adopt_dropped_files(service)

    assert adopted == ["shopee/.inbox/cache-ttl.md"]
    fm, body = _frontmatter("shopee", "cache-ttl.md")
    assert fm["title"] == "Cache TTL"
    assert fm["description"] == "Sessions expire after 30 minutes."
    assert fm["actor"] == "agent"
    assert fm["created_at"] and fm["updated_at"]
    assert body.strip() == "# Cache TTL\n\nSessions expire after 30 minutes."
    [event] = audit.entries
    assert event.event_type == "knowledge_written"
    assert event.actor == "agent"
    assert event.details["item"] == "cache-ttl.md"
    assert event.details["actor_reported"] is False
    # Adoption only normalises it; promoting is the sweep's next step.
    assert inbox.inbox_items("shopee") == ("cache-ttl.md",)


@pytest.mark.acceptance(spec="knowledge", scenario="keys a writer set are kept")
async def test_keys_a_writer_set_are_kept() -> None:
    service, audit = _world(KnowledgeHistory())
    _drop(
        "shopee",
        "note.md",
        "---\ntitle: Own title\nactor: user\nsource: runbook\n---\n\nplain body\n",
    )

    await adopt_dropped_files(service)

    fm, _ = _frontmatter("shopee", "note.md")
    assert fm["title"] == "Own title"
    assert fm["actor"] == "user"
    assert fm["source"] == "runbook"
    assert fm["description"] == "plain body"
    [event] = audit.entries
    assert event.actor == "user"
    assert event.details["actor_reported"] is True


async def test_title_falls_back_to_the_file_stem_and_description_to_the_title() -> None:
    service, _ = _world(KnowledgeHistory())
    _drop("shopee", "just-a-name.md", "")

    await adopt_dropped_files(service)

    fm, _ = _frontmatter("shopee", "just-a-name.md")
    assert fm["title"] == "just-a-name"
    assert fm["description"] == "just-a-name"


async def test_a_file_coffer_wrote_is_not_adopted_again() -> None:
    history = KnowledgeHistory()
    service, audit = _world(history)
    await service.submit(
        collection="shopee", title="By tool", description="d", body="b", actor="claude-code"
    )
    audit.entries.clear()
    _drop("shopee", "dropped.md", "# Dropped\n\ntext\n")

    first = await adopt_dropped_files(service)
    await settle(history)
    second = await adopt_dropped_files(service)

    assert first == ["shopee/.inbox/dropped.md"]
    assert second == []
    assert [e.details["item"] for e in audit.entries] == ["dropped.md"]


async def test_without_git_only_a_file_lacking_coffer_keys_is_adopted() -> None:
    service, audit = _world(None)
    await service.submit(
        collection="shopee", title="By tool", description="d", body="b", actor="agent"
    )
    audit.entries.clear()
    _drop("shopee", "dropped.md", "text only\n")

    assert await adopt_dropped_files(service) == ["shopee/.inbox/dropped.md"]
    assert await adopt_dropped_files(service) == []


@pytest.mark.acceptance(
    spec="knowledge", scenario="a file outside a collection or that is not Markdown is not material"
)
async def test_a_file_outside_a_collection_or_not_markdown_is_not_material() -> None:
    service, audit = _world(KnowledgeHistory())
    stray = paths.knowledge_root() / "notes" / ".inbox"
    stray.mkdir(parents=True)
    (stray / "idea.md").write_text("an idea\n", encoding="utf-8")
    _drop("shopee", "data.bin", "\x00\x01")

    assert await adopt_dropped_files(service) == []

    assert (stray / "idea.md").read_text(encoding="utf-8") == "an idea\n"
    assert (paths.inbox_dir("shopee") / "data.bin").exists()
    assert audit.entries == []
    assert [c.name for c in await service.list_collections()] == ["shopee"]
    assert inbox.inbox_items("shopee") == ()
