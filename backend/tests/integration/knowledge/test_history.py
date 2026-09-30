"""Every write to a collection is a version naming its writer, and a pass can
be undone as a whole (spec knowledge "Keep every document's history and undo a
pass as a whole", "Follow knowledge changes across collections").

Integration tier because the history is real git over a real directory — the
vault repository, whose ``knowledge/`` directory holds every collection; its
trailers and its diffs are the mechanism, and a fake of any of them would be
testing the fake. The services are real; the registry and the
audit log are small in-memory stand-ins, and the curation pass's agentic loop
is scripted, because it is an LLM call.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.knowledge.curate import pending_items, run_curation
from coffer.application.knowledge.history_service import KnowledgeHistoryService
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.knowledge.entry import ACTOR_AGENT, ACTOR_USER, Pending
from coffer.domain.knowledge.errors import KnowledgeUndoConflict
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
    """The audit log: recorded, and queried the way a pass looks up an item's author."""

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


class _Model:
    async def get_default(self) -> Any:
        return type("C", (), {"model": "fake-model"})()


class _Loop:
    """An agentic loop scripted to make a fixed sequence of tool calls."""

    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls
        self.results: list[dict[str, Any]] = []

    async def run(self, *, tools: Any, **_: Any) -> dict[str, Any]:
        by_name = {t.name: t for t in tools}
        for name, args in self._calls:
            self.results.append(await by_name[name].handler(args))
        return {}


class _World:
    def __init__(self) -> None:
        self.resources = _Resources()
        self.audit = _Audit()
        self.can_merge = False
        self.history = KnowledgeHistory()

        async def merge() -> bool:
            return self.can_merge

        self.knowledge = KnowledgeService(
            resources=self.resources,  # type: ignore[arg-type]
            audit=self.audit,  # type: ignore[arg-type]
            merge_available=merge,
            history=self.history,
        )
        self.histories = KnowledgeHistoryService(
            knowledge=self.knowledge,
            history=self.history,
            audit=self.audit,  # type: ignore[arg-type]
        )

    async def curate(
        self, collection: str, item: Pending, calls: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        loop = _Loop(calls)
        outcome = await run_curation(
            self.knowledge,
            f"uid-{collection}",
            item=item,
            agent=loop,
            models=_Model(),
            secret_resolver=lambda ref: "key",
        )
        assert all("error" not in r for r in loop.results), loop.results
        return outcome


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
async def test_a_documents_history_names_the_user_curation_and_the_user(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    # The user's Add a document, with no model to merge it: a document at once.
    added = await world.knowledge.submit(
        collection="shopee",
        title="Session ownership",
        description="who owns login",
        body="The account service owns sessions.",
        actor_kind=ACTOR_USER,
        actor=ACTOR_USER,
    )
    assert added.document is not None
    doc = added.document.path

    # Claude Code writes an item, and a pass merges it into the document.
    world.can_merge = True
    waiting = await world.knowledge.submit(
        collection="shopee",
        title="Session TTL",
        description="how long",
        body="Sessions last 30 days.",
        actor_kind=ACTOR_AGENT,
        actor="claude-code",
    )
    assert waiting.pending is not None
    outcome = await world.curate(
        "shopee",
        Pending(material=waiting.pending),
        [
            (
                "write_document",
                {
                    "path": doc,
                    "title": "Session ownership",
                    "description": "who owns login",
                    "body": "The account service owns sessions.\n\nSessions last 30 days.",
                },
            )
        ],
    )
    assert outcome["status"] == "ok"

    # And the user edits it.
    await _save(world, doc, "The account service owns sessions, which last 30 days.")

    versions = await world.histories.versions(doc)
    assert [(v.change.meta.writer, v.change.meta.operation) for v in versions] == [
        ("user", "save"),
        ("curation", "pass"),
        ("user", "promote"),
    ]
    # The curated version names the agent whose item it curated.
    assert versions[1].change.meta.agent == "claude-code"
    assert versions[1].change.meta.item == f"shopee/{paths.INBOX_DIR_NAME}/{waiting.pending}"
    for version in versions:
        diff = await world.histories.version_diff(doc, version.change.version)
        assert diff.diff.startswith("diff --git"), diff
    assert versions[0].change.time >= versions[-1].change.time

    # Restoring the first version is a new commit; the history keeps all three.
    first = versions[-1].change.version
    await world.histories.restore(doc, first, actor=ACTOR_USER)
    after = await world.histories.versions(doc)
    assert [v.change.meta.operation for v in after] == ["restore", "save", "pass", "promote"]
    assert after[0].change.meta.restored_from == first
    assert _body(doc) == "The account service owns sessions."


async def _three_documents(world: _World) -> tuple[str, str, str]:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    made = [
        fs.write_file(
            directory="shopee", title=title, description="d", body=f"{title} facts.", curated=True
        ).path
        for title in ("Alpha", "Beta", "Gamma")
    ]
    return made[0], made[1], made[2]


@pytest.mark.acceptance(spec="knowledge", scenario="undo a pass as a whole")
async def test_undoing_a_pass_puts_every_document_back(world: _World) -> None:
    alpha, beta, gamma = await _three_documents(world)
    world.can_merge = True
    item = await world.knowledge.submit(
        collection="shopee",
        title="News",
        description="d",
        body="Gamma moved into Beta.",
        actor_kind=ACTOR_USER,
        actor=ACTOR_USER,
    )
    before = {p: _bytes(p) for p in (alpha, beta, gamma)}
    await world.curate(
        "shopee",
        Pending(material=item.pending),
        [
            ("read_document", {"path": gamma}),
            (
                "write_document",
                {"path": alpha, "title": "Alpha", "description": "d", "body": "Alpha, revised."},
            ),
            (
                "write_document",
                {
                    "path": beta,
                    "title": "Beta",
                    "description": "d",
                    "body": "Beta facts. Gamma facts.",
                },
            ),
            ("retire_document", {"path": gamma}),
        ],
    )
    assert not paths.resolve(gamma).exists()
    [pass_] = [c for c in (await world.histories.changes()).changes if c.meta.operation == "pass"]
    assert {d.path for d in pass_.documents} == {alpha, beta, gamma}

    undone = await world.histories.undo(pass_.version, actor=ACTOR_USER)

    # One new commit puts all three back as they were before the pass.
    assert undone.meta.operation == "undo"
    assert undone.meta.undoes == pass_.version
    assert {d.path for d in undone.documents} == {alpha, beta, gamma}
    assert {p: _bytes(p) for p in (alpha, beta, gamma)} == before
    # Put back exactly as curation last left them, so the sweep does not read
    # the undo as a person's edit and redo the pass.
    assert pending_items("shopee") == ()


@pytest.mark.acceptance(
    spec="knowledge", scenario="an undo that would overwrite a later change is refused"
)
async def test_an_undo_over_a_later_edit_is_refused_naming_the_document(world: _World) -> None:
    alpha, _beta, _gamma = await _three_documents(world)
    world.can_merge = True
    item = await world.knowledge.submit(
        collection="shopee",
        title="News",
        description="d",
        body="b",
        actor_kind=ACTOR_USER,
        actor=ACTOR_USER,
    )
    await world.curate(
        "shopee",
        Pending(material=item.pending),
        [
            (
                "write_document",
                {"path": alpha, "title": "Alpha", "description": "d", "body": "By the pass."},
            )
        ],
    )
    pass_version = (await world.histories.versions(alpha))[0].change.version
    await _save(world, alpha, "The user's own words.")
    head = (await world.histories.versions(alpha))[0].change.version

    with pytest.raises(KnowledgeUndoConflict) as refused:
        await world.histories.undo(pass_version, actor=ACTOR_USER)

    assert refused.value.document == alpha
    assert _body(alpha) == "The user's own words."
    # Nothing was written: the newest version is still the user's save.
    assert (await world.histories.versions(alpha))[0].change.version == head


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


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="recent changes lists passes and edits across collections with the waiting items",
)
async def test_recent_changes_across_collections_with_the_waiting_items(world: _World) -> None:
    await world.knowledge.create_collection("shopee", actor=ACTOR_USER)
    await world.knowledge.create_collection("personal", actor=ACTOR_USER)
    note = fs.write_file(
        directory="personal", title="Note", description="d", body="one", curated=True
    ).path
    world.can_merge = True
    item = await world.knowledge.submit(
        collection="shopee",
        title="Gateway",
        description="d",
        body="The gateway routes by region.",
        actor_kind=ACTOR_AGENT,
        actor="codex",
    )
    await world.curate(
        "shopee",
        Pending(material=item.pending),
        [
            (
                "write_document",
                {
                    "title": "Gateway",
                    "description": "d",
                    "body": "Routes by region.\nAnd by tenant.",
                },
            )
        ],
    )
    await _save(world, note, "one\ntwo\nthree")
    for title in ("First waiting", "Second waiting"):
        await world.knowledge.submit(
            collection="shopee",
            title=title,
            description="d",
            body="b",
            actor_kind=ACTOR_AGENT,
            actor="claude-code",
        )

    feed = await world.histories.changes()
    edit, pass_ = feed.changes[0], feed.changes[1]
    assert (edit.collections, edit.meta.writer, edit.meta.operation) == (
        ("personal",),
        "user",
        "save",
    )
    assert (pass_.collections, pass_.meta.writer, pass_.meta.agent) == (
        ("shopee",),
        "curation",
        "codex",
    )
    [written] = pass_.documents
    assert (written.path, written.status) == ("shopee/gateway.md", "added")
    assert written.added > 0
    [changed] = edit.documents
    assert (changed.status, changed.added, changed.removed) == ("modified", 2, 0)
    # Submissions still waiting are not changes; they are the waiting items.
    assert all(c.meta.operation != "submit" for c in feed.changes)
    assert sorted((w.title, w.submitted_by) for w in feed.waiting) == [
        ("First waiting", "claude-code"),
        ("Second waiting", "claude-code"),
    ]

    shopee = await world.histories.changes(collection="shopee")
    assert all(c.collections == ("shopee",) for c in shopee.changes)
    assert shopee.changes[0].version == pass_.version
    assert len(shopee.waiting) == 2
    personal = await world.histories.changes(collection="personal")
    assert personal.waiting == ()
    assert personal.changes[0].version == edit.version

    detail = await world.histories.change(pass_.version)
    assert [d.path for d in detail.diffs] == ["shopee/gateway.md"]
    assert "+Routes by region." in detail.diffs[0].diff


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
    with pytest.raises(KnowledgeHistoryUnavailable):
        await world.histories.versions(added.document.path)
    assert inbox.inbox_items("shopee") == ()
    assert KIND_KNOWLEDGE == "knowledge"
