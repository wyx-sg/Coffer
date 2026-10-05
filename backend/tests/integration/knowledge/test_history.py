"""Every write to a collection is a commit naming its writer (spec knowledge
"Commit every knowledge write naming its writer", "Follow edits across
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

from coffer.application.knowledge.change_service import KnowledgeChangeService
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
        self.changes = KnowledgeChangeService(
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


def _edit_on_disk(relpath: str, old: str, new: str) -> None:
    """A person's own editor, or an agent's file tools, outside Coffer."""
    target = paths.resolve(relpath)
    target.write_text(target.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


async def _upload(world: _World, title: str, body: str = "b") -> str:
    """A person's upload: material that becomes a document at once."""
    added = await world.knowledge.submit(
        collection="shopee",
        title=title,
        description="d",
        body=body,
        actor_kind=ACTOR_USER,
        actor=ACTOR_USER,
    )
    return added.document.path


@pytest.mark.acceptance(
    spec="knowledge", scenario="knowledge writes are commits naming their writers"
)
async def test_knowledge_writes_are_commits_naming_their_writers(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    first = await _upload(world, "Session ownership", "The account service owns sessions.")
    # An agent edits it with its own file tools, outside Coffer.
    _edit_on_disk(first, "owns sessions.", "owns sessions, which last 30 days.")

    second = await _upload(world, "Gateway", "Routes by region.")

    commits = vault_repository().log(paths.vault_path(first))
    assert [(c.meta.writer, c.meta.operation) for c in commits] == [
        ("disk", "edit"),
        ("user", "promote"),
    ]
    [upload] = vault_repository().log(paths.vault_path(second))
    assert upload.meta.writer == "user"
    assert [pc.path for pc in upload.paths] == [paths.vault_path(second)]
    # The same commits, read back knowledge-root-relative through the feed.
    feed = await world.changes.changes()
    assert [c.meta.writer for c in feed.changes if first in {d.path for d in c.documents}] == [
        "disk",
        "user",
    ]


@pytest.mark.acceptance(spec="knowledge", scenario="an edit on disk becomes a commit of its own")
async def test_an_edit_on_disk_is_committed_before_coffers_next_write(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    edited = await _upload(world, "By hand", "v1")

    # A person's own editor, outside Coffer; then Coffer's next knowledge write.
    _edit_on_disk(edited, "v1", "v2")
    uploaded = await _upload(world, "By the page", "page")

    [edit, *_] = vault_repository().log(paths.vault_path(edited))
    assert (edit.meta.writer, edit.meta.operation) == ("disk", "edit")
    [upload] = vault_repository().log(paths.vault_path(uploaded))
    assert upload.meta.writer == "user"
    assert [pc.path for pc in upload.paths] == [paths.vault_path(uploaded)]
    # Two vault commits, the disk edit first: Coffer's holds only its own path.
    [newest, before] = vault_repository().log("knowledge", limit=2)
    assert newest.version == upload.version
    assert before.version == edit.version
    assert [pc.path for pc in before.paths] == [paths.vault_path(edited)]


async def test_knowledge_history_is_the_vault_repositorys(world: _World) -> None:
    """There is no knowledge repository of its own: every commit lands in the
    vault's, under ``knowledge/``, authored by its writer."""
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    path = await _upload(world, "T")
    assert not (paths.knowledge_root() / ".git").exists()
    assert (vault_root() / ".git").is_dir()
    [commit] = vault_repository().log(paths.vault_path(path))
    assert commit.meta.writer == "user"
    assert commit.meta.operation == "promote"
    assert all(pc.path.startswith("knowledge/shopee/") for pc in commit.paths)
    # And the knowledge view hands the same commit back knowledge-root-relative.
    change = world.history.change(commit.version)
    assert change is not None
    assert {d.path for d in change.documents} == {
        pc.path.removeprefix("knowledge/") for pc in commit.paths
    }
    assert f"b/{path}" in world.history.diff(commit.version, path)


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
    # An agent's edit on disk in the other collection, found before the next write.
    _edit_on_disk(note, "one", "one\ntwo\nthree")
    await world.knowledge.submit(
        collection="personal",
        title="Upload",
        description="d",
        body="uploaded",
        actor_kind=ACTOR_USER,
        actor=ACTOR_USER,
    )

    feed = await world.changes.changes()
    upload, edit, added = feed.changes[0], feed.changes[1], feed.changes[2]
    assert (upload.collections, upload.meta.writer) == (("personal",), "user")
    assert (edit.collections, edit.meta.writer, edit.meta.operation) == (
        ("personal",),
        "disk",
        "edit",
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

    shopee = await world.changes.changes(collection="shopee")
    assert all(c.collections == ("shopee",) for c in shopee.changes)
    assert shopee.changes[0].version == added.version
    personal = await world.changes.changes(collection="personal")
    assert personal.changes[0].version == upload.version

    # One change read in full: every document it touched, with its diff.
    in_full = world.history.change(added.version)
    assert in_full is not None
    [diffed] = [world.history.diff(in_full.version, d.path) for d in in_full.documents]
    assert "+Routes by region." in diffed


async def test_the_feed_pages_by_cursor(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    for n in range(4):
        await _upload(world, f"Doc {n}")

    first = await world.changes.changes(limit=2)
    second = await world.changes.changes(limit=2, cursor=first.next_cursor)
    assert first.next_cursor is not None
    seen = [c.version for c in (*first.changes, *second.changes)]
    assert len(seen) == len(set(seen)) == 4


@pytest.mark.acceptance(spec="knowledge", scenario="no git hands installing it to an agent")
async def test_without_git_writes_work_and_the_feed_says_so(
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
        await world.changes.changes()
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
