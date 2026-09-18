"""Renaming a partition moves the directory its name IS.

The mirror of ``tests/unit/knowledge/test_rename.py``, and the same argument:
a ``memory`` row's name is a path segment under ``~/.coffer/memory/``, so a
rename that only moved the label would leave the row naming an empty folder.
These drive the kind's own ``on_rename`` hook — what ``ResourceService.rename``
actually calls — and assert against the files, because "the notes are still
there afterwards" is the whole claim.

Being derived does not make this cheap. Aggregation would refill the new
directory from the agents' *current* memory, so what a missed move loses is
everything the layer had accumulated on top of that: the notes the distil pass
wrote, and ``RETIRED.md``, without which the next pass re-imports every note a
person deliberately removed.
"""

from __future__ import annotations

import pytest

from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.domain.errors import ConfigValidationError, ResourceAlreadyExists
from coffer.domain.memory.note import TYPE_PROJECT, Note
from coffer.domain.memory.partition import GLOBAL_PARTITION
from coffer.domain.memory.reader import RawEntry
from coffer.domain.memory.retired import RetiredNote
from coffer.domain.resource import Kind, Resource
from coffer.infrastructure.memory import paths, store
from coffer.infrastructure.memory.raw_store import StoredRawEntry, list_raw_entries, write_raw_entry
from tests.unit.memory.conftest import FakeResources, memory_service

pytestmark = pytest.mark.asyncio


def _fill(partition: str) -> None:
    """One partition with all four of the things a move has to carry."""
    store.write_note(
        Note(
            slug="who-owns-login",
            title="Who owns login state",
            description="account.session issues and revokes the token.",
            type=TYPE_PROJECT,
            body="`account.session` owns it.",
            partition=partition,
        )
    )
    store.write_index(partition, "# Memory\n\n- who-owns-login\n")
    store.write_retired(
        partition,
        [RetiredNote(slug="stale", title="Stale", reason="superseded", retired_at="2026-01-01")],
    )
    write_raw_entry(
        StoredRawEntry(
            partition=partition,
            agent="codex",
            native_path="/cx/memories/MEMORY.md",
            captured_at="2026-01-01T00:00:00+00:00",
            entry=RawEntry(
                title="Who owns login state",
                description="d",
                type=TYPE_PROJECT,
                body="account.session",
                anchor="login",
                project_root="/repo",
                source_written_at="",
            ),
        )
    )


def _service(resources: FakeResources) -> MemoryService:
    return memory_service(resources, {})


def _kind(resources: FakeResources) -> Kind:
    return make_memory_kind(_service(resources))


async def _register(resources: FakeResources, name: str) -> Resource:
    return await resources.register(
        kind=KIND_MEMORY, name=name, config={}, actor="t", allow_lifecycle_kind=True
    )


async def _rename(resources: FakeResources, row: Resource, new_name: str) -> None:
    """The hook, then the label — the order ``ResourceService.rename`` uses.

    Pre-write on purpose: the hook is handed the resource as it still stands,
    so a refusal leaves the row exactly as the caller found it.
    """
    hook = _kind(resources).on_rename
    assert hook is not None, "the memory kind must supply on_rename"
    await hook(row, new_name)  # type: ignore[misc]
    row.name = new_name


@pytest.mark.acceptance(
    spec="resource-framework",
    scenario="a kind whose name is a directory moves it with the rename",
)
async def test_renaming_a_partition_moves_its_directory() -> None:
    resources = FakeResources()
    row = await _register(resources, "coffer")
    _fill("coffer")

    await _rename(resources, row, "coffer-vault")

    assert not paths.partition_dir("coffer").exists()
    assert paths.partition_dir("coffer-vault").is_dir()


async def test_the_notes_inside_are_still_readable_under_the_new_name() -> None:
    """One move takes all four writers' output with it.

    The note is checked through ``list_notes``, which opens the directory:
    that is the read every surface makes, and it is the one that would come
    back empty if the folder had stayed behind.
    """
    resources = FakeResources()
    row = await _register(resources, "coffer")
    _fill("coffer")
    before = store.list_notes("coffer")

    await _rename(resources, row, "coffer-vault")

    after = store.list_notes("coffer-vault")
    assert [n.slug for n in after] == [n.slug for n in before]
    assert after[0].body == before[0].body
    # A note reports the partition it was read from, so the moved copy names
    # the new one: the directory is the authority, not anything in the file.
    assert after[0].partition == "coffer-vault"
    assert store.read_index("coffer-vault").startswith("# Memory")
    assert [r.slug for r in store.read_retired("coffer-vault")] == ["stale"]
    assert [e.agent for e in list_raw_entries("coffer-vault")] == ["codex"]


async def test_the_service_serves_the_partition_under_its_new_name() -> None:
    """Row and directory have to agree, because the read path uses both: the
    registry says which partitions are served, the directory says what is in
    them."""
    resources = FakeResources()
    row = await _register(resources, "coffer")
    _fill("coffer")

    await _rename(resources, row, "coffer-vault")
    service = _service(resources)

    assert await service.enabled_partitions() == ["coffer-vault"]
    assert [n.slug for n in await service.list_notes("coffer-vault")] == ["who-owns-login"]


async def test_global_cannot_be_renamed() -> None:
    """The one partition the layer names in code.

    ``GLOBAL_PARTITION`` is where aggregation files a personal entry and a
    directory inside no repository, and where composing a session's context
    looks for what is known about the developer. Renaming the row would move
    the notes out from under all of that and the next pass would start a fresh,
    empty ``global`` beside it — so it is refused rather than half-supported.
    """
    resources = FakeResources()
    row = await _register(resources, GLOBAL_PARTITION)
    _fill(GLOBAL_PARTITION)

    with pytest.raises(ConfigValidationError):
        await _rename(resources, row, "personal")

    assert row.name == GLOBAL_PARTITION
    assert paths.partition_dir(GLOBAL_PARTITION).is_dir()
    assert not paths.partition_dir("personal").exists()


async def test_a_directory_already_under_the_new_name_aborts_the_rename() -> None:
    """Merging is the specific harm, and the tree being derived does not undo
    it: two repositories' raw entries in one partition is what keying on a
    repository exists to prevent, and the next pass would refill the merged
    directory rather than unpick it."""
    resources = FakeResources()
    row = await _register(resources, "coffer")
    _fill("coffer")
    _fill("other")

    with pytest.raises(ResourceAlreadyExists):
        await _rename(resources, row, "other")

    assert row.name == "coffer"
    assert [n.slug for n in store.list_notes("coffer")] == ["who-owns-login"]
    assert [n.slug for n in store.list_notes("other")] == ["who-owns-login"]


async def test_an_empty_directory_under_the_new_name_is_refused_too() -> None:
    """Explicit, because POSIX ``rename`` would have let this one through: it
    fails on a non-empty target directory and succeeds silently over an empty
    one."""
    resources = FakeResources()
    row = await _register(resources, "coffer")
    _fill("coffer")
    paths.partition_dir("other").mkdir(parents=True)

    with pytest.raises(ResourceAlreadyExists):
        await _rename(resources, row, "other")

    assert paths.partition_dir("coffer").is_dir()


async def test_a_row_whose_directory_is_gone_still_renames() -> None:
    """Nothing to move, and nothing gained by refusing: the next aggregation
    pass writes the directory under whatever name the row now carries."""
    resources = FakeResources()
    row = await _register(resources, "coffer")

    await _rename(resources, row, "coffer-vault")

    assert row.name == "coffer-vault"
