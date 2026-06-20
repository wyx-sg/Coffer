"""Integration: the memory application service over the real substrate."""

from __future__ import annotations

import pytest

from coffer.application.memory.scope import GLOBAL_STORE_NAME, project_store_name
from coffer.domain.errors import MemoryRejected, ScopeUnresolved
from coffer.domain.knowledge.document import WORKSPACE_GLOBAL_PROJECT_ID
from coffer.domain.memory.scope import MemoryScope
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.memory.scope_fs import project_ulid

pytestmark = pytest.mark.asyncio


def _project_store(mem) -> str:
    from pathlib import Path

    return project_store_name(project_ulid(str(Path(mem.project_cwd).parent)))


@pytest.mark.acceptance(spec="007-memory", scenario="agent remembers a project fact")
async def test_remember_project_fact_writes_file_and_index(mem) -> None:
    fact = await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="deploy-via-make",
        description="deploys via make release",
        body="This repo deploys via make release, never git push --tags.",
        actor="agent",
        type="project",
    )
    store = _project_store(mem)
    # The per-item file exists under the knowledge/ lane's inbox with frontmatter.
    store_dir = paths.memory_store_dir(project_ulid_from(mem))
    inbox_files = list(paths.inbox_dir(store_dir).glob("*.md"))
    assert len(inbox_files) == 1
    text = inbox_files[0].read_text()
    assert "name: deploy-via-make" in text
    assert "actor: agent" in text
    # No derived MEMORY.md index is generated.
    assert not (store_dir / "MEMORY.md").exists()
    # Indexed into documents (kind=memory).
    assert await mem.documents.count_documents("memory", store) == 1
    assert fact.id


@pytest.mark.acceptance(spec="007-memory", scenario="agent recalls a project fact")
async def test_recall_returns_facts(mem) -> None:
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="api-base",
        description="api base path",
        body="The service API base path is /api/v2 for this repo.",
        actor="agent",
    )
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="api base path", top_k=5)
    assert len(hits) >= 1
    assert any("/api/v2" in h.text for h in hits)
    assert hits[0].id
    assert hits[0].source


@pytest.mark.acceptance(spec="007-memory", scenario="remember at global scope")
async def test_remember_global_scope(mem) -> None:
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="tabs",
        description="prefers tabs",
        body="The user prefers tabs over spaces.",
        actor="user",
    )
    assert await mem.documents.count_documents("memory", GLOBAL_STORE_NAME) == 1
    # Recall from a project still sees the global fact.
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="tabs over spaces", top_k=5)
    assert any("tabs" in h.text for h in hits)


@pytest.mark.acceptance(spec="007-memory", scenario="recall spans project and global scope")
async def test_recall_spans_project_and_global(mem) -> None:
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="g",
        description="global pref",
        body="global preference uses spaces indentation",
        actor="user",
    )
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="p",
        description="project fact",
        body="project fact uses spaces in config files",
        actor="agent",
    )
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="spaces", top_k=10)
    sources = {h.source.split(":")[0] for h in hits}
    assert "global" in sources
    assert "project" in sources


@pytest.mark.acceptance(
    spec="007-memory", scenario="project scope resolves from the agent's working directory"
)
async def test_project_scope_resolution_provisions_store(mem) -> None:
    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    assert resolved.scope is MemoryScope.PROJECT
    assert resolved.project_id != WORKSPACE_GLOBAL_PROJECT_ID
    # The backing Resource was auto-provisioned.
    listed = [r.name for r in await mem.resources.list(kind="memory")]
    assert project_store_name(resolved.project_id) in listed


async def test_project_scope_unresolved_outside_git(mem) -> None:
    with pytest.raises(ScopeUnresolved):
        await mem.service.add_fact(
            scope=MemoryScope.PROJECT,
            cwd="/tmp/not-a-repo",
            name="x",
            description="x",
            body="x",
            actor="agent",
        )


# Service-level update (the REST/CLI write surface); the MCP update_memory tool
# was removed in the knowledge-lane redesign.
async def test_update_fact_reflects_in_recall(mem) -> None:
    fact = await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="f",
        description="d",
        body="original aardvark text",
        actor="agent",
    )
    store = _project_store(mem)
    updated = await mem.service.update_fact(
        store_name=store, fact_id=fact.id, new_body="replaced zebra text", actor="user"
    )
    assert updated.body == "replaced zebra text"
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="zebra", top_k=5)
    assert any("zebra" in h.text for h in hits)
    assert (await mem.service.recall(cwd=mem.project_cwd, query="aardvark", top_k=5))[0] == []


# Service-level delete (the REST/CLI write surface); the MCP forget tool was
# removed in the knowledge-lane redesign.
async def test_forget_removes_fact(mem) -> None:
    fact = await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="f",
        description="d",
        body="ephemeral walrus fact",
        actor="agent",
    )
    store = _project_store(mem)
    await mem.service.delete_fact(store_name=store, fact_id=fact.id, actor="user")
    assert await mem.documents.count_documents("memory", store) == 0
    assert (await mem.service.recall(cwd=mem.project_cwd, query="walrus", top_k=5))[0] == []
    store_dir = paths.memory_store_dir(project_ulid_from(mem))
    assert list(paths.inbox_dir(store_dir).glob("*.md")) == []


@pytest.mark.acceptance(spec="007-memory", scenario="user adds a fact")
async def test_user_add_sets_actor_user(mem) -> None:
    fact = await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="pref",
        description="a preference",
        body="user likes dark mode",
        actor="user",
    )
    got = await mem.service.get_fact(store_name=GLOBAL_STORE_NAME, fact_id=fact.id)
    assert got.actor == "user"


@pytest.mark.acceptance(spec="007-memory", scenario="user corrects a fact out-of-band")
async def test_user_corrects_fact_via_write_api(mem) -> None:
    """The programmatic write path (REST/CLI) — the in-app viewer is read-only.

    The external-edit-on-disk + lazy-reindex half of this scenario is covered
    by ``test_lazy_reindex_picks_up_out_of_band_edit`` below.
    """
    fact = await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="pref",
        description="d",
        body="light mode preferred",
        actor="user",
    )
    await mem.service.update_fact(
        store_name=GLOBAL_STORE_NAME, fact_id=fact.id, new_body="dark mode preferred", actor="user"
    )
    got = await mem.service.get_fact(store_name=GLOBAL_STORE_NAME, fact_id=fact.id)
    assert got.body == "dark mode preferred"


@pytest.mark.acceptance(spec="007-memory", scenario="user deletes a fact")
async def test_user_delete_fact(mem) -> None:
    fact = await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="x",
        description="d",
        body="to be deleted",
        actor="user",
    )
    await mem.service.delete_fact(store_name=GLOBAL_STORE_NAME, fact_id=fact.id, actor="user")
    facts, total = await mem.service.list_facts(store_name=GLOBAL_STORE_NAME)
    assert total == 0
    assert facts == []


@pytest.mark.acceptance(spec="007-memory", scenario="clear a memory scope")
async def test_clear_scope_keeps_resource(mem) -> None:
    for i in range(3):
        await mem.service.add_fact(
            scope=MemoryScope.GLOBAL,
            cwd=None,
            name=f"f{i}",
            description="d",
            body=f"fact number {i}",
            actor="user",
        )
    cleared = await mem.service.clear(store_name=GLOBAL_STORE_NAME, actor="user")
    assert cleared == 3
    _, total = await mem.service.list_facts(store_name=GLOBAL_STORE_NAME)
    assert total == 0
    # Store Resource still exists.
    assert GLOBAL_STORE_NAME in [r.name for r in await mem.resources.list(kind="memory")]
    # The knowledge lane is emptied; no derived MEMORY.md index exists.
    assert list(paths.inbox_dir(paths.memory_global_dir()).glob("*.md")) == []
    assert not (paths.memory_global_dir() / "MEMORY.md").exists()


async def test_metrics(mem) -> None:
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="x",
        description="d",
        body="some content",
        actor="user",
    )
    m = await mem.service.metrics(store_name=GLOBAL_STORE_NAME)
    assert m["fact_count"] == 1
    assert m["disk_bytes"] > 0


async def test_fact_count_uses_indexed_count_without_disk_scan(mem) -> None:
    """KB14: ``fact_count`` hits only the indexed DB count — no ``scan_store_dir``
    file parse and no ``du_bytes`` disk walk (the list path discards disk_bytes).
    Patching both on the queries module to raise proves neither runs on the cheap
    count path, while ``metrics()`` (the detail endpoint) still scans + reports
    disk_bytes."""
    from coffer.application.memory import queries as mem_queries_mod

    for name in ("x", "y"):
        await mem.service.add_fact(
            scope=MemoryScope.GLOBAL,
            cwd=None,
            name=name,
            description="d",
            body=f"some {name} content",
            actor="user",
        )

    def _boom_du(_path):
        raise AssertionError("du_bytes must not run on the fact_count path")

    def _boom_scan(_path):
        raise AssertionError("scan_store_dir must not run on the fact_count path")

    # A local context so undo() does NOT revert the ``mem`` fixture's env-var
    # patches (they share the per-test monkeypatch object otherwise).
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mem_queries_mod, "du_bytes", _boom_du)
        mp.setattr(mem_queries_mod, "scan_store_dir", _boom_scan)
        assert await mem.service.fact_count(store_name=GLOBAL_STORE_NAME) == 2

    # The detail endpoint still scans + walks the disk → confirm both survive.
    m = await mem.service.metrics(store_name=GLOBAL_STORE_NAME)
    assert m["fact_count"] == 2
    assert m["disk_bytes"] > 0


@pytest.mark.acceptance(
    spec="007-memory", scenario="vector recall falls back when embedding is unconfigured"
)
async def test_vector_recall_falls_back_when_unconfigured(mem) -> None:
    """A store with no embedding provider, queried with mode=vector, returns
    keyword results — never an error."""
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="x",
        description="d",
        body="the okapi fact about embeddings",
        actor="user",
    )
    # No embedding configured on the default store → vector degrades to keyword.
    hits, _fb = await mem.service.recall(
        cwd=None, query="okapi", scope=MemoryScope.GLOBAL, top_k=5, mode="vector"
    )
    assert any("okapi" in h.text for h in hits)


async def test_fact_too_long_rejected(mem) -> None:
    with pytest.raises(MemoryRejected) as exc:
        await mem.service.add_fact(
            scope=MemoryScope.GLOBAL,
            cwd=None,
            name="x",
            description="d",
            body="x" * 10_000,  # default max_fact_chars is 8192
            actor="user",
        )
    assert exc.value.reason == "too_long"


@pytest.mark.acceptance(
    spec="007-memory", scenario="out-of-band fact-file edits are visible on recall"
)
async def test_lazy_reindex_picks_up_out_of_band_edit(mem) -> None:
    """An out-of-band edit to a fact file (the user editing it directly on disk,
    or another process) is reflected on the next recall, no watcher running."""
    fact = await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="f",
        description="d",
        body="original narwhal content",
        actor="agent",
    )
    store_dir = paths.memory_store_dir(project_ulid_from(mem))
    fact_file = next(iter(paths.inbox_dir(store_dir).glob("*.md")))
    # Edit the body directly on disk (frontmatter preserved).
    text = fact_file.read_text()
    fact_file.write_text(text.replace("original narwhal content", "edited platypus content"))
    hits, _fb = await mem.service.recall(cwd=mem.project_cwd, query="platypus", top_k=5)
    assert any("platypus" in h.text for h in hits)
    assert (await mem.service.recall(cwd=mem.project_cwd, query="narwhal", top_k=5))[0] == []
    assert fact.id  # the same fact id, re-indexed in place


async def test_grep_recall_ignores_legacy_root_facts(mem) -> None:
    """A pre-lane fact abandoned at the store ROOT (not under knowledge/) must NOT
    surface via recall in any mode — grep runs over the whole store dir, so the
    knowledge/-lane filter must exclude it, staying consistent with keyword/vector
    (whose reconciler indexes only the lane)."""
    await mem.service.add_fact(
        scope=MemoryScope.PROJECT,
        cwd=mem.project_cwd,
        name="real",
        description="d",
        body="a real lane fact about otters",
        actor="agent",
    )
    store_dir = paths.memory_store_dir(project_ulid_from(mem))
    # Plant a legacy fact at the store root (pre-lane layout), abandoned in place.
    (store_dir / "legacy-zebra.md").write_text(
        "---\nid: legacy-zebra\nname: legacy\ndescription: d\n"
        "metadata:\n  actor: agent\n---\nthe secret zebra lives at the store root\n",
        encoding="utf-8",
    )
    for mode in ("grep", "keyword", "vector"):
        hits, _fb = await mem.service.recall(
            cwd=mem.project_cwd, query="zebra", mode=mode, top_k=20
        )
        assert all("zebra" not in h.text for h in hits), f"legacy root fact leaked via {mode}"


def project_ulid_from(mem) -> str:
    from pathlib import Path

    return project_ulid(str(Path(mem.project_cwd).parent))


@pytest.mark.acceptance(
    spec="007-memory",
    scenario="vector recall falls back when embedding is unconfigured",
)
async def test_enabling_vector_backfills_existing_facts(mem) -> None:
    """Enabling vector on a store with existing facts must re-embed them: the
    sha no-op gate must not leave the new vec table empty forever (review H2)."""
    from coffer.domain.resource import ResourceRef

    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="merge-style",
        description="merge convention",
        body="We always use squash-merge for feature branches.",
        actor="user",
    )

    await mem.resources.update_config(
        ResourceRef("memory", GLOBAL_STORE_NAME),
        new_config={
            "retrieval_modes": ["grep", "keyword", "vector"],
            "default_mode": "keyword",
            "embedding_provider": "local",
            "embedding_model": "fake-model",
            "embedding_dimensions": 32,
        },
        actor="user",
    )

    hits, mode, fallback = await mem.service.recall_in_store(
        store_name=GLOBAL_STORE_NAME,
        query="squash-merge feature branches",
        mode="vector",
        top_k=5,
    )
    assert mode == "vector"
    assert fallback is False
    assert any("squash-merge" in h.text for h in hits)


async def test_degraded_fact_is_retried_on_next_reconcile(mem) -> None:
    """KB8: a fact whose embed degraded (provider down) MUST be retried on the
    next reconcile — the no-op pre-gate no longer skips a still-pending fact just
    because its content sha matches. The persisted ``embed_pending`` flag is what
    makes the retry happen even though the body is unchanged."""
    from coffer.domain.errors import EngineUnavailable
    from coffer.domain.resource import ResourceRef

    # Provision the global store (the first write auto-registers it), then enable
    # vector so a later write attempts an embed.
    await mem.service.add_fact_to_store(
        store_name=GLOBAL_STORE_NAME, name="seed", description="", body="seed fact", actor="user"
    )
    await mem.resources.update_config(
        ResourceRef("memory", GLOBAL_STORE_NAME),
        new_config={
            "retrieval_modes": ["grep", "keyword", "vector"],
            "default_mode": "keyword",
            "embedding_provider": "local",
            "embedding_model": "fake-model",
            "embedding_dimensions": 32,
        },
        actor="user",
    )

    # Force the embedder to fail for the write that indexes the new fact.
    reindexer = mem.service._reconciler._reindexer  # type: ignore[attr-defined]
    real_factory = reindexer._embedder_factory  # type: ignore[attr-defined]

    def _failing(config):
        class _Down:
            @property
            def dimensions(self):
                return config.dimensions

            async def embed(self, texts):
                raise EngineUnavailable("embedding", "provider down (test)")

        return _Down()

    reindexer._embedder_factory = _failing  # type: ignore[attr-defined]
    wombat = await mem.service.add_fact_to_store(
        store_name=GLOBAL_STORE_NAME,
        name="wombat",
        description="d",
        body="the wombat fact about embeddings",
        actor="user",
    )
    # The wombat fact is indexed keyword-only and persisted as embed_pending.
    pending = await mem.documents.get_document("memory", GLOBAL_STORE_NAME, wombat.id)
    assert pending is not None
    assert pending.embed_pending is True
    assert pending.content_sha256 != ""  # real sha, decoupled from the retry state

    # Restore the provider and reconcile (recall reconciles on read). The fact's
    # body is unchanged, but because it is still pending the retry runs.
    reindexer._embedder_factory = real_factory  # type: ignore[attr-defined]
    hits, mode, fallback = await mem.service.recall_in_store(
        store_name=GLOBAL_STORE_NAME,
        query="wombat embeddings",
        mode="vector",
        top_k=5,
    )
    assert mode == "vector"
    assert fallback is False  # the embed was retried → vector recall works
    assert any("wombat" in h.text for h in hits)

    cleared = await mem.documents.get_document("memory", GLOBAL_STORE_NAME, wombat.id)
    assert cleared is not None
    assert cleared.embed_pending is False


async def test_recall_hit_time_and_source_carry_fact_metadata(mem) -> None:
    """MemoryHit.time must be the fact's updated_at (not now()) and source must
    carry the fact file's path, per the data-model (review misalignment #3)."""
    await mem.service.add_fact(
        scope=MemoryScope.GLOBAL,
        cwd=None,
        name="platypus",
        description="d",
        body="the platypus memo body",
        actor="user",
    )
    hits, fallback = await mem.service.recall(cwd=None, query="platypus", top_k=5)
    assert fallback is False
    h = hits[0]
    doc = await mem.documents.get_document("memory", GLOBAL_STORE_NAME, h.id)
    assert doc is not None
    assert doc.path.endswith(".md")
    assert h.source == f"global:{doc.path}"
    assert h.time == doc.updated_at


async def test_grep_recall_budget_not_consumed_by_one_facts_lines(mem) -> None:
    """A fact with many matching lines must not starve other matching facts:
    the grep line budget is wider than top_k and dedupe happens before the
    cut (review L2)."""
    await mem.service.add_fact_to_store(
        store_name="global",
        name="multi",
        description="",
        body="\n".join(f"needle line {i}" for i in range(10)),
        actor="user",
    )
    await mem.service.add_fact_to_store(
        store_name="global", name="other", description="", body="a single needle here", actor="user"
    )
    hits, mode, _fb = await mem.service.recall_in_store(
        store_name="global", query="needle", mode="grep", top_k=3
    )
    assert mode == "grep"
    assert len(hits) == 2  # one hit per fact, both facts found


async def test_recall_scope_global_returns_global_only(mem) -> None:
    """scope="global" on a project store must return GLOBAL hits only — it is
    not an alias for "both" (review L3)."""
    from coffer.application.memory.scope import project_store_name

    resolved = await mem.service.resolve_scope(scope=MemoryScope.PROJECT, cwd=mem.project_cwd)
    project_store = project_store_name(resolved.project_id)
    await mem.service.add_fact_to_store(
        store_name=project_store, name="p", description="", body="ocelot project fact", actor="user"
    )
    await mem.service.add_fact_to_store(
        store_name="global", name="g", description="", body="ocelot global fact", actor="user"
    )

    hits, _mode, _fb = await mem.service.recall_in_store(
        store_name=project_store, query="ocelot", scope="global", top_k=10
    )
    texts = [h.text for h in hits]
    assert any("global" in t for t in texts)
    assert not any("project" in t for t in texts)


async def test_new_fact_embeds_via_global_config_without_per_store_fields(mem) -> None:
    """A fact written to a vector-enabled store with NO per-store embedding
    fields must be embedded via the GLOBAL embedding config at write time —
    keyword-only indexing here records the real sha, so the reconcile no-op
    gate would otherwise block the embed forever (review P0-2)."""
    from coffer.domain.resource import ResourceRef

    await mem.service.ensure_store(GLOBAL_STORE_NAME)
    await mem.resources.update_config(
        ResourceRef("memory", GLOBAL_STORE_NAME),
        new_config={
            "retrieval_modes": ["grep", "keyword", "vector"],
            "default_mode": "keyword",
        },
        actor="user",
    )
    await mem.service.add_fact_to_store(
        store_name=GLOBAL_STORE_NAME,
        name="quokka",
        description="",
        body="the quokka habitat fact",
        actor="user",
    )
    vec = (mem.vec_stores or {}).get(("memory", GLOBAL_STORE_NAME))
    assert vec is not None and len(vec._rows) == 1  # vec row written at remember() time
    hits, mode, fallback = await mem.service.recall_in_store(
        store_name=GLOBAL_STORE_NAME, query="quokka habitat", mode="vector", top_k=5
    )
    assert mode == "vector"
    assert fallback is False
    assert any("quokka" in h.text for h in hits)


async def test_store_delete_and_recreate_has_no_stale_vectors(mem) -> None:
    """Deleting a vector-enabled store drops its vec table; a same-name
    re-create starts clean (review gap: end-to-end vec-leak test)."""
    from coffer.domain.resource import ResourceRef

    await mem.service.ensure_store(GLOBAL_STORE_NAME)
    await mem.resources.update_config(
        ResourceRef("memory", GLOBAL_STORE_NAME),
        new_config={
            "retrieval_modes": ["grep", "keyword", "vector"],
            "default_mode": "keyword",
            "embedding_provider": "local",
            "embedding_model": "fake-model",
            "embedding_dimensions": 32,
        },
        actor="user",
    )
    await mem.service.add_fact_to_store(
        store_name=GLOBAL_STORE_NAME,
        name="v",
        description="",
        body="vanishing vector fact",
        actor="user",
    )
    await mem.resources.delete(ResourceRef("memory", GLOBAL_STORE_NAME), actor="user")
    vec = (mem.vec_stores or {}).get(("memory", GLOBAL_STORE_NAME))
    assert vec is not None and vec.dropped

    # Recreate (lazy provision) — vector recall over the fresh store is empty.
    await mem.service.ensure_store(GLOBAL_STORE_NAME)
    hits, _mode, _fb = await mem.service.recall_in_store(
        store_name=GLOBAL_STORE_NAME, query="vanishing", mode="keyword", top_k=5
    )
    assert hits == []
