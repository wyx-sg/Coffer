"""Store consolidation: pure-fs lane merge + end-to-end stale-store collapse.

Three layers over real SQLite + real lane files:

- ``merge_store_dir`` — the byte-level, additive, retry-idempotent file merge.
- ``StoreConsolidator`` — the boot pass (``run``) and the resolve-time
  adoption (``adopt``): merge, alias bookkeeping, label/root carry-over,
  reconcile, retire.
- ``ScopeResolver`` alias redirect — a merged-away identity resolves to the
  surviving store instead of re-provisioning an empty duplicate.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.knowledge.consolidate import (
    StoreConsolidator,
    find_alias_holder,
    merge_store_dir,
)
from coffer.application.knowledge.scope import (
    KnowledgeScope,
    ScopeResolver,
    project_scope_name,
)
from coffer.domain.errors import ResourceNotFound
from coffer.domain.knowledge.document import KIND_KNOWLEDGE
from coffer.domain.knowledge.scope_config import KnowledgeConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.paths import note_path, notes_dir
from coffer.infrastructure.knowledge_scope.project_root_repo import ProjectRootRepo
from coffer.infrastructure.knowledge_scope.scope_fs import project_ulid
from coffer.infrastructure.knowledge_scope.store_label_repo import StoreLabelRepo

_SRC_ULID = "B" * 26
_DST_ULID = "A" * 26
_OLD_ULID = "C" * 26  # already merged into SRC before the test (transitivity)
_SRC = project_scope_name(_SRC_ULID)
_DST = project_scope_name(_DST_ULID)


def _write_note(store_dir: pathlib.Path, slug: str, body: str) -> None:
    """Write a raw ``notes/<slug>.md`` lane file (the merge is byte-level)."""
    path = note_path(store_dir, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _consolidator(mem, *, resolves_to: str = _DST_ULID) -> StoreConsolidator:
    return StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=ProjectRootRepo(mem.sm),
        labels=StoreLabelRepo(mem.sm),
        scope_dir=paths.scope_dir,
        git_root=lambda cwd: pathlib.Path(cwd),
        project_ulid=lambda root: resolves_to,
    )


# ----- pure-fs merge_store_dir -----------------------------------------------


def test_merge_keeps_both_on_note_name_collision(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    _write_note(dst, "auth", "dst-auth\n")
    _write_note(src, "auth", "src-auth\n")

    merge_store_dir(src, dst, tag="9E9E")

    assert note_path(dst, "auth").read_text() == "dst-auth\n"  # winner untouched
    kept = (notes_dir(dst) / "auth--from-9E9E.md").read_text()
    assert kept == "src-auth\n"  # incoming preserved under a suffixed name


def test_merge_carries_every_lane_including_the_hidden_archives(tmp_path):
    """Everything under a scope dir is content someone wrote or uploaded, so
    both content lanes AND the two hidden archives travel — a merge that
    dropped ``.raw/`` would lose the originals a re-conversion needs."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    _write_note(src, "note", "note body\n")
    for rel, body in (
        ("docs/guide.md", "# Guide\n"),
        (".raw/guide.pdf", "%PDF-fake\n"),
        (".history/note.md", "older revision\n"),
    ):
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    assert merge_store_dir(src, dst, tag="X") == 4

    assert note_path(dst, "note").read_text() == "note body\n"
    assert (dst / "docs" / "guide.md").read_text() == "# Guide\n"
    assert (dst / ".raw" / "guide.pdf").read_text() == "%PDF-fake\n"
    assert (dst / ".history" / "note.md").read_text() == "older revision\n"


def test_merge_of_identical_content_is_a_noop(tmp_path):
    """A byte-identical collision is skipped, so re-running a merge never
    mints a second copy."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    _write_note(src, "same", "same body\n")
    _write_note(dst, "same", "same body\n")

    assert merge_store_dir(src, dst, tag="X") == 0
    assert sorted(p.name for p in notes_dir(dst).iterdir()) == ["same.md"]


def test_merge_absent_src_is_noop(tmp_path):
    assert merge_store_dir(tmp_path / "nope", tmp_path / "dst", tag="X") == 0


# ----- end-to-end StoreConsolidator.run() ------------------------------------


@pytest.mark.asyncio
async def test_consolidator_collapses_stale_worktree_store(mem):
    roots = ProjectRootRepo(mem.sm)
    labels = StoreLabelRepo(mem.sm)

    canonical_root = "/repo-main"
    stale_root = "/repo-main/.wt/feature"  # a worktree path of the same repo
    canonical_store = project_scope_name(project_ulid(canonical_root))
    stale_store = project_scope_name(project_ulid(stale_root))
    assert canonical_store != stale_store  # the pre-fix fragmentation

    # After the git_root fix, BOTH paths resolve to the main repo root.
    def fake_git_root(cwd: str):
        return pathlib.Path(canonical_root)

    cfg = KnowledgeConfig().model_dump(mode="json")
    canonical_dir = paths.scope_dir(canonical_store)
    stale_dir = paths.scope_dir(stale_store)

    # Canonical store: a pre-existing note that MUST survive untouched.
    _write_note(canonical_dir, "shared", "canon\n")
    await mem.resources.register(
        kind=KIND_KNOWLEDGE, name=canonical_store, config=cfg, actor="system"
    )
    await roots.set(canonical_store, canonical_root)

    # Stale worktree store: a colliding note + a fresh note and a user label —
    # none of which may be lost.
    _write_note(stale_dir, "shared", "wt-shared\n")
    _write_note(stale_dir, "wt-only", "wt-only\n")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=stale_store, config=cfg, actor="system")
    await roots.set(stale_store, stale_root)
    await labels.set(stale_store, "Feature WT")

    report = await StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=roots,
        labels=labels,
        scope_dir=paths.scope_dir,
        git_root=fake_git_root,
        project_ulid=project_ulid,
    ).run()

    # The stale store was merged and fully retired.
    assert report.merged_stores == [stale_store]
    with pytest.raises(ResourceNotFound):
        await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=stale_store))
    assert await roots.get(stale_store) is None
    assert await labels.get(stale_store) is None
    assert not stale_dir.exists()

    # Canonical store kept its own data and gained the stale store's.
    assert note_path(canonical_dir, "shared").read_text() == "canon\n"  # no clobber
    stale_tag = project_ulid(stale_root)[:5]
    suffixed = notes_dir(canonical_dir) / f"shared--from-{stale_tag}.md"
    assert suffixed.read_text() == "wt-shared\n"  # additive, both copies kept
    assert note_path(canonical_dir, "wt-only").read_text() == "wt-only\n"
    assert await labels.get(canonical_store) == "Feature WT"  # label moved (canon had none)
    assert await roots.get(canonical_store) == canonical_root


@pytest.mark.asyncio
async def test_consolidator_is_idempotent_and_leaves_canonical_alone(mem):
    roots = ProjectRootRepo(mem.sm)
    labels = StoreLabelRepo(mem.sm)
    canonical_root = "/solo-repo"
    canonical_store = project_scope_name(project_ulid(canonical_root))

    def fake_git_root(cwd: str):
        return pathlib.Path(canonical_root)

    cfg = KnowledgeConfig().model_dump(mode="json")
    canonical_dir = paths.scope_dir(canonical_store)
    _write_note(canonical_dir, "solo", "solo\n")
    await mem.resources.register(
        kind=KIND_KNOWLEDGE, name=canonical_store, config=cfg, actor="system"
    )
    await roots.set(canonical_store, canonical_root)

    consolidator = StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=roots,
        labels=labels,
        scope_dir=paths.scope_dir,
        git_root=fake_git_root,
        project_ulid=project_ulid,
    )
    first = await consolidator.run()
    second = await consolidator.run()

    assert first.merged_stores == [] and second.merged_stores == []
    assert await roots.get(canonical_store) == canonical_root
    assert note_path(canonical_dir, "solo").read_text() == "solo\n"


@pytest.mark.asyncio
async def test_consolidator_skips_unresolvable_root(mem):
    """A recorded root whose worktree is gone (git_root → None) is left intact,
    never silently dropped."""
    roots = ProjectRootRepo(mem.sm)
    labels = StoreLabelRepo(mem.sm)
    gone_root = "/deleted/worktree"
    store = project_scope_name(project_ulid(gone_root))
    await mem.resources.register(
        kind=KIND_KNOWLEDGE,
        name=store,
        config=KnowledgeConfig().model_dump(mode="json"),
        actor="system",
    )
    await roots.set(store, gone_root)

    report = await StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=roots,
        labels=labels,
        scope_dir=paths.scope_dir,
        git_root=lambda cwd: None,  # unresolvable
        project_ulid=project_ulid,
    ).run()

    assert report.unresolvable == [store]
    assert await roots.get(store) == gone_root  # untouched


# ----- alias bookkeeping: the no-resurrection trail --------------------------


async def test_boot_pass_does_not_reverse_a_merge(mem):
    """The merge-reversal scenario: the survivor's recorded root re-resolves to
    the merged-away identity. The boot pass must treat the alias holder as
    canonical — never re-provision the retired store, never retire the
    survivor, never drop the aliases."""
    roots = ProjectRootRepo(mem.sm)
    y_cfg = KnowledgeConfig(merged_identities=[_SRC_ULID]).model_dump(mode="json")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_DST, config=y_cfg, actor="system")
    dst_dir = paths.scope_dir(_DST)
    _write_note(dst_dir, "kept", "kept\n")
    await roots.set(_DST, "/checkout-that-minted-the-merged-id")

    # Every root re-resolves to the MERGED-AWAY identity.
    report = await _consolidator(mem, resolves_to=_SRC_ULID).run()

    assert report.merged_stores == [] and report.retired_empty == [] and report.failed == []
    dst_res = await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=_DST))
    assert dst_res.config["merged_identities"] == [_SRC_ULID]  # aliases intact
    with pytest.raises(ResourceNotFound):  # the retired identity stayed retired
        await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=_SRC))
    assert note_path(dst_dir, "kept").read_text() == "kept\n"


async def test_boot_adoption_records_the_retired_identity_as_alias(mem):
    """A boot/adoption merge leaves a no-resurrection trail: the stale store's
    identity AND its accumulated aliases land on the canonical store's
    ``merged_identities``."""
    roots = ProjectRootRepo(mem.sm)
    stale_cfg = KnowledgeConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_SRC, config=stale_cfg, actor="system")
    _write_note(paths.scope_dir(_SRC), "moved", "moved\n")
    await roots.set(_SRC, "/repo")

    report = await _consolidator(mem, resolves_to=_DST_ULID).run()

    assert report.merged_stores == [_SRC]
    dst_res = await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=_DST))
    assert dst_res.config["merged_identities"] == [_SRC_ULID, _OLD_ULID]
    assert note_path(paths.scope_dir(_DST), "moved").read_text() == "moved\n"


async def test_recording_aliases_strips_stale_claims_from_other_stores(mem):
    """Exactly one live holder per identity: an adoption that claims an alias
    removes the same id from every other store's ``merged_identities``, so the
    resolver redirect can never pick an arbitrary holder."""
    third = project_scope_name("D" * 26)
    cfg = KnowledgeConfig().model_dump(mode="json")
    src_cfg = KnowledgeConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    stale_claim = KnowledgeConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_SRC, config=src_cfg, actor="system")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_DST, config=cfg, actor="system")
    await mem.resources.register(
        kind=KIND_KNOWLEDGE, name=third, config=stale_claim, actor="system"
    )
    _write_note(paths.scope_dir(_SRC), "moved", "moved\n")

    await _consolidator(mem).adopt(_SRC, _DST, "/repo")

    dst_res = await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=_DST))
    assert dst_res.config["merged_identities"] == [_SRC_ULID, _OLD_ULID]
    third_res = await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=third))
    assert third_res.config["merged_identities"] == []  # stale claim stripped


async def test_adoption_keeps_the_canonical_stores_own_label(mem):
    """The label travels only into a canonical store that has none — an
    adoption never renames a store the user already named."""
    labels = StoreLabelRepo(mem.sm)
    cfg = KnowledgeConfig().model_dump(mode="json")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_SRC, config=cfg, actor="system")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_DST, config=cfg, actor="system")
    await labels.set(_SRC, "loser")
    await labels.set(_DST, "keeper")
    _write_note(paths.scope_dir(_SRC), "moved", "moved\n")

    await _consolidator(mem).adopt(_SRC, _DST, "/repo")

    assert await labels.get(_DST) == "keeper"
    assert await labels.get(_SRC) is None  # retired with the stale store


async def test_adoption_retry_after_midway_failure_does_not_duplicate_files(mem, monkeypatch):
    """An adoption that dies after copying files (reconcile boom) must be safely
    retryable: the content-idempotent file merge re-lands nothing, so the
    survivor ends with exactly ONE suffixed copy of the colliding note."""
    cfg = KnowledgeConfig().model_dump(mode="json")
    src_dir, dst_dir = paths.scope_dir(_SRC), paths.scope_dir(_DST)
    _write_note(src_dir, "auth", "src-auth\n")
    _write_note(dst_dir, "auth", "dst-auth\n")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_SRC, config=cfg, actor="system")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_DST, config=cfg, actor="system")

    consolidator = _consolidator(mem)
    real_reconcile = mem.reconciler.reconcile
    calls = {"n": 0}

    async def flaky_reconcile(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("reconcile boom")
        return await real_reconcile(**kw)

    monkeypatch.setattr(mem.reconciler, "reconcile", flaky_reconcile)
    with pytest.raises(RuntimeError):
        await consolidator.adopt(_SRC, _DST, "/repo")

    await consolidator.adopt(_SRC, _DST, "/repo")  # the natural retry

    names = sorted(p.name for p in notes_dir(dst_dir).glob("auth*"))
    assert names == [f"auth--from-{_SRC_ULID[:5]}.md", "auth.md"]  # ONE copy, not two
    assert calls["n"] == 2  # the retry really re-ran the reconcile
    with pytest.raises(ResourceNotFound):
        await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=_SRC))


async def test_find_alias_holder_is_deterministic_and_self_excluding(mem):
    lost = "E" * 26
    holder_a = project_scope_name("A" * 26)
    holder_d = project_scope_name("D" * 26)
    self_claim = project_scope_name(lost)  # a store may not alias its own id
    claim = KnowledgeConfig(merged_identities=[lost]).model_dump(mode="json")
    for name in (holder_d, self_claim, holder_a):
        await mem.resources.register(kind=KIND_KNOWLEDGE, name=name, config=claim, actor="system")

    assert await find_alias_holder(mem.resources, lost) == holder_a  # name order
    assert await find_alias_holder(mem.resources, "F" * 26) is None


# ----- ScopeResolver alias redirect ------------------------------------------


async def test_merged_identity_resolves_to_survivor(mem, tmp_path):
    # The survivor Y holds X in merged_identities (as a real adoption records it).
    y_cfg = KnowledgeConfig(merged_identities=[_SRC_ULID]).model_dump(mode="json")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_DST, config=y_cfg, actor="system")

    async def merged_alias_target(project_id: str) -> str | None:
        # The SAME lookup the knowledge wiring injects — not a re-implementation.
        return await find_alias_holder(mem.resources, project_id)

    resolver = ScopeResolver(
        resources=mem.resources,
        git_root=lambda cwd: pathlib.Path(cwd),
        project_ulid=lambda root: _SRC_ULID,  # this checkout minted the MERGED id
        scope_dir=paths.scope_dir,
        merged_alias_target=merged_alias_target,
    )
    resolved = await resolver.resolve(scope=KnowledgeScope.PROJECT, cwd=str(tmp_path))

    assert resolved.project_id == _DST_ULID  # landed on the survivor
    assert resolved.store_dir == paths.scope_dir(_DST)
    with pytest.raises(ResourceNotFound):  # no empty duplicate re-provisioned
        await mem.resources.get(ResourceRef(kind=KIND_KNOWLEDGE, name=_SRC))


async def test_live_identity_is_never_redirected(mem, tmp_path):
    """The redirect fires only on a MISS: when the computed identity's store
    exists it wins, even if some config lists it as merged (stale alias)."""
    cfg_src = KnowledgeConfig().model_dump(mode="json")
    cfg_dst = KnowledgeConfig(merged_identities=[_SRC_ULID]).model_dump(mode="json")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_SRC, config=cfg_src, actor="system")
    await mem.resources.register(kind=KIND_KNOWLEDGE, name=_DST, config=cfg_dst, actor="system")

    async def merged_alias_target(project_id: str) -> str | None:
        return _DST

    resolver = ScopeResolver(
        resources=mem.resources,
        git_root=lambda cwd: pathlib.Path(cwd),
        project_ulid=lambda root: _SRC_ULID,
        scope_dir=paths.scope_dir,
        merged_alias_target=merged_alias_target,
    )
    resolved = await resolver.resolve(scope=KnowledgeScope.PROJECT, cwd=str(tmp_path))
    assert resolved.project_id == _SRC_ULID
