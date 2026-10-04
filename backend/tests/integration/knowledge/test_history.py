"""Every write to a collection is a version naming its writer (spec knowledge
"Keep every document's history", "Follow edits across
collections in one feed").

Integration tier because the history is real git over a real directory — the
vault repository, whose ``knowledge/`` directory holds every collection; its
trailers and its diffs are the mechanism, and a fake of any of them would be
testing the fake. The services are real; the registry and the
audit log are small in-memory stand-ins.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.history_service import KnowledgeHistoryService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge import fs, inbox, paths
from coffer.infrastructure.knowledge.history import KnowledgeHistory
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_repository

pytestmark = pytest.mark.anyio


class _Resources:
    def __init__(self) -> None:
        self.rows: list[Resource] = []

    async def register(self, *, kind: str, name: str, **_: Any) -> Resource:
        now = datetime.now(tz=UTC)
        row = Resource(
            uid=f"uid-{name}",
            kind=kind,
            name=name,
            description=None,
            config={},
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self.rows.append(row)
        return row

    async def get(self, uid: str) -> Resource:
        for row in self.rows:
            if row.uid == uid:
                return row
        raise ResourceNotFound(uid)

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return list(self.rows)


@dataclass
class _Entry:
    event_type: str
    actor: str
    resource_uid: str | None
    details: dict[str, Any] = field(default_factory=dict)


class _Audit:
    """The audit log."""

    def __init__(self) -> None:
        self.entries: list[_Entry] = []

    async def record(
        self, event_type: str, *, resource: Any = None, actor: str, details: Any = None
    ) -> None:
        rid = resource.uid if resource is not None else None
        self.entries.append(_Entry(event_type, actor, rid, dict(details or {})))

    async def query(
        self, *, resource: Any = None, event_type: str | None = None, limit: int = 50, **_: Any
    ) -> list[_Entry]:
        found = [
            e
            for e in reversed(self.entries)
            if (event_type is None or e.event_type == event_type)
            and (resource is None or e.resource_uid == resource.uid)
        ]
        return found[:limit]


class _World:
    def __init__(self) -> None:
        self.resources = _Resources()
        self.audit = _Audit()
        self.history = KnowledgeHistory()

        self.knowledge = KnowledgeService(
            resources=self.resources,  # type: ignore[arg-type]
            audit=self.audit,  # type: ignore[arg-type]
            history=self.history,
        )
        self.histories = KnowledgeHistoryService(
            knowledge=self.knowledge,
            history=self.history,
            audit=self.audit,  # type: ignore[arg-type]
            machine=lambda: "a test machine",
        )


@pytest.fixture
def world() -> _World:
    paths.knowledge_root().mkdir(parents=True)
    return _World()


def _body(relpath: str) -> str:
    return fs.read_file(relpath).body.strip()


def _bytes(relpath: str) -> bytes:
    return paths.resolve(relpath).read_bytes()


async def _save(world: _World, relpath: str, body: str) -> None:
    current = fs.read_file(relpath)
    await world.knowledge.save_document(
        relpath, body, expected_fingerprint=current.fingerprint, actor=ACTOR_USER
    )


@pytest.mark.acceptance(
    spec="knowledge", scenario="a document's history lists its versions with their writers"
)
async def test_a_documents_history_names_the_agent_and_the_user(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    # Claude Code submits material, which becomes a document at once.
    added = await world.knowledge.submit(
        collection="shopee",
        title="Session ownership",
        description="who owns login",
        body="The account service owns sessions.",
        actor_kind=ACTOR_AGENT,
        actor="claude-code",
    )
    doc = added.document.path

    # And the user edits it.
    await _save(world, doc, "The account service owns sessions, which last 30 days.")

    versions = await world.histories.versions(doc)
    assert [(v.change.meta.writer, v.change.meta.operation) for v in versions] == [
        ("user", "save"),
        ("agent", "promote"),
    ]
    assert versions[1].change.meta.agent == "claude-code"
    for version in versions:
        diff = await world.histories.version_diff(doc, version.change.version)
        assert diff.diff.startswith("diff --git"), diff
    assert versions[0].change.time >= versions[-1].change.time

    # Restoring the first version is a new commit; the history keeps both.
    first = versions[-1].change.version
    await world.histories.restore(doc, first, actor=ACTOR_USER)
    after = await world.histories.versions(doc)
    assert [v.change.meta.operation for v in after] == ["restore", "save", "promote"]
    assert after[0].change.meta.restored_from == first
    assert _body(doc) == "The account service owns sessions."


@pytest.mark.acceptance(spec="knowledge", scenario="an edit on disk becomes a version of its own")
async def test_an_edit_on_disk_is_committed_before_coffers_next_write(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    edited = fs.write_file(directory="shopee", title="By hand", description="d", body="v1").path
    saved = fs.write_file(directory="shopee", title="By the page", description="d", body="v1").path
    await world.histories.changes()  # history has seen both

    # A person's own editor, outside Coffer.
    target = paths.resolve(edited)
    target.write_text(target.read_text(encoding="utf-8").replace("v1", "v2"), encoding="utf-8")
    await _save(world, saved, "saved from the page")

    [edit, *_] = await world.histories.versions(edited)
    assert (edit.change.meta.writer, edit.change.meta.operation) == ("disk", "edit")
    [save, *_] = await world.histories.versions(saved)
    assert save.change.meta.writer == "user"
    assert [d.path for d in save.change.documents] == [saved]
    # Two vault commits, the disk edit first: the save names only its own path.
    [newest, before] = vault_repository().log("knowledge", limit=2)
    assert newest.version == save.change.version
    assert before.version == edit.change.version
    assert [pc.path for pc in before.paths] == [paths.vault_path(edited)]


async def test_knowledge_history_is_the_vault_repositorys(world: _World) -> None:
    """There is no knowledge repository of its own: every commit lands in the
    vault's, under ``knowledge/``, authored by its writer."""
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    added = await world.knowledge.submit(
        collection="shopee",
        title="T",
        description="d",
        body="b",
        actor_kind=ACTOR_USER,
        actor=ACTOR_USER,
    )
    assert added.document is not None
    assert not (paths.knowledge_root() / ".git").exists()
    assert (vault_root() / ".git").is_dir()
    [commit] = vault_repository().log(paths.vault_path(added.document.path))
    assert commit.meta.writer == "user"
    assert commit.meta.operation == "promote"
    assert all(pc.path.startswith("knowledge/shopee/") for pc in commit.paths)
    # And the knowledge view hands the same commit back knowledge-root-relative.
    [version] = await world.histories.versions(added.document.path)
    assert version.change.version == commit.version
    assert {d.path for d in version.change.documents} == {
        pc.path.removeprefix("knowledge/") for pc in commit.paths
    }
    diff = await world.histories.version_diff(added.document.path, commit.version)
    assert f"b/{added.document.path}" in diff.diff


async def test_a_save_over_a_change_it_did_not_see_is_refused(world: _World) -> None:
    from coffer.domain.knowledge.errors import KnowledgeFileConflict

    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    doc = fs.write_file(directory="shopee", title="Doc", description="d", body="v1").path
    stale = fs.read_file(doc).fingerprint
    target = paths.resolve(doc)
    target.write_text(target.read_text(encoding="utf-8").replace("v1", "v2"), encoding="utf-8")

    with pytest.raises(KnowledgeFileConflict) as refused:
        await world.knowledge.save_document(
            doc, "from the page", expected_fingerprint=stale, actor=ACTOR_USER
        )
    assert "v2" in str(refused.value.error_details["current_body"])
    assert _body(doc) == "v2"


@pytest.mark.acceptance(spec="knowledge", scenario="recent changes lists edits across collections")
async def test_recent_changes_across_collections(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    await world.knowledge.create_collection("personal", actor=ACTOR_USER)
    note = fs.write_file(directory="personal", title="Note", description="d", body="one").path
    item = await world.knowledge.submit(
        collection="shopee",
        title="Gateway",
        description="d",
        body="Routes by region.\nAnd by tenant.",
        actor_kind=ACTOR_AGENT,
        actor="codex",
    )
    await _save(world, note, "one\ntwo\nthree")

    feed = await world.histories.changes()
    edit, added = feed.changes[0], feed.changes[1]
    assert (edit.collections, edit.meta.writer, edit.meta.operation) == (
        ("personal",),
        "user",
        "save",
    )
    assert (added.collections, added.meta.writer, added.meta.agent) == (
        ("shopee",),
        "agent",
        "codex",
    )
    [written] = added.documents
    assert (written.path, written.status) == (item.document.path, "added")
    assert written.added > 0
    [changed] = edit.documents
    assert (changed.status, changed.added, changed.removed) == ("modified", 2, 0)

    shopee = await world.histories.changes(collection="shopee")
    assert all(c.collections == ("shopee",) for c in shopee.changes)
    assert shopee.changes[0].version == added.version
    personal = await world.histories.changes(collection="personal")
    assert personal.changes[0].version == edit.version

    detail = await world.histories.version_diff("shopee/gateway.md", added.version)
    assert detail.path == "shopee/gateway.md"
    assert "+Routes by region." in detail.diff


async def test_the_feed_pages_by_cursor(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    doc = fs.write_file(directory="shopee", title="Doc", description="d", body="0").path
    for n in range(1, 5):
        await _save(world, doc, str(n))

    first = await world.histories.changes(limit=2)
    second = await world.histories.changes(limit=2, cursor=first.next_cursor)
    assert first.next_cursor is not None
    seen = [c.version for c in (*first.changes, *second.changes)]
    assert len(seen) == len(set(seen)) == 4


@pytest.mark.acceptance(spec="knowledge", scenario="no git hands installing it to an agent")
async def test_without_git_writes_work_and_history_says_so(
    world: _World, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    from coffer.domain.knowledge.errors import KnowledgeHistoryUnavailable
    from coffer.infrastructure.vault import git

    monkeypatch.setattr(git, "git_available", lambda: False)
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    added = await world.knowledge.submit(
        collection="shopee", title="T", description="d", body="b", actor=ACTOR_USER
    )
    assert added.document is not None
    assert not (vault_root() / ".git").exists()
    with pytest.raises(KnowledgeHistoryUnavailable) as refused:
        await world.histories.versions(added.document.path)
    # The refusal carries the install hand-off: the machine, what needed git,
    # and how to confirm it — never an install command.
    details = refused.value.error_details
    assert details["reason"] == "git_missing"
    prompt = details["handoff"]["prompt"]  # type: ignore[index]
    assert prompt.startswith("Please install git on this machine.")
    assert "This machine: a test machine." in prompt
    assert "`git --version`" in prompt
    assert "brew" not in prompt and "xcode-select" not in prompt
    assert "install" not in str(refused.value).replace("not installed", "")
    assert inbox.inbox_items("shopee") == ()
    assert KIND_KNOWLEDGE == "knowledge"
