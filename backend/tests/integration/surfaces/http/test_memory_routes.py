"""HTTP-level tests for /api/v1/memory_stores/* (spec 007 redesign).

Drives the real wired stack via ``create_app()`` + ``TestClient`` against a
temp HOME (real SQLite + real per-fact files). The memory face has NO LLM /
503 path — writes hand Coffer a clean fact; ``recall`` degrades vector→keyword
(flagged) instead of erroring. Stores auto-provision per scope.

Ties REST scenarios to the 007 acceptance markers.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "memory-routes-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_USER = {**_HEADERS, "X-Coffer-Actor": "user"}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _assert_envelope(body: dict, code: str) -> None:
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)


def test_global_store_auto_provisions_and_lists(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59600)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/memory_stores", headers=_HEADERS)
        assert r.status_code == 200, r.text
        stores = r.json()["memory_stores"]
        glob = next(s for s in stores if s["name"] == "global")
        assert glob["scope"] == "global"
        assert glob["project_id"] == "00000000000000000000000000"


def test_list_stores_reports_indexed_fact_count_without_disk_scan(tmp_path, monkeypatch):
    """KB14: GET /memory_stores reports per-store fact_count from the cheap indexed
    count, NOT ``metrics()``' per-store ``scan_store_dir`` + ``du_bytes`` walk.
    Patching both on the queries module to raise proves the list path never runs
    them."""
    from coffer.application.memory import queries as mem_queries_mod

    app = _app(tmp_path, monkeypatch, 59770)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        added = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "prefers tabs over spaces", "name": "tabs"},
            headers=_USER,
        )
        assert added.status_code == 201, added.text

        def _boom_du(_path):
            raise AssertionError("du_bytes must not run on the list path")

        def _boom_scan(_path):
            raise AssertionError("scan_store_dir must not run on the list path")

        monkeypatch.setattr(mem_queries_mod, "du_bytes", _boom_du)
        monkeypatch.setattr(mem_queries_mod, "scan_store_dir", _boom_scan)

        listed = c.get("/api/v1/memory_stores", headers=_HEADERS)
        assert listed.status_code == 200, listed.text
        glob = next(s for s in listed.json()["memory_stores"] if s["name"] == "global")
        assert glob["fact_count"] == 1


@pytest.mark.acceptance(spec="007-memory", scenario="user adds a fact")
def test_user_adds_a_fact(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59610)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "prefers tabs over spaces", "name": "tabs"},
            headers=_USER,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["actor"] == "user"
        assert body["text"] == "prefers tabs over spaces"
        assert body["scope"] == "global"
        assert body["path"].endswith(".md")


@pytest.mark.acceptance(spec="007-memory", scenario="user corrects a fact out-of-band")
def test_user_corrects_a_fact_via_write_api(tmp_path, monkeypatch):
    """The programmatic write path (REST PATCH) — the in-app viewer is
    read-only. (The external-edit-on-disk + lazy-reindex half of this scenario
    is covered at the service level in test_memory_service.py.)"""
    app = _app(tmp_path, monkeypatch, 59630)
    store_dir = tmp_path / "memory" / "global"
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        created = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "old text", "name": "f"},
            headers=_USER,
        ).json()
        fid = created["id"]
        # The read-only viewer needs absolute paths for open/reveal:
        # the fact carries its file path + containing folder (the knowledge-lane
        # inbox, where freshly-remembered items live).
        inbox = store_dir / "knowledge" / "inbox"
        assert created["path"].endswith(".md")
        assert created["folder_path"] == str(inbox)
        r = c.patch(
            f"/api/v1/memory_stores/global/facts/{fid}",
            json={"text": "new corrected text"},
            headers=_USER,
        )
        assert r.status_code == 200, r.text
        assert r.json()["text"] == "new corrected text"
        assert r.json()["folder_path"] == str(inbox)
        got = c.get(f"/api/v1/memory_stores/global/facts/{fid}", headers=_HEADERS)
        assert got.json()["text"] == "new corrected text"
        # The store read carries the on-disk store dir (reveal).
        store = c.get("/api/v1/memory_stores/global", headers=_HEADERS).json()
        assert store["store_dir"] == str(store_dir)


@pytest.mark.acceptance(spec="007-memory", scenario="user deletes a fact")
def test_user_deletes_a_fact(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59640)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        fid = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "to be removed", "name": "x"},
            headers=_USER,
        ).json()["id"]
        r = c.request("DELETE", f"/api/v1/memory_stores/global/facts/{fid}", headers=_USER)
        assert r.status_code == 204
        assert r.content == b""
        got = c.get(f"/api/v1/memory_stores/global/facts/{fid}", headers=_HEADERS)
        assert got.status_code == 404
        _assert_envelope(got.json(), "MEMORY_NOT_FOUND")


@pytest.mark.acceptance(spec="007-memory", scenario="clear a memory scope")
def test_clear_a_memory_scope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59650)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        for i in range(3):
            c.post(
                "/api/v1/memory_stores/global/facts",
                json={"text": f"fact {i}", "name": f"f{i}"},
                headers=_USER,
            )
        r = c.request("DELETE", "/api/v1/memory_stores/global/facts", headers=_USER)
        assert r.status_code == 200, r.text
        assert r.json()["cleared"] == 3
        # Store preserved; facts gone.
        listed = c.get("/api/v1/memory_stores/global/facts", headers=_HEADERS)
        assert listed.json()["total"] == 0
        assert c.get("/api/v1/memory_stores/global", headers=_HEADERS).status_code == 200


@pytest.mark.acceptance(spec="007-memory", scenario="user renames a memory store")
def test_user_renames_a_memory_store(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59760)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # A fresh store carries no display label.
        assert c.get("/api/v1/memory_stores/global", headers=_HEADERS).json()["label"] is None
        # Setting a label trims surrounding whitespace and echoes it back.
        r = c.patch(
            "/api/v1/memory_stores/global/label",
            json={"label": "  My notes  "},
            headers=_USER,
        )
        assert r.status_code == 200, r.text
        assert r.json()["label"] == "My notes"
        # It survives a re-read and shows up in the list.
        assert c.get("/api/v1/memory_stores/global", headers=_HEADERS).json()["label"] == "My notes"
        listed = c.get("/api/v1/memory_stores", headers=_HEADERS).json()["memory_stores"]
        assert any(s["name"] == "global" and s["label"] == "My notes" for s in listed)
        # An empty / whitespace label clears it (reverts to the fallback name).
        r = c.patch("/api/v1/memory_stores/global/label", json={"label": "   "}, headers=_USER)
        assert r.status_code == 200, r.text
        assert r.json()["label"] is None
        # Renaming an unknown store is a 404 envelope, not an autocreate.
        miss = c.patch(
            "/api/v1/memory_stores/project-2K8S7KVJ0SJEZX0P0KSXWAN0KZ/label",
            json={"label": "x"},
            headers=_USER,
        )
        assert miss.status_code == 404
        _assert_envelope(miss.json(), "MEMORY_STORE_NOT_FOUND")


def test_per_store_metrics(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59660)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "one fact", "name": "f"},
            headers=_USER,
        )
        r = c.get("/api/v1/memory_stores/global/metrics", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["fact_count"] == 1
        assert body["disk_bytes"] >= 0


def test_recall_returns_hits_with_mode(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59670)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "the api base path is /api/v2", "name": "api"},
            headers=_USER,
        )
        r = c.post(
            "/api/v1/memory_stores/global/recall",
            json={"query": "api base path", "top_k": 5},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] in {"keyword", "grep", "vector"}
        assert isinstance(body["hits"], list)
        assert "fallback" in body


@pytest.mark.acceptance(
    spec="007-memory", scenario="vector recall falls back when embedding is unconfigured"
)
def test_vector_recall_falls_back_when_embedding_unconfigured(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59680)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "fallback content", "name": "f"},
            headers=_USER,
        )
        r = c.post(
            "/api/v1/memory_stores/global/recall",
            json={"query": "fallback", "mode": "vector", "top_k": 3},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # No embedding configured → degrade to keyword, flagged, never an error.
        assert body["fallback"] is True
        assert body["mode"] == "keyword"


def test_store_scoped_recall_honours_scope(tmp_path, monkeypatch):
    # The store-scoped REST recall reads RecallRequest.scope (finding #5):
    # ``both`` folds in the global store; ``project`` stays in the named store.
    app = _app(tmp_path, monkeypatch, 59750)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        store = "project-02ABCDEF02ABCDEF02ABCDEF02"
        c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "project deploy note about wombats", "name": "p"},
            headers=_USER,
        )
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "global deploy note about wombats", "name": "g"},
            headers=_USER,
        )

        # scope=both → both the project and global facts are recalled.
        both = c.post(
            f"/api/v1/memory_stores/{store}/recall",
            json={"query": "wombats", "scope": "both", "top_k": 10},
            headers=_HEADERS,
        ).json()
        texts_both = " ".join(h["text"] for h in both["hits"])
        assert "project deploy note" in texts_both
        assert "global deploy note" in texts_both

        # scope=project → only the named store's fact, never the global one.
        proj = c.post(
            f"/api/v1/memory_stores/{store}/recall",
            json={"query": "wombats", "scope": "project", "top_k": 10},
            headers=_HEADERS,
        ).json()
        texts_proj = " ".join(h["text"] for h in proj["hits"])
        assert "project deploy note" in texts_proj
        assert "global deploy note" not in texts_proj


def test_empty_fact_text_rejected_by_schema(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59690)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": ""},
            headers=_USER,
        )
        assert r.status_code == 422, r.text


def test_too_long_fact_rejected(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59700)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # PATCH the store down to a tiny limit, then exceed it (service emits
        # MEMORY_REJECTED → 422). Schema cap (32768) is not reached.
        c.get("/api/v1/memory_stores/global", headers=_HEADERS)
        c.patch(
            "/api/v1/memory_stores/global",
            json={"max_fact_chars": 64},
            headers=_HEADERS,
        )
        r = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "x" * 200},
            headers=_USER,
        )
        assert r.status_code == 422, r.text
        _assert_envelope(r.json(), "MEMORY_REJECTED")


def test_get_missing_store_returns_not_found_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/memory_stores/project-DOESNOTEXIST", headers=_HEADERS)
        assert r.status_code == 404
        _assert_envelope(r.json(), "MEMORY_STORE_NOT_FOUND")


def test_patch_store_updates_config(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.get("/api/v1/memory_stores/global", headers=_HEADERS)  # provision
        r = c.patch(
            "/api/v1/memory_stores/global",
            json={"max_fact_chars": 4096},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        assert r.json()["config"]["max_fact_chars"] == 4096


def test_global_store_exposes_sentinel_and_no_project_root(tmp_path, monkeypatch):
    # The global store derives the WORKSPACE_GLOBAL sentinel project_id and has
    # no project_root (finding #10).
    app = _app(tmp_path, monkeypatch, 59730)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/memory_stores/global", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["project_id"] == "00000000000000000000000000"
        assert body["project_root"] is None


def test_project_store_get_returns_recorded_project_root(tmp_path, monkeypatch):
    # A project store echoes the absolute git-root it was provisioned from
    # (finding #10). The cwd→root recording happens in the ScopeResolver; here we
    # provision a project store by name and seed its recorded root via the same
    # repo the resolver writes to, then assert GET surfaces it.
    import anyio

    from coffer.surfaces.http.memory.dependencies import get_project_root_repo

    app = _app(tmp_path, monkeypatch, 59740)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        store = "project-01ABCDEF01ABCDEF01ABCDEF01"
        # Provision the project store by writing a fact to it.
        r = c.post(
            f"/api/v1/memory_stores/{store}/facts",
            json={"text": "ships via make release", "name": "deploy"},
            headers=_USER,
        )
        assert r.status_code == 201, r.text
        # Record the project root exactly as the cwd-driven resolver would.
        repo = get_project_root_repo()
        anyio.run(repo.set, store, "/work/my-repo")

        got = c.get(f"/api/v1/memory_stores/{store}", headers=_HEADERS)
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["scope"] == "project"
        assert body["project_root"] == "/work/my-repo"
        # And the list endpoint carries it too.
        listed = c.get("/api/v1/memory_stores", headers=_HEADERS).json()["memory_stores"]
        proj = next(s for s in listed if s["name"] == store)
        assert proj["project_root"] == "/work/my-repo"


def test_post_facts_to_unknown_store_is_404_not_autocreate(tmp_path, monkeypatch):
    """The contract promises 404 for an unknown store; POSTing to an arbitrary
    name must neither manufacture a Resource nor 500 on the mangled scope
    (review misalignment #5)."""
    app = _app(tmp_path, monkeypatch, 59960)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/typo/facts",
            json={"text": "should not be stored"},
            headers=_USER,
        )
        assert r.status_code == 404, r.text
        _assert_envelope(r.json(), "MEMORY_STORE_NOT_FOUND")

        # No orphan store was created.
        listed = c.get("/api/v1/memory_stores", headers=_HEADERS)
        assert "typo" not in {s["name"] for s in listed.json()["memory_stores"]}

        # A WELL-FORMED project store name still lazily provisions, with the
        # scope/project_id derived correctly (no mangled prefix stripping).
        good = "project-01HZX5XKQW9YV3T8R2M4N6PABC"
        r2 = c.post(
            f"/api/v1/memory_stores/{good}/facts",
            json={"text": "provisions lazily"},
            headers=_USER,
        )
        assert r2.status_code == 201, r2.text
        store = c.get(f"/api/v1/memory_stores/{good}", headers=_HEADERS).json()
        assert store["scope"] == "project"
        assert store["project_id"] == "01HZX5XKQW9YV3T8R2M4N6PABC"


def test_body_validation_failure_returns_error_envelope(tmp_path, monkeypatch):
    """Schema-level body failures (e.g. empty text) must return the standard
    ``{error:{code,message,details}}`` envelope, not FastAPI's raw ``detail``
    list (review misalignment: FR-005 error-shape break)."""
    app = _app(tmp_path, monkeypatch, 59970)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": ""},
            headers=_USER,
        )
        assert r.status_code == 422, r.text
        _assert_envelope(r.json(), "CONFIG_INVALID")


def test_fact_list_pagination_boundaries(tmp_path, monkeypatch):
    """offset past the total returns an empty page (total intact); limit/offset
    outside the declared ranges are 422 envelopes."""
    app = _app(tmp_path, monkeypatch, 59980)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        for i in range(3):
            c.post(
                "/api/v1/memory_stores/global/facts",
                json={"text": f"boundary fact {i}"},
                headers=_USER,
            )
        past = c.get(
            "/api/v1/memory_stores/global/facts",
            params={"limit": 50, "offset": 99},
            headers=_HEADERS,
        ).json()
        assert past["facts"] == []
        assert past["total"] == 3

        for params in [{"limit": 0}, {"limit": 201}, {"offset": -1}]:
            r = c.get("/api/v1/memory_stores/global/facts", params=params, headers=_HEADERS)
            assert r.status_code == 422, (params, r.text)
            _assert_envelope(r.json(), "CONFIG_INVALID")


def test_organize_returns_no_model_noop_shape(tmp_path, monkeypatch):
    """The wired ``POST …/organize`` returns the OrganizeResult shape. On a fresh
    install no internal model is configured → a clean ``no_model`` no-op (the
    full wiring + route + schema are exercised without calling a real LLM)."""
    app = _app(tmp_path, monkeypatch, 59700)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # An item to (not) organize — proves the no-op leaves the inbox untouched.
        c.post(
            "/api/v1/memory_stores/global/facts",
            json={"text": "a fact awaiting organization"},
            headers=_USER,
        )
        r = c.post("/api/v1/memory_stores/global/organize", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "no_model"
        assert body["items_processed"] == 0
        assert body["topics_created"] == 0
        assert body["topics_updated"] == 0
        assert body["skipped"] == 0
        assert body["model"] is None
        # The inbox item is untouched (still listed).
        facts = c.get("/api/v1/memory_stores/global/facts", headers=_HEADERS).json()
        assert facts["total"] == 1


def test_organize_unknown_store_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post("/api/v1/memory_stores/not-a-real-store/organize", headers=_HEADERS)
        assert r.status_code == 404, r.text
        _assert_envelope(r.json(), "MEMORY_STORE_NOT_FOUND")
