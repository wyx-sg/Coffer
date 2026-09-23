"""One repository, one partition — against real git trees.

See "Identify a partition by its repository" and "Create no partition for a
non-repository directory".

A partition used to be keyed on the working directory a fact was learned in,
and measured on the maintainer's live vault that produced three failures at
once: a worktree filed away from its own checkout, an orphan partition nothing
could resolve to, and six dated scratch folders turned into permanent
partitions.

The fixtures here are real: ``git init``, a real ``git worktree add`` (whose
``.git`` is a *file* pointing at a private directory whose ``commondir``
points back), and a real second clone whose ``origin`` is set to a different
but equivalent spelling of the same URL. Coffer parses all three by hand
rather than shelling out, so a fixture that wrote them by hand would be
testing this test's idea of git instead of git's.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.memory.service import KIND_MEMORY
from coffer.domain.memory.note import TYPE_USER
from coffer.infrastructure.memory import store
from coffer.infrastructure.memory.raw_store import list_raw_entries
from coffer.infrastructure.memory.repository import resolve_repository
from tests.integration.memory.conftest import (
    FakeResources,
    init_repository,
    second_clone,
    worktree_of,
)
from tests.unit.memory.conftest import FakeReader, memory_service, raw_entry

_REMOTE_SSH = "git@github.com:owner/coffer.git"
_REMOTE_HTTPS = "https://github.com/owner/coffer"


@pytest.fixture
def three_checkouts(tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    """The main checkout, a worktree of it, and a second clone of the same
    upstream under a different local directory name."""
    main = init_repository(tmp_path / "coffer", remote=_REMOTE_SSH)
    tree = worktree_of(main, tmp_path / "worktrees" / "feature-x")
    clone = second_clone(main, tmp_path / "coffer-copy", remote=_REMOTE_HTTPS)
    return {"main": main, "worktree": tree, "clone": clone}


# --- the resolver, against the real thing ------------------------------------


def test_a_worktree_resolves_to_its_main_checkout(three_checkouts: dict) -> None:
    """The ``.git`` file's ``gitdir:`` points at a private directory under the
    main checkout, whose ``commondir`` names the shared ``.git`` — following
    both hops is what collapses a worktree into its repository."""
    resolved = resolve_repository(three_checkouts["worktree"])

    assert resolved is not None
    assert pathlib.Path(resolved.root) == three_checkouts["main"].resolve()
    assert resolved.key == resolve_repository(three_checkouts["main"]).key  # type: ignore[union-attr]


def test_a_directory_deep_inside_a_worktree_resolves_the_same_way(
    three_checkouts: dict,
) -> None:
    nested = three_checkouts["worktree"] / "backend" / "coffer"
    nested.mkdir(parents=True)

    resolved = resolve_repository(nested)

    assert resolved is not None
    assert pathlib.Path(resolved.root) == three_checkouts["main"].resolve()


def test_two_clones_with_differently_spelled_remotes_share_one_key(
    three_checkouts: dict,
) -> None:
    main = resolve_repository(three_checkouts["main"])
    clone = resolve_repository(three_checkouts["clone"])

    assert main is not None and clone is not None
    assert main.remote_url == _REMOTE_SSH
    assert clone.remote_url == _REMOTE_HTTPS
    assert main.key == clone.key == "remote:github.com/owner/coffer"
    assert main.name == clone.name == "coffer"


def test_a_repository_with_no_remote_is_identified_by_its_own_path(
    tmp_path: pathlib.Path,
) -> None:
    root = init_repository(tmp_path / "local-only")

    resolved = resolve_repository(root)

    assert resolved is not None
    assert resolved.remote_url == ""
    assert resolved.key == f"path:{root.resolve()}"


def test_a_directory_in_no_repository_resolves_to_nothing(tmp_path: pathlib.Path) -> None:
    scratch = tmp_path / "Documents" / "Codex" / "2026-09-17"
    scratch.mkdir(parents=True)
    assert resolve_repository(scratch) is None


def test_a_directory_that_no_longer_exists_resolves_to_nothing(tmp_path: pathlib.Path) -> None:
    """A working directory an agent recorded months ago may be gone; that is a
    normal answer with a normal consequence, not an error ("Report unresolvable
    partitions")."""
    assert resolve_repository(tmp_path / "deleted" / "months" / "ago") is None


def test_a_stale_worktree_pointer_does_not_crash_the_walk(three_checkouts: dict) -> None:
    """A ``gitdir:`` naming a directory somebody deleted is an ordinary state
    of a developer's disk."""
    import shutil

    tree = three_checkouts["worktree"]
    shutil.rmtree(three_checkouts["main"] / ".git" / "worktrees")

    assert resolve_repository(tree) is None


# --- the pass, which is what the resolver is for -----------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a worktree and its main checkout resolve to one partition"
)
async def test_three_checkouts_of_one_repository_file_into_one_partition(
    three_checkouts: dict,
) -> None:
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry(
                "From the checkout", "a", anchor="one", project_root=str(three_checkouts["main"])
            ),
            raw_entry(
                "From the worktree",
                "b",
                anchor="two",
                project_root=str(three_checkouts["worktree"]),
            ),
            raw_entry(
                "From the clone", "c", anchor="three", project_root=str(three_checkouts["clone"])
            ),
        ),
    )
    service = memory_service(resources, {"codex": reader})  # type: ignore[arg-type]

    result = await service.aggregate()

    assert result.partitions == ("coffer",)
    assert store.list_partitions() == ("coffer",)
    assert len(list_raw_entries("coffer")) == 3


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a worktree and its main checkout resolve to one partition"
)
async def test_the_partition_is_named_from_the_repository_and_records_its_path(
    three_checkouts: dict,
) -> None:
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (raw_entry("A", "b", project_root=str(three_checkouts["worktree"])),),
    )
    service = memory_service(resources, {"codex": reader})  # type: ignore[arg-type]

    await service.aggregate()

    row = resources.by_name(KIND_MEMORY, "coffer")
    assert row.config["repository_key"] == "remote:github.com/owner/coffer"
    # The main checkout's path, not the worktree's, so a later session's cwd
    # matches whichever of the three it is opened in.
    assert row.config["repository_path"] == str(three_checkouts["main"].resolve())


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a directory that is not a repository gets no partition"
)
async def test_a_scratch_directory_beside_a_repository_creates_no_partition(
    tmp_path: pathlib.Path,
) -> None:
    repository = init_repository(tmp_path / "coffer", remote=_REMOTE_SSH)
    scratch = tmp_path / "Documents" / "Codex" / "2026-09-17" / "a-topic"
    scratch.mkdir(parents=True)
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry("Real project material", "a", anchor="one", project_root=str(repository)),
            raw_entry("Incidental", "b", anchor="two", project_root=str(scratch)),
            raw_entry(
                "A preference", "c", anchor="three", type=TYPE_USER, project_root=str(scratch)
            ),
        ),
    )
    service = memory_service(resources, {"codex": reader})  # type: ignore[arg-type]

    result = await service.aggregate()

    assert sorted(result.partitions) == ["coffer", "global"]
    assert "a-topic" not in store.list_partitions()
    assert [p.name for p in await service.list_partitions()] == ["coffer", "global"]
    # The scratch entry is held for the distil pass to judge, not discarded.
    assert {e.entry.title for e in list_raw_entries("global")} == {"Incidental", "A preference"}


@pytest.mark.asyncio
async def test_a_repository_under_another_ones_directory_gets_its_own_partition(
    tmp_path: pathlib.Path,
) -> None:
    outer = init_repository(tmp_path / "outer")
    inner = init_repository(outer / "vendor" / "inner")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry("Outer", "a", anchor="one", project_root=str(outer)),
            raw_entry("Inner", "b", anchor="two", project_root=str(inner)),
        ),
    )
    service = memory_service(resources, {"codex": reader})  # type: ignore[arg-type]

    result = await service.aggregate()

    assert sorted(result.partitions) == ["inner", "outer"]
