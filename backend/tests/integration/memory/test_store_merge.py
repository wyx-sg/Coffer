"""Integration: AI-assisted store merge (FR-056-059) — the real machinery.

Three layers over real SQLite + real lane files:

- ``StoreConsolidator.merge`` — additive file merge, label/root carry-over,
  FR-058 aliases (incl. transitive), reconcile, retire.
- ``ScopeResolver`` alias redirect — a merged-away identity resolves to the
  surviving store instead of re-provisioning an empty duplicate.
- The HTTP routes over the full app — merge + validation + audit + the
  no-model scan degradation through the real wiring.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from coffer.application.memory.consolidate import StoreConsolidator, find_alias_holder
from coffer.application.memory.scope import MemoryScope, ScopeResolver, project_store_name
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.config import MemoryStoreConfig
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.paths import journal_path, topic_path
from coffer.infrastructure.memory.journal_files import append_entry, read_entries
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.store_label_repo import StoreLabelRepo
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_SRC_ULID = "B" * 26
_DST_ULID = "A" * 26
_OLD_ULID = "C" * 26  # already merged into SRC before the test (transitivity)
_SRC = project_store_name(_SRC_ULID)
_DST = project_store_name(_DST_ULID)


def _ts(day: int, hour: int) -> datetime:
    return datetime(2026, 7, day, hour, tzinfo=UTC)


def _consolidator(mem, *, resolves_to: str = _DST_ULID) -> StoreConsolidator:
    return StoreConsolidator(
        resources=mem.resources,
        reconciler=mem.reconciler,
        roots=ProjectRootRepo(mem.sm),
        labels=StoreLabelRepo(mem.sm),
        store_dir=paths.memory_store_dir,
        git_root=lambda cwd: pathlib.Path(cwd),
        project_ulid=lambda root: resolves_to,
    )


# ----- StoreConsolidator.merge (FR-057/FR-058) -------------------------------


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="merging two stores consolidates additively and retires the source",
)
async def test_merge_consolidates_additively_and_retires_source(mem):
    roots, labels = ProjectRootRepo(mem.sm), StoreLabelRepo(mem.sm)
    src_dir = paths.memory_store_dir(_SRC_ULID)
    dst_dir = paths.memory_store_dir(_DST_ULID)

    # Target: its own journal day + an 'auth' topic that must stay untouched.
    append_entry(journal_path(dst_dir, "2026-07-01"), timestamp=_ts(1, 8), body="dst-day1")
    topic_path(dst_dir, "auth").parent.mkdir(parents=True, exist_ok=True)
    topic_path(dst_dir, "auth").write_text("dst-auth\n", encoding="utf-8")
    await mem.resources.register(
        kind="memory",
        name=_DST,
        config=MemoryStoreConfig().model_dump(mode="json"),
        actor="system",
    )

    # Source: overlapping journal period + colliding topic filename + a label,
    # a root, and a pre-existing alias (a store merged into IT earlier).
    append_entry(journal_path(src_dir, "2026-07-01"), timestamp=_ts(1, 15), body="src-day1")
    append_entry(journal_path(src_dir, "2026-07-06"), timestamp=_ts(6, 9), body="src-day6")
    topic_path(src_dir, "auth").parent.mkdir(parents=True, exist_ok=True)
    topic_path(src_dir, "auth").write_text("src-auth\n", encoding="utf-8")
    src_cfg = MemoryStoreConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_SRC, config=src_cfg, actor="system")
    await roots.set(_SRC, "/old-machine/repo")
    await labels.set(_SRC, "Old Machine Repo")

    outcome = await _consolidator(mem).merge(_SRC, _DST, actor="user")

    # Additive: both journal days landed, the colliding topic kept BOTH copies.
    day1 = {e.body for e in read_entries(journal_path(dst_dir, "2026-07-01"))}
    assert day1 == {"dst-day1", "src-day1"}
    day6 = [e.body for e in read_entries(journal_path(dst_dir, "2026-07-06"))]
    assert day6 == ["src-day6"]
    assert topic_path(dst_dir, "auth").read_text() == "dst-auth\n"
    suffixed = dst_dir / "knowledge" / f"auth--from-{_SRC_ULID[:5]}.md"
    assert suffixed.read_text() == "src-auth\n"
    assert outcome.merged_files == 3  # day1 merged + day6 created + auth suffixed

    # Label + root moved (target had neither).
    assert outcome.label_moved and outcome.root_moved
    assert await labels.get(_DST) == "Old Machine Repo"
    assert await roots.get(_DST) == "/old-machine/repo"

    # FR-058: the source's ULID AND its own alias carried over transitively.
    assert outcome.aliases == [_SRC_ULID, _OLD_ULID]
    dst_res = await mem.resources.get(ResourceRef(kind="memory", name=_DST))
    assert dst_res.config["merged_identities"] == [_SRC_ULID, _OLD_ULID]

    # Source fully retired: resource, binding rows, on-disk dir.
    with pytest.raises(ResourceNotFound):
        await mem.resources.get(ResourceRef(kind="memory", name=_SRC))
    assert await roots.get(_SRC) is None
    assert await labels.get(_SRC) is None
    assert not src_dir.exists()

    # Reconcile made the merged journal recall-able.
    doc = await mem.documents.get_document("memory", _DST, "journal-2026-07-06")
    assert doc is not None


async def test_merge_keeps_targets_own_label_and_root(mem):
    roots, labels = ProjectRootRepo(mem.sm), StoreLabelRepo(mem.sm)
    cfg = MemoryStoreConfig().model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_SRC, config=cfg, actor="system")
    await mem.resources.register(kind="memory", name=_DST, config=cfg, actor="system")
    await labels.set(_SRC, "loser")
    await labels.set(_DST, "keeper")
    await roots.set(_SRC, "/src")
    await roots.set(_DST, "/dst")

    outcome = await _consolidator(mem).merge(_SRC, _DST)

    assert not outcome.label_moved and not outcome.root_moved
    assert await labels.get(_DST) == "keeper"
    assert await roots.get(_DST) == "/dst"


async def test_merge_missing_store_raises_resource_not_found(mem):
    cfg = MemoryStoreConfig().model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_DST, config=cfg, actor="system")
    with pytest.raises(ResourceNotFound):
        await _consolidator(mem).merge(_SRC, _DST)


# ----- ScopeResolver alias redirect (FR-058) ---------------------------------


@pytest.mark.acceptance(
    spec="007-memory", scenario="a merged identity resolves to the surviving store"
)
async def test_merged_identity_resolves_to_survivor(mem, tmp_path):
    # The survivor Y holds X in merged_identities (as a real merge records it).
    y_cfg = MemoryStoreConfig(merged_identities=[_SRC_ULID]).model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_DST, config=y_cfg, actor="system")

    async def merged_alias_target(project_id: str) -> str | None:
        # The SAME lookup wire_memory_kind injects — not a test re-implementation.
        return await find_alias_holder(mem.resources, project_id)

    resolver = ScopeResolver(
        resources=mem.resources,
        git_root=lambda cwd: pathlib.Path(cwd),
        project_ulid=lambda root: _SRC_ULID,  # this checkout minted the MERGED id
        store_dir=paths.memory_store_dir,
        merged_alias_target=merged_alias_target,
    )
    resolved = await resolver.resolve(scope=MemoryScope.PROJECT, cwd=str(tmp_path))

    assert resolved.project_id == _DST_ULID  # landed on the survivor
    assert resolved.store_dir == paths.memory_store_dir(_DST_ULID)
    with pytest.raises(ResourceNotFound):  # no empty duplicate re-provisioned
        await mem.resources.get(ResourceRef(kind="memory", name=_SRC))


async def test_live_identity_is_never_redirected(mem, tmp_path):
    """The redirect fires only on a MISS: when the computed identity's store
    exists it wins, even if some config lists it as merged (stale alias)."""
    cfg_src = MemoryStoreConfig().model_dump(mode="json")
    cfg_dst = MemoryStoreConfig(merged_identities=[_SRC_ULID]).model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_SRC, config=cfg_src, actor="system")
    await mem.resources.register(kind="memory", name=_DST, config=cfg_dst, actor="system")

    async def merged_alias_target(project_id: str) -> str | None:
        return _DST

    resolver = ScopeResolver(
        resources=mem.resources,
        git_root=lambda cwd: pathlib.Path(cwd),
        project_ulid=lambda root: _SRC_ULID,
        store_dir=paths.memory_store_dir,
        merged_alias_target=merged_alias_target,
    )
    resolved = await resolver.resolve(scope=MemoryScope.PROJECT, cwd=str(tmp_path))
    assert resolved.project_id == _SRC_ULID


# ----- review regressions: retry idempotency, boot-pass reversal, aliases -----


async def test_merge_retry_after_midway_failure_does_not_duplicate_files(mem, monkeypatch):
    """A merge that dies after copying files (reconcile boom) must be safely
    retryable: the content-idempotent file merge re-lands nothing, so the
    survivor ends with exactly ONE suffixed copy of the colliding topic."""
    cfg = MemoryStoreConfig().model_dump(mode="json")
    src_dir, dst_dir = paths.memory_store_dir(_SRC_ULID), paths.memory_store_dir(_DST_ULID)
    for d, body in ((src_dir, "src-auth\n"), (dst_dir, "dst-auth\n")):
        topic_path(d, "auth").parent.mkdir(parents=True, exist_ok=True)
        topic_path(d, "auth").write_text(body, encoding="utf-8")
    await mem.resources.register(kind="memory", name=_SRC, config=cfg, actor="system")
    await mem.resources.register(kind="memory", name=_DST, config=cfg, actor="system")

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
        await consolidator.merge(_SRC, _DST)

    outcome = await consolidator.merge(_SRC, _DST)  # the natural retry

    names = sorted(p.name for p in (dst_dir / "knowledge").glob("auth*"))
    assert names == [f"auth--from-{_SRC_ULID[:5]}.md", "auth.md"]  # ONE copy, not two
    assert outcome.merged_files == 0  # everything already landed on attempt #1
    with pytest.raises(ResourceNotFound):
        await mem.resources.get(ResourceRef(kind="memory", name=_SRC))


async def test_boot_pass_does_not_reverse_a_merge(mem):
    """The reviewer's merge-reversal scenario: the survivor's recorded root
    re-resolves to the merged-away identity. The boot pass must treat the
    alias holder as canonical — never re-provision the retired store, never
    retire the survivor, never drop the aliases."""
    roots = ProjectRootRepo(mem.sm)
    y_cfg = MemoryStoreConfig(merged_identities=[_SRC_ULID]).model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_DST, config=y_cfg, actor="system")
    dst_dir = paths.memory_store_dir(_DST_ULID)
    append_entry(journal_path(dst_dir, "2026-07-01"), timestamp=_ts(1, 8), body="kept")
    await roots.set(_DST, "/checkout-that-minted-the-merged-id")

    # Every root re-resolves to the MERGED-AWAY identity.
    report = await _consolidator(mem, resolves_to=_SRC_ULID).run()

    assert report.merged_stores == [] and report.retired_empty == [] and report.failed == []
    dst_res = await mem.resources.get(ResourceRef(kind="memory", name=_DST))
    assert dst_res.config["merged_identities"] == [_SRC_ULID]  # aliases intact
    with pytest.raises(ResourceNotFound):  # the retired identity stayed retired
        await mem.resources.get(ResourceRef(kind="memory", name=_SRC))
    assert {e.body for e in read_entries(journal_path(dst_dir, "2026-07-01"))} == {"kept"}


async def test_boot_adoption_records_the_retired_identity_as_alias(mem):
    """A boot/adoption merge leaves the same no-resurrection trail as an
    explicit merge: the stale store's identity AND its accumulated aliases
    land on the canonical store's merged_identities."""
    roots = ProjectRootRepo(mem.sm)
    stale_cfg = MemoryStoreConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_SRC, config=stale_cfg, actor="system")
    src_dir = paths.memory_store_dir(_SRC_ULID)
    append_entry(journal_path(src_dir, "2026-07-02"), timestamp=_ts(2, 9), body="moved")
    await roots.set(_SRC, "/repo")

    report = await _consolidator(mem, resolves_to=_DST_ULID).run()

    assert report.merged_stores == [_SRC]
    dst_res = await mem.resources.get(ResourceRef(kind="memory", name=_DST))
    assert dst_res.config["merged_identities"] == [_SRC_ULID, _OLD_ULID]


async def test_recording_aliases_strips_stale_claims_from_other_stores(mem):
    """Exactly one live holder per identity: a merge that claims an alias
    removes the same id from every other store's merged_identities, so the
    resolver redirect can never pick an arbitrary holder."""
    third = project_store_name("D" * 26)
    cfg = MemoryStoreConfig().model_dump(mode="json")
    src_cfg = MemoryStoreConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    stale_claim = MemoryStoreConfig(merged_identities=[_OLD_ULID]).model_dump(mode="json")
    await mem.resources.register(kind="memory", name=_SRC, config=src_cfg, actor="system")
    await mem.resources.register(kind="memory", name=_DST, config=cfg, actor="system")
    await mem.resources.register(kind="memory", name=third, config=stale_claim, actor="system")

    outcome = await _consolidator(mem).merge(_SRC, _DST)

    assert outcome.aliases == [_SRC_ULID, _OLD_ULID]
    third_res = await mem.resources.get(ResourceRef(kind="memory", name=third))
    assert third_res.config["merged_identities"] == []  # stale claim stripped


async def test_find_alias_holder_is_deterministic_and_self_excluding(mem):
    lost = "E" * 26
    holder_a = project_store_name("A" * 26)
    holder_d = project_store_name("D" * 26)
    self_claim = project_store_name(lost)  # a store may not alias its own id
    claim = MemoryStoreConfig(merged_identities=[lost]).model_dump(mode="json")
    for name in (holder_d, self_claim, holder_a):
        await mem.resources.register(kind="memory", name=name, config=claim, actor="system")

    assert await find_alias_holder(mem.resources, lost) == holder_a  # name order
    assert await find_alias_holder(mem.resources, "F" * 26) is None


# ----- HTTP routes over the full app ------------------------------------------


_TOKEN = "merge-route-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _add_fact(c: TestClient, store: str, text: str) -> None:
    r = c.post(
        f"/api/v1/memory_stores/{store}/facts",
        json={"title": text, "text": text},
        headers=_HEADERS,
    )
    assert r.status_code == 201, r.text


def test_merge_route_merges_and_reports_no_model_organize(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59930)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _add_fact(c, _SRC, "src fact one")
        _add_fact(c, _SRC, "src fact two")
        _add_fact(c, _DST, "dst fact")
        r = c.patch(
            f"/api/v1/memory_stores/{_SRC}/label", json={"label": "老机器"}, headers=_HEADERS
        )
        assert r.status_code == 200, r.text

        r = c.post(
            "/api/v1/memory_stores/merge",
            json={"source": _SRC, "target": _DST},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["target"] == _DST
        assert body["merged_files"] >= 2  # the two source fact files moved
        assert body["label_moved"] is True
        assert body["aliases"] == [_SRC_ULID]
        # organize=true by default, but the test app has no internal engine —
        # FR-059: the merge still succeeds and reports the degradation.
        assert body["reorg_status"] == "no_model"

        # The source is gone from the list; the target absorbed its facts.
        r = c.get("/api/v1/memory_stores", headers=_HEADERS)
        names = {s["name"]: s for s in r.json()["memory_stores"]}
        assert _SRC not in names
        assert names[_DST]["fact_count"] == 3
        assert names[_DST]["label"] == "老机器"
        assert c.get(f"/api/v1/memory_stores/{_SRC}", headers=_HEADERS).status_code == 404

        # One memory_stores_merged audit entry (names + counts only).
        r = c.get("/api/v1/audit", headers=_HEADERS)
        assert r.status_code == 200, r.text
        merged = [e for e in r.json()["entries"] if e["event_type"] == "memory_stores_merged"]
        assert len(merged) == 1


def test_merge_route_validates_pairs_with_no_side_effects(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59940)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _add_fact(c, _SRC, "src fact")

        for payload, expected in [
            ({"source": "global", "target": _DST}, 400),
            ({"source": _SRC, "target": _SRC}, 400),
            ({"source": "not-a-store", "target": _DST}, 400),
            ({"source": _SRC, "target": _DST}, 404),  # target never provisioned
        ]:
            r = c.post("/api/v1/memory_stores/merge", json=payload, headers=_HEADERS)
            assert r.status_code == expected, (payload, r.text)

        # The failed merges left the source untouched.
        r = c.get(f"/api/v1/memory_stores/{_SRC}", headers=_HEADERS)
        assert r.status_code == 200 and r.json()["fact_count"] == 1


def test_merge_scan_route_degrades_to_no_model_on_the_real_wiring(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59950)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        _add_fact(c, _SRC, "src fact")
        r = c.post("/api/v1/memory_stores/merge_scan", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"engine": "no_model", "truncated": False, "proposals": []}
