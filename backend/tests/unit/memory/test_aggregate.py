"""The aggregation pass: the agents' own words, filed by repository.

Aggregation is the **input** half of the layer. It reads each registered,
enabled agent through that agent's reader and writes what it read, verbatim,
under a partition's hidden ``.raw/`` — and it writes nothing else, because
``notes/``, ``MEMORY.md`` and ``RETIRED.md`` all belong to the distil pass
(FR-008, FR-026).

The readers are faked here, per the tier's own rule: a unit test never touches
a developer's real ``~/.claude`` or ``~/.codex``. The store is real, under the
``tmp_path`` the suite-wide ``_isolated_memory_root`` fixture pins
``COFFER_MEMORY_ROOT`` to, because "what is on disk after a pass" is the whole
of what these tests assert. Resolving a **real** repository — a ``git init``, a
real ``git worktree add``, a second clone with a differently-spelled remote —
is the integration tier's, in
``tests/integration/memory/test_partitions_are_repositories.py``.

Three decisions are pinned here, and each is a named past failure:

* an entry **about the person** files into ``global`` whichever repository it
  came from (FR-011);
* a directory inside **no repository** creates no partition of its own
  (FR-015) — six of sixteen partitions on the maintainer's live vault were
  dated scratch folders that the previous design made permanent;
* **the skip is never taken on a digest alone** (FR-019). A digest match says
  the *source* has not changed; it does not say the entries it produced are
  still on disk.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.memory.aggregate import Placement, SourceFailure, run_aggregation
from coffer.application.memory.service import KIND_MEMORY
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.domain.resource import ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.memory import paths, source_state, store
from coffer.infrastructure.memory.raw_store import list_raw_entries
from tests.unit.memory.conftest import (
    FakeAudit,
    FakeReader,
    FakeResources,
    memory_service,
    raw_entry,
)


def _repository(tmp_path: pathlib.Path, name: str, *, remote: str = "") -> pathlib.Path:
    """A directory that looks enough like a checkout for the resolver.

    A real ``git init`` is the integration tier's business; what the *placer*
    needs is a ``.git`` directory with an optional ``origin`` in its config,
    and writing those two files directly keeps this tier free of subprocesses.
    """
    root = tmp_path / name
    git_dir = root / ".git"
    git_dir.mkdir(parents=True)
    if remote:
        (git_dir / "config").write_text(
            f'[core]\n\tbare = false\n[remote "origin"]\n\turl = {remote}\n', encoding="utf-8"
        )
    return root


async def _aggregate(resources: FakeResources, readers: dict[str, FakeReader], **kw: object):  # type: ignore[no-untyped-def]
    audit = kw.pop("audit", None) or FakeAudit()
    service = memory_service(resources, readers, audit=audit)  # type: ignore[arg-type]
    return await service.aggregate(**kw)  # type: ignore[arg-type]


# --- where an entry lands ----------------------------------------------------


@pytest.mark.asyncio
async def test_an_entry_learned_in_a_repository_lands_in_that_repositorys_partition(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", "/cc")
    reader = FakeReader(agent_type="claude_code")
    reader.set_source(
        "/cc",
        "/cc/projects/coffer/memory/f.md",
        "d1",
        (raw_entry("Use a worktree", "Always develop in a worktree.", project_root=str(root)),),
    )

    result = await _aggregate(resources, {"claude_code": reader})

    assert result.partitions == ("coffer",)
    assert result.entries_written == 1
    (stored,) = list_raw_entries("coffer")
    assert stored.entry.body == "Always develop in a worktree."
    assert stored.agent == "claude-code"


@pytest.mark.asyncio
@pytest.mark.parametrize("personal", [TYPE_USER, TYPE_FEEDBACK])
async def test_an_entry_about_the_person_lands_in_global_whichever_repository_it_came_from(
    tmp_path: pathlib.Path, personal: str
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (raw_entry("Reply in Chinese", "Prefers Chinese.", type=personal, project_root=str(root)),),
    )

    result = await _aggregate(resources, {"codex": reader})

    assert result.partitions == ("global",)
    assert [e.entry.title for e in list_raw_entries("global")] == ["Reply in Chinese"]
    assert store.list_partitions() == ("global",)


@pytest.mark.asyncio
async def test_an_entry_learned_in_the_home_directory_itself_is_about_the_person(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("At home", "x", project_root=str(home)),)
    )

    result = await _aggregate(resources, {"codex": reader})

    assert result.partitions == ("global",)


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a directory that is not a repository gets no partition"
)
async def test_a_dated_scratch_directory_creates_no_partition_of_its_own(
    tmp_path: pathlib.Path,
) -> None:
    """The impostor failure: six of sixteen partitions on the live vault were
    one-off session directories that could never reach the repository they
    were actually about (FR-015)."""
    scratch = tmp_path / "Documents" / "Codex" / "2026-09-17" / "some-topic"
    scratch.mkdir(parents=True)
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry(
                "Something incidental", "learned in a scratch folder", project_root=str(scratch)
            ),
        ),
    )

    result = await _aggregate(resources, {"codex": reader})

    assert result.partitions == ("global",)
    assert "some-topic" not in store.list_partitions()
    assert [r[1] for r in resources.rows if r[0] == KIND_MEMORY] == ["global"]
    # Held for the distil pass to judge on its merits, not thrown away.
    assert len(list_raw_entries("global")) == 1


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a directory that is not a repository gets no partition"
)
async def test_a_partition_whose_repository_is_gone_is_reported_as_unresolvable(
    tmp_path: pathlib.Path,
) -> None:
    """FR-016: an orphaned partition is delivered to nobody, and only the
    developer can decide whether that repository is coming back."""
    root = _repository(tmp_path, "vanishing")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry("A", "b", project_root=str(root)),
            raw_entry("A preference", "c", anchor="two", type=TYPE_USER),
        ),
    )
    service = memory_service(resources, {"codex": reader})  # type: ignore[arg-type]
    await service.aggregate()

    assert [p.unresolvable for p in await service.list_partitions() if p.name == "vanishing"] == [
        False
    ]

    import shutil

    shutil.rmtree(root)

    summaries = {p.name: p for p in await service.list_partitions()}
    assert summaries["vanishing"].unresolvable is True
    assert summaries["global"].unresolvable is False  # global is delivered everywhere


@pytest.mark.asyncio
async def test_a_worktree_and_its_checkout_named_by_one_remote_share_one_partition(
    tmp_path: pathlib.Path,
) -> None:
    """The pure half of FR-014, with the ``.git`` written by hand; the real
    ``git worktree add`` is exercised in the integration tier."""
    main = _repository(tmp_path, "coffer", remote="git@github.com:owner/coffer.git")
    clone = _repository(tmp_path, "coffer-second", remote="https://github.com/owner/coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry("From the checkout", "a", anchor="one", project_root=str(main)),
            raw_entry("From the clone", "b", anchor="two", project_root=str(clone)),
        ),
    )

    result = await _aggregate(resources, {"codex": reader})

    assert result.partitions == ("coffer",)
    assert len(list_raw_entries("coffer")) == 2


@pytest.mark.asyncio
async def test_two_repositories_sharing_a_name_are_told_apart_by_their_parent(
    tmp_path: pathlib.Path,
) -> None:
    work = _repository(tmp_path / "work", "api")
    personal = _repository(tmp_path / "personal", "api")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx",
        "/cx/memories/MEMORY.md",
        "d1",
        (
            raw_entry("A", "a", anchor="one", project_root=str(work)),
            raw_entry("B", "b", anchor="two", project_root=str(personal)),
        ),
    )

    result = await _aggregate(resources, {"codex": reader})

    assert "api" in result.partitions
    assert any(name.endswith("-api") for name in result.partitions), result.partitions
    assert not any(name.startswith("partition-") for name in result.partitions)


# --- only ``.raw/`` is written -----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="raw entries land hidden, and only aggregation writes them"
)
async def test_a_pass_writes_raw_entries_and_no_note_index_or_retirement_record(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )

    await _aggregate(resources, {"codex": reader})

    assert len(list_raw_entries("coffer")) == 1
    assert store.list_notes("coffer") == ()
    assert store.read_index("coffer") == ""
    assert store.read_retired("coffer") == ()
    assert sorted(p.name for p in paths.partition_dir("coffer").iterdir()) == [".raw"]


# --- the skip, and the trap under it -----------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an unchanged source file is skipped on the next sync"
)
async def test_an_unchanged_source_is_not_read_at_all_on_the_next_pass(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )
    first = await _aggregate(resources, {"codex": reader})
    assert (first.sources_read, first.sources_skipped) == (1, 0)

    reader.explode_on_read = True  # rigged to raise if consulted again
    second = await _aggregate(resources, {"codex": reader})

    assert (second.sources_read, second.sources_skipped) == (0, 1)
    assert second.failures == ()
    assert len(list_raw_entries("coffer")) == 1


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="deleting the memory tree and re-syncing reproduces an equivalent set"
)
async def test_a_digest_match_alone_never_suppresses_a_rebuild(tmp_path: pathlib.Path) -> None:
    """The trap the source-state cache creates (FR-019, SC-002).

    A digest match says the *source* is unchanged. It does not say the entries
    it produced are still on disk — and deleting the tree with the cache
    deliberately left behind is exactly the case the spec requires to rebuild.
    """
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )
    await _aggregate(resources, {"codex": reader})
    assert source_state.load() == {"/cx/memories/MEMORY.md": "d1"}

    store.delete_partition("coffer")
    assert source_state.load()  # the cache is deliberately left behind

    second = await _aggregate(resources, {"codex": reader})

    assert second.sources_read == 1
    assert second.sources_skipped == 0
    assert [e.entry.title for e in list_raw_entries("coffer")] == ["A"]


@pytest.mark.asyncio
async def test_an_entry_the_agent_deleted_from_its_own_memory_stops_being_stored(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    path = "/cx/memories/MEMORY.md"
    reader.set_source(
        "/cx",
        path,
        "d1",
        (
            raw_entry("Kept", "still true", anchor="one", project_root=str(root)),
            raw_entry("Removed", "the agent deleted this", anchor="two", project_root=str(root)),
        ),
    )
    await _aggregate(resources, {"codex": reader})
    assert len(list_raw_entries("coffer")) == 2

    reader.set_digest("/cx", path, "d2")
    reader.content[path] = (raw_entry("Kept", "still true", anchor="one", project_root=str(root)),)
    await _aggregate(resources, {"codex": reader})

    assert [e.entry.title for e in list_raw_entries("coffer")] == ["Kept"]


# --- failure isolation -------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an agent whose native memory shape is unreadable degrades loudly"
)
async def test_one_agents_unreadable_file_leaves_the_others_aggregation_intact(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", "/cc")
    resources.add_agent("codex", "codex", "/cx")

    broken = FakeReader(agent_type="claude_code")
    broken.set_source(
        "/cc",
        "/cc/projects/coffer/memory/broken.md",
        "d1",
        UnreadableMemory("/cc/projects/coffer/memory/broken.md", "no YAML frontmatter fence"),
    )
    healthy = FakeReader(agent_type="codex")
    healthy.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )

    # A note an earlier pass distilled, which must be left standing (SC-006).
    store.write_note(
        Note(
            slug="standing",
            title="Standing",
            description="from an earlier pass",
            type=TYPE_PROJECT,
            body="body",
            partition="coffer",
            origins=(Origin(agent="codex", native_path="/old.md", anchor="x"),),
        )
    )

    result = await _aggregate(resources, {"claude_code": broken, "codex": healthy})

    assert result.failures == (
        SourceFailure(
            agent="claude-code",
            path="/cc/projects/coffer/memory/broken.md",
            reason="no YAML frontmatter fence",
        ),
    )
    assert [e.agent for e in list_raw_entries("coffer")] == ["codex"]
    assert [n.slug for n in store.list_notes("coffer")] == ["standing"]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an agent whose native memory shape is unreadable degrades loudly"
)
async def test_a_source_that_failed_is_tried_again_next_pass_rather_than_being_cached(
    tmp_path: pathlib.Path,
) -> None:
    """Its digest is deliberately not recorded: a reader broken by a format
    change must not have that treated as the new normal."""
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", "/cc")
    reader = FakeReader(agent_type="claude_code")
    reader.set_source("/cc", "/cc/m.md", "d1", UnreadableMemory("/cc/m.md", "bad fence"))

    await _aggregate(resources, {"claude_code": reader})

    assert source_state.load() == {}
    second = await _aggregate(resources, {"claude_code": reader})
    assert len(second.failures) == 1


@pytest.mark.asyncio
async def test_a_reader_that_raises_something_unexpected_costs_that_file_not_the_pass(
    tmp_path: pathlib.Path,
) -> None:
    """FR-005's isolation is only worth anything if it holds for the failure
    nobody anticipated."""
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source("/cx", "/cx/boom.md", "d1", RuntimeError("a reader bug"))
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d2", (raw_entry("A", "b", project_root=str(root)),)
    )

    result = await _aggregate(resources, {"codex": reader})

    assert result.failures[0].path == "/cx/boom.md"
    assert "RuntimeError" in result.failures[0].reason
    assert result.entries_written == 1


# --- which agents are read at all --------------------------------------------


@pytest.mark.asyncio
async def test_a_disabled_agent_is_not_read(tmp_path: pathlib.Path) -> None:
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx", enabled=False)
    reader = FakeReader(agent_type="codex")
    reader.set_source("/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b"),))

    result = await _aggregate(resources, {"codex": reader})

    assert result.entries_written == 0
    assert reader.read_paths == []


@pytest.mark.asyncio
async def test_an_agent_type_with_no_reader_is_skipped_rather_than_failing_the_pass() -> None:
    """A third agent earns an adapter, not a failure here (FR-045)."""
    resources = FakeResources()
    resources.add_agent("cursor", "cursor", "/cursor")
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source("/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b"),))

    result = await _aggregate(resources, {"codex": reader})

    assert result.failures == ()
    assert result.entries_written == 1


@pytest.mark.asyncio
async def test_a_pass_over_an_idle_machine_writes_nothing_and_reports_it() -> None:
    resources = FakeResources()
    result = await _aggregate(resources, {})
    assert (result.partitions, result.entries_written, result.sources_read) == ((), 0, 0)


# --- the database half -------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a partition is registered as a resource scoped to the agents it came from",
)
async def test_a_new_partitions_scope_is_the_agents_it_was_aggregated_from(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer", remote="git@github.com:owner/coffer.git")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )

    await _aggregate(resources, {"codex": reader})

    row = await resources.get(ResourceRef(KIND_MEMORY, "coffer"))
    assert row.scope == Scope(agents=["codex"])
    assert row.config["repository_path"] == str(root)
    assert row.config["repository_key"] == "remote:github.com/owner/coffer"


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a partition is registered as a resource scoped to the agents it came from",
)
async def test_a_later_pass_leaves_a_scope_the_developer_narrowed_alone(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    resources.add_agent("claude-code", "claude_code", "/cc")
    codex = FakeReader(agent_type="codex")
    codex.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )
    claude = FakeReader(agent_type="claude_code")
    claude.set_source(
        "/cc", "/cc/m.md", "d1", (raw_entry("B", "c", anchor="two", project_root=str(root)),)
    )
    readers = {"codex": codex, "claude_code": claude}
    await _aggregate(resources, readers)

    ref = ResourceRef(KIND_MEMORY, "coffer")
    await resources.update_scope(ref, Scope(agents=["codex"]), actor="user")
    codex.set_digest("/cx", "/cx/memories/MEMORY.md", "d2")

    await _aggregate(resources, readers)

    assert (await resources.get(ref)).scope == Scope(agents=["codex"])


@pytest.mark.asyncio
async def test_a_pass_records_one_audit_event_naming_its_actor(tmp_path: pathlib.Path) -> None:
    """So the log can tell a scheduled pass from a requested one (FR-038)."""
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("codex", "codex", "/cx")
    reader = FakeReader(agent_type="codex")
    reader.set_source(
        "/cx", "/cx/memories/MEMORY.md", "d1", (raw_entry("A", "b", project_root=str(root)),)
    )
    audit = FakeAudit()

    await _aggregate(
        resources, {"codex": reader}, audit=audit, actor="system:memory-aggregate-worker"
    )

    assert len(audit.events) == 1
    event_type, actor, details = audit.events[0]
    assert event_type == "memory_aggregated"
    assert actor == "system:memory-aggregate-worker"
    assert details["entries_written"] == 1
    assert details["partitions"] == ["coffer"]


@pytest.mark.asyncio
async def test_a_partitions_notes_are_read_from_disk_on_every_call(tmp_path: pathlib.Path) -> None:
    """``list_notes`` opens the directory every time, which is what makes a
    retirement hold on this path — the previous design served a value it had
    already computed and went on handing back 11 dead facts."""
    resources = FakeResources()
    await resources.register(
        kind=KIND_MEMORY, name="coffer", config={}, actor="t", allow_lifecycle_kind=True
    )
    service = memory_service(resources, {})  # type: ignore[arg-type]
    assert await service.list_notes("coffer") == ()

    store.write_note(
        Note(
            slug="fresh",
            title="Fresh",
            description="d",
            type=TYPE_PROJECT,
            body="b",
            partition="coffer",
        )
    )

    assert [n.slug for n in await service.list_notes("coffer")] == ["fresh"]


@pytest.mark.asyncio
async def test_a_partition_out_of_an_agents_scope_reads_as_absent_rather_than_forbidden(
    tmp_path: pathlib.Path,
) -> None:
    resources = FakeResources()
    await resources.register(
        kind=KIND_MEMORY, name="coffer", config={}, actor="t", allow_lifecycle_kind=True
    )
    await resources.update_scope(
        ResourceRef(KIND_MEMORY, "coffer"), Scope(agents=["codex"]), actor="t"
    )
    store.write_note(
        Note(slug="n", title="N", description="d", type=TYPE_PROJECT, body="b", partition="coffer")
    )
    service = memory_service(resources, {})  # type: ignore[arg-type]

    assert await service.list_notes("coffer", agent="claude-code") == ()
    assert [n.slug for n in await service.list_notes("coffer", agent="codex")] == ["n"]
    assert await service.visible_partitions("claude-code") == []


@pytest.mark.asyncio
async def test_deleting_a_partition_takes_its_directory_with_it(tmp_path: pathlib.Path) -> None:
    store.write_note(
        Note(slug="n", title="N", description="d", type=TYPE_PROJECT, body="b", partition="coffer")
    )
    service = memory_service(FakeResources(), {})  # type: ignore[arg-type]

    await service.cleanup_partition("coffer")

    assert not paths.partition_dir("coffer").exists()


def test_a_placement_for_global_names_neither_a_repository_nor_a_path() -> None:
    from coffer.application.memory.aggregate import GLOBAL_PLACEMENT

    assert Placement(name="global", repository_key="", repository_path="") == GLOBAL_PLACEMENT


def test_run_aggregation_over_no_agents_writes_nothing() -> None:
    outcome = run_aggregation(agents=[], readers={}, known=[])
    assert outcome.result.partitions == ()
    assert outcome.touched == ()
