"""Renaming a collection moves the directory its name IS.

A ``knowledge`` row's name is a path segment under ``~/.coffer/knowledge/``,
so the rename the framework offers every kind (ADR
resource-identity-is-an-immutable-uid) is only half a rename here until the
folder follows. These tests drive the kind's own ``on_rename`` hook — the same
callable ``ResourceService.rename`` invokes — rather than a helper written for
the test, because the hook is the whole of what rename costs this kind and a
test of anything else would not notice it going missing.

They assert against the FILES, not against a return value: what makes a rename
correct here is that the documents a person wrote are still readable afterwards,
at the new name.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.domain.errors import ResourceAlreadyExists
from coffer.domain.resource import Kind, Resource
from coffer.infrastructure.knowledge import fs, paths


class _Resources:
    """Enough ``ResourceService`` for the service's read paths."""

    def __init__(self, rows: list[Resource]) -> None:
        self._rows = rows

    async def list(self, kind=None, enabled=None):  # type: ignore[no-untyped-def]
        return [r for r in self._rows if enabled is None or r.enabled is enabled]


class _Audit:
    async def record(self, event_type, **kwargs):  # type: ignore[no-untyped-def]
        return None


def _row(name: str) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        uid="uid-1",
        kind=KIND_KNOWLEDGE,
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
        scope=None,
    )


@pytest.fixture(autouse=True)
def knowledge_root(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    return tmp_path / "knowledge"


@pytest.fixture
def collection() -> Resource:
    """One collection on disk with two documents, a pending item and a README."""
    row = _row("shopee")
    fs.create_collection_dir(row.name)
    paths.readme_path(row.name).write_text("# shopee\n\nThe account system.\n", encoding="utf-8")
    fs.write_file(
        directory="shopee",
        title="Session facts",
        description="Who owns login state.",
        body="`account.session` owns it.",
        actor="user",
    )
    fs.write_file(
        directory="shopee/account",
        title="session — who owns login state",
        description="Which service issues a login token.",
        body="account.session.",
    )
    fs.submit_material(row.name, title="Waiting", description="d", body="not merged yet")
    return row


def _kind(row: Resource) -> Kind:
    return make_knowledge_kind(KnowledgeService(resources=_Resources([row]), audit=_Audit()))  # type: ignore[arg-type]


async def _rename(row: Resource, new_name: str) -> None:
    """Exactly what ``ResourceService.rename`` does with the hook, and nothing
    else: fire it, then move the label. The row is mutated afterwards because
    the hook runs PRE-write and is handed the resource as it still stands."""
    hook = _kind(row).on_rename
    assert hook is not None, "the knowledge kind must supply on_rename"
    await hook(row, new_name)  # type: ignore[misc]
    row.name = new_name


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a kind whose name is a directory moves it with the rename",
)
async def test_renaming_a_collection_moves_its_directory(collection: Resource) -> None:
    old = paths.collection_dir("shopee")
    assert old.is_dir()

    await _rename(collection, "account")

    assert not old.exists()
    assert paths.collection_dir("account").is_dir()


@pytest.mark.asyncio
async def test_the_files_inside_are_still_readable_under_the_new_name(
    collection: Resource,
) -> None:
    """The point of moving the directory rather than recreating it.

    The documents, the inbox and the README travel, with their bytes intact — a rename is a
    relabelling, and a person who renames a collection has not asked for any of
    their writing to change.
    """
    before = {entry.path: fs.read_file(entry.path).body for entry in _walk("shopee")}
    assert before, "the fixture must have written something to move"

    await _rename(collection, "account")

    for old_path, body in before.items():
        moved = old_path.replace("shopee/", "account/", 1)
        assert fs.read_file(moved).body == body
    assert paths.readme_path("account").read_text(encoding="utf-8").startswith("# shopee")
    assert fs.read_material("account", "waiting.md").body.strip() == "not merged yet"


def _walk(relpath: str) -> tuple:
    from coffer.infrastructure.knowledge import catalogue

    return catalogue.walk_files(paths.resolve(relpath))


@pytest.mark.asyncio
async def test_a_collection_the_service_can_reach_is_the_renamed_one(
    collection: Resource,
) -> None:
    """The service reads the directory the row names, so the two have to agree.

    This is the failure a missing hook would produce and the reason the hook
    aborts the rename when it cannot move: the row would say ``account`` while
    the corpus sat under ``shopee``, and every read would answer as if the
    collection had been emptied.
    """
    service = KnowledgeService(resources=_Resources([collection]), audit=_Audit())  # type: ignore[arg-type]

    await _rename(collection, "account")

    assert await service.enabled_collections() == ["account"]
    [level] = [await service.list_level("account")]
    assert [f.path for f in level.files] == ["account/session-facts.md"]


@pytest.mark.asyncio
async def test_a_directory_already_under_the_new_name_aborts_the_rename(
    collection: Resource,
) -> None:
    """A folder with no row behind it is a collision, not something to merge.

    The framework only checked that no ``knowledge`` ROW holds the new name.
    A directory can be there anyway — somebody made it by hand, or a failed
    cleanup left it — and both ways of proceeding are wrong: merging adopts
    files into the corpus that nobody registered, and replacing destroys them.
    So the hook raises, and because it is pre-write the row keeps its name and
    nothing on disk has moved.
    """
    stray = paths.collection_dir("account")
    stray.mkdir(parents=True)
    (stray / "not-ours.md").write_text("someone else's\n", encoding="utf-8")

    with pytest.raises(ResourceAlreadyExists):
        await _rename(collection, "account")

    assert collection.name == "shopee"
    assert paths.collection_dir("shopee").is_dir()
    assert (stray / "not-ours.md").read_text(encoding="utf-8") == "someone else's\n"


@pytest.mark.asyncio
async def test_an_empty_directory_under_the_new_name_is_refused_too(
    collection: Resource,
) -> None:
    """Checked explicitly because ``rename(2)`` would not check it for us.

    POSIX rename fails on a non-empty target directory but succeeds silently
    over an empty one, so relying on the OS to report the collision would make
    the refusal depend on whether the stray folder happened to have anything
    in it.
    """
    paths.collection_dir("account").mkdir(parents=True)

    with pytest.raises(ResourceAlreadyExists):
        await _rename(collection, "account")

    assert paths.collection_dir("shopee").is_dir()


@pytest.mark.asyncio
async def test_a_row_whose_directory_is_gone_can_still_be_renamed(
    collection: Resource, knowledge_root: pathlib.Path
) -> None:
    """The asymmetry with the collision above, and it is deliberate.

    A row with no directory is already broken. Refusing to rename it would
    take away the one thing about it the user can still change, and the rename
    makes nothing worse: there was nothing to move either way.
    """
    fs.remove_collection_dir("shopee")

    await _rename(collection, "account")

    assert collection.name == "account"
    assert not paths.collection_dir("account").exists()
