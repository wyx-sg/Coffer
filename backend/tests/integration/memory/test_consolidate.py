"""Store consolidation: pure-fs lane merge + end-to-end stale-store collapse."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.memory.consolidate import StoreConsolidator, merge_store_dir
from coffer.application.memory.scope import project_store_name
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.paths import journal_path, topic_path
from coffer.infrastructure.memory.journal_files import append_entry, read_entries
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.scope_fs import project_ulid
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo


def _ts(day: int, hour: int) -> datetime:
    return datetime(2026, 7, day, hour, tzinfo=UTC)


# ----- pure-fs merge_store_dir -----


def test_merge_journal_dedupes_by_timestamp_and_keeps_both_days(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    # dst already has a 07-01 entry; src has a duplicate 07-01 ts + a new one + a new day
    append_entry(journal_path(dst, "2026-07-01"), timestamp=_ts(1, 10), body="orig")
    append_entry(journal_path(src, "2026-07-01"), timestamp=_ts(1, 10), body="orig")  # dup ts
    append_entry(journal_path(src, "2026-07-01"), timestamp=_ts(1, 12), body="new-same-day")
    append_entry(journal_path(src, "2026-07-05"), timestamp=_ts(5, 9), body="new-day")

    merged = merge_store_dir(src, dst, tag="ABCDE")

    day1 = [e.body for e in read_entries(journal_path(dst, "2026-07-01"))]
    assert day1 == ["orig", "new-same-day"]  # duplicate ts collapsed, order preserved
    day5 = [e.body for e in read_entries(journal_path(dst, "2026-07-05"))]
    assert day5 == ["new-day"]
    assert merged == 2  # 07-01 file changed + 07-05 file created


def test_merge_keeps_both_on_topic_name_collision(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    topic_path(dst, "auth").parent.mkdir(parents=True, exist_ok=True)
    topic_path(dst, "auth").write_text("dst-auth\n", encoding="utf-8")
    topic_path(src, "auth").parent.mkdir(parents=True, exist_ok=True)
    topic_path(src, "auth").write_text("src-auth\n", encoding="utf-8")

    merge_store_dir(src, dst, tag="9E9E")

    assert topic_path(dst, "auth").read_text() == "dst-auth\n"  # winner untouched
    kept = (dst / "knowledge" / "auth--from-9E9E.md").read_text()
    assert kept == "src-auth\n"  # incoming preserved under a suffixed name


def test_merge_skips_derived_index_files(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / "knowledge").mkdir(parents=True)
    (src / "knowledge" / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (src / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    (src / "consolidation-log.md").write_text("log\n", encoding="utf-8")

    assert merge_store_dir(src, dst, tag="X") == 0
    assert not (dst / "knowledge" / "INDEX.md").exists()
    assert not (dst / "MEMORY.md").exists()


def test_merge_absent_src_is_noop(tmp_path):
    assert merge_store_dir(tmp_path / "nope", tmp_path / "dst", tag="X") == 0


# ----- end-to-end StoreConsolidator.run() -----


@pytest.mark.asyncio
async def test_consolidator_collapses_stale_worktree_store(mem):
    roots = ProjectRootRepo(mem.sm)
    labels = StoreLabelRepo(mem.sm)

    canonical_root = "/repo-main"
    stale_root = "/repo-main/.wt/feature"  # a worktree path of the same repo
    canonical_store = project_store_name(project_ulid(canonical_root))
    stale_store = project_store_name(project_ulid(stale_root))
    assert canonical_store != stale_store  # the pre-fix fragmentation

    # After the git_root fix, BOTH paths resolve to the main repo root.
    def fake_git_root(cwd: str):
        return pathlib.Path(canonical_root)

    cfg = MemoryStoreConfig().model_dump(mode="json")
    canonical_dir = paths.memory_store_dir(project_ulid(canonical_root))
    stale_dir = paths.memory_store_dir(project_ulid(stale_root))

    # Canonical store: pre-existing journal entry that MUST survive untouched.
    append_entry(journal_path(canonical_dir, "2026-07-01"), timestamp=_ts(1, 8), body="canon")
    await mem.resources.register(kind="memory", name=canonical_store, config=cfg, actor="system")
    await roots.set(canonical_store, canonical_root)

    # Stale worktree store: a same-day (distinct ts) + a new-day journal entry, a
    # knowledge topic, and a user label — none of which may be lost.
    append_entry(journal_path(stale_dir, "2026-07-01"), timestamp=_ts(1, 15), body="wt-day1")
    append_entry(journal_path(stale_dir, "2026-07-06"), timestamp=_ts(6, 9), body="wt-day6")
    await mem.resources.register(kind="memory", name=stale_store, config=cfg, actor="system")
    await roots.set(stale_store, stale_root)
    await labels.set(stale_store, "Feature WT")

    report = await StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=roots,
        labels=labels,
        store_dir=paths.memory_store_dir,
        git_root=fake_git_root,
        project_ulid=project_ulid,
    ).run()

    # The stale store was merged and fully retired.
    assert report.merged_stores == [stale_store]
    with pytest.raises(ResourceNotFound):
        await mem.resources.get(ResourceRef(kind="memory", name=stale_store))
    assert await roots.get(stale_store) is None
    assert await labels.get(stale_store) is None
    assert not stale_dir.exists()

    # Canonical store kept its own data and gained the stale store's.
    day1 = {e.body for e in read_entries(journal_path(canonical_dir, "2026-07-01"))}
    assert day1 == {"canon", "wt-day1"}  # additive, no clobber
    day6 = {e.body for e in read_entries(journal_path(canonical_dir, "2026-07-06"))}
    assert day6 == {"wt-day6"}
    assert await labels.get(canonical_store) == "Feature WT"  # label moved (canon had none)
    assert await roots.get(canonical_store) == canonical_root

    # Reconcile indexed the merged journal into documents.
    doc = await mem.documents.get_document("memory", canonical_store, "journal-2026-07-06")
    assert doc is not None


@pytest.mark.asyncio
async def test_consolidator_is_idempotent_and_leaves_canonical_alone(mem):
    roots = ProjectRootRepo(mem.sm)
    labels = StoreLabelRepo(mem.sm)
    canonical_root = "/solo-repo"
    canonical_store = project_store_name(project_ulid(canonical_root))

    def fake_git_root(cwd: str):
        return pathlib.Path(canonical_root)

    cfg = MemoryStoreConfig().model_dump(mode="json")
    canonical_dir = paths.memory_store_dir(project_ulid(canonical_root))
    append_entry(journal_path(canonical_dir, "2026-07-02"), timestamp=_ts(2, 9), body="solo")
    await mem.resources.register(kind="memory", name=canonical_store, config=cfg, actor="system")
    await roots.set(canonical_store, canonical_root)

    consolidator = StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=roots,
        labels=labels,
        store_dir=paths.memory_store_dir,
        git_root=fake_git_root,
        project_ulid=project_ulid,
    )
    first = await consolidator.run()
    second = await consolidator.run()

    assert first.merged_stores == [] and second.merged_stores == []
    assert await roots.get(canonical_store) == canonical_root
    assert {e.body for e in read_entries(journal_path(canonical_dir, "2026-07-02"))} == {"solo"}


@pytest.mark.asyncio
async def test_consolidator_skips_unresolvable_root(mem):
    """A recorded root whose worktree is gone (git_root → None) is left intact,
    never silently dropped."""
    roots = ProjectRootRepo(mem.sm)
    labels = StoreLabelRepo(mem.sm)
    gone_root = "/deleted/worktree"
    store = project_store_name(project_ulid(gone_root))
    await mem.resources.register(
        kind="memory",
        name=store,
        config=MemoryStoreConfig().model_dump(mode="json"),
        actor="system",
    )
    await roots.set(store, gone_root)

    report = await StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=roots,
        labels=labels,
        store_dir=paths.memory_store_dir,
        git_root=lambda cwd: None,  # unresolvable
        project_ulid=project_ulid,
    ).run()

    assert report.unresolvable == [store]
    assert await roots.get(store) == gone_root  # untouched
