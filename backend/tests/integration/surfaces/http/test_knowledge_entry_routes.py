"""HTTP-level tests for the scope + entry half of ``/api/v1/knowledge/*``.

The two pre-merge route trees (``/memory_stores/*`` and ``/knowledge_bases/*``)
collapse into one addressed by scope name, so the scope surface — list, create,
read, patch, label, metrics, 404 — is exercised here once rather than twice.
The document half lives in ``test_knowledge_document_routes.py``.

Drives the real wired stack via ``create_app()`` + ``TestClient`` against a
temp HOME (real SQLite + real per-entry files). The entry face has NO LLM /
503 path — writes hand Coffer a clean entry; ``recall`` degrades vector→keyword
(flagged internally) instead of erroring. ``global`` and ``project-<ULID>``
scopes auto-provision; a named collection is created deliberately.

Ties REST scenarios to the 007 acceptance markers.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "knowledge-routes-token"
_HEADERS = {"X-Coffer-Token": _TOKEN}
_USER = {**_HEADERS, "X-Coffer-Actor": "user"}


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _assert_envelope(body: dict, code: str) -> None:
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["details"], dict)


def _scope_dir(tmp_path, name: str):
    """Where a scope's markdown lives under the temp HOME (one root now)."""
    return tmp_path / ".coffer" / "knowledge" / name


# --------------------------------------------------------------------------- #
# scopes
# --------------------------------------------------------------------------- #


def test_global_scope_auto_provisions_and_lists(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59600)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/knowledge", headers=_HEADERS)
        assert r.status_code == 200, r.text
        scopes = r.json()["scopes"]
        glob = next(s for s in scopes if s["name"] == "global")
        assert glob["scope"] == "global"
        assert glob["project_id"] == "00000000000000000000000000"


def test_create_and_list_named_collection(tmp_path, monkeypatch):
    # NB: TEST22-009 — the "agent lists available knowledge bases" acceptance
    # marker lives on the MCP-tool-level test (test_kb_builtin_tools.py), not
    # on this HTTP-route test. Agents see scopes through the coffer__ tool, not
    # via the HTTP API.
    app = _app(tmp_path, monkeypatch, 59410)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge",
            json={"name": "designs", "config": {}},
            headers=_HEADERS,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "designs"
        assert body["scope"] == "named"

        listed = c.get("/api/v1/knowledge", headers=_HEADERS)
        assert listed.status_code == 200
        assert any(s["name"] == "designs" for s in listed.json()["scopes"])


def test_create_rejects_the_auto_provisioned_scope_names(tmp_path, monkeypatch):
    """``POST /knowledge`` creates a NAMED collection only. ``global`` and
    ``project-<ULID>`` provision themselves on first use, so conjuring one by
    hand is a 422 rather than a second, typo-shaped auto-scope."""
    app = _app(tmp_path, monkeypatch, 59415)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        for name in ("global", "project-01J0000000000000000000000A"):
            r = c.post(
                "/api/v1/knowledge",
                json={"name": name, "config": {}},
                headers=_HEADERS,
            )
            assert r.status_code == 422, (name, r.text)
            _assert_envelope(r.json(), "CONFIG_INVALID")


def test_create_duplicate_named_collection_returns_conflict_envelope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59420)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        body = {"name": "dup", "config": {}}
        assert c.post("/api/v1/knowledge", json=body, headers=_HEADERS).status_code == 201
        r = c.post("/api/v1/knowledge", json=body, headers=_HEADERS)
        assert r.status_code == 409
        _assert_envelope(r.json(), "RESOURCE_ALREADY_EXISTS")


def test_list_scopes_reports_indexed_counts_without_disk_walk(tmp_path, monkeypatch):
    """KB14: ``GET /knowledge`` reports each scope's ``entry_count`` /
    ``document_count`` from the cheap indexed counts, NOT from ``metrics()``'
    per-scope ``scan_scope_dir`` + ``du_bytes`` walk. Patching both on the
    queries module (which is what ``metrics()`` goes through) to raise proves
    the list path never runs them.

    Collapsed from the two pre-merge suites: both faces asserted this about
    their own list route, which is now the one route reporting both counts.
    The two counts are asserted on separate scopes because every markdown file
    in a scope — an entry included — is indexed as a document row, so an entry
    in the same scope would also move ``document_count``."""
    from coffer.application.knowledge import queries as knowledge_queries

    app = _app(tmp_path, monkeypatch, 59770)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        added = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "prefers tabs over spaces", "name": "tabs"},
            headers=_USER,
        )
        assert added.status_code == 201, added.text
        c.post("/api/v1/knowledge", json={"name": "docs", "config": {}}, headers=_HEADERS)
        up = c.post(
            "/api/v1/knowledge/docs/documents",
            files={"file": ("a.md", b"# A\n\nalpha content here", "text/markdown")},
            headers=_HEADERS,
        )
        assert up.status_code == 201, up.text

        def _boom_du(_path):
            raise AssertionError("du_bytes must not run on the list path")

        def _boom_scan(_path):
            raise AssertionError("scope_metrics' scan must not run on the list path")

        monkeypatch.setattr(knowledge_queries, "du_bytes", _boom_du)
        monkeypatch.setattr(knowledge_queries, "scan_scope_dir", _boom_scan)

        listed = c.get("/api/v1/knowledge", headers=_HEADERS)
        assert listed.status_code == 200, listed.text
        rows = {s["name"]: s for s in listed.json()["scopes"]}
        assert rows["global"]["entry_count"] == 1
        assert rows["docs"]["document_count"] == 1


def test_scope_metrics_reports_the_union_of_both_halves(tmp_path, monkeypatch):
    """``GET /{scope}/metrics`` returns one number set covering entries AND
    documents — the merge of what the two pre-merge metrics routes reported.

    Collapsed from ``test_per_store_metrics`` (real substrate, entry counts) and
    ``test_metrics_route_returns_kb_metrics`` (wire shape, document counts)."""
    app = _app(tmp_path, monkeypatch, 59660)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post("/api/v1/knowledge", json={"name": "docs", "config": {}}, headers=_HEADERS)
        c.post(
            "/api/v1/knowledge/docs/documents",
            files={"file": ("a.md", b"# A\n\nalpha content here", "text/markdown")},
            headers=_HEADERS,
        )
        r = c.get("/api/v1/knowledge/docs/metrics", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        # One metrics shape for the whole scope, whatever material it holds.
        assert set(body) == {
            "entry_count",
            "document_count",
            "chunk_count",
            "documents_degraded",
            "indexed_modes",
            "disk_bytes",
        }
        assert body["entry_count"] == 0
        assert body["document_count"] == 1
        assert body["chunk_count"] >= 1
        assert body["documents_degraded"] == 0
        assert body["indexed_modes"] == ["grep", "keyword"]
        assert body["disk_bytes"] >= 0

        # And the entry half of the same shape, on a scope holding entries.
        c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "one entry", "name": "f"},
            headers=_USER,
        )
        glob = c.get("/api/v1/knowledge/global/metrics", headers=_HEADERS).json()
        assert glob["entry_count"] == 1
        assert glob["disk_bytes"] >= 0


def test_get_missing_scope_returns_not_found_envelope(tmp_path, monkeypatch):
    """One 404 for the one scope route, whichever shape of name missed.

    Collapsed from the two pre-merge misses (``MEMORY_STORE_NOT_FOUND`` on an
    unknown project store, ``KB_NOT_FOUND`` on an unknown knowledge base)."""
    app = _app(tmp_path, monkeypatch, 59710)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        for name in ("project-DOESNOTEXIST", "nope"):
            r = c.get(f"/api/v1/knowledge/{name}", headers=_HEADERS)
            assert r.status_code == 404, (name, r.text)
            _assert_envelope(r.json(), "MEMORY_STORE_NOT_FOUND")


def test_patch_scope_updates_config(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.get("/api/v1/knowledge/global", headers=_HEADERS)  # provision
        r = c.patch(
            "/api/v1/knowledge/global",
            json={"max_entry_chars": 4096},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        assert r.json()["config"]["max_entry_chars"] == 4096


def test_scope_config_on_the_wire_carries_no_embedding_fields(tmp_path, monkeypatch):
    """Embedding is installation-wide: the merged config drops both faces'
    per-scope ``embedding_*`` fields and renames ``enabled_modes``."""
    app = _app(tmp_path, monkeypatch, 59725)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        config = c.get("/api/v1/knowledge/global", headers=_HEADERS).json()["config"]
        assert not [k for k in config if k.startswith("embedding")]
        assert "enabled_modes" not in config
        assert config["retrieval_modes"] == ["grep", "keyword"]


def test_global_scope_exposes_sentinel_and_no_project_root(tmp_path, monkeypatch):
    # The global scope derives the WORKSPACE_GLOBAL sentinel project_id and has
    # no project_root (finding #10).
    app = _app(tmp_path, monkeypatch, 59730)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.get("/api/v1/knowledge/global", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["project_id"] == "00000000000000000000000000"
        assert body["project_root"] is None


def test_project_scope_get_returns_recorded_project_root(tmp_path, monkeypatch):
    # A project scope echoes the absolute git-root it was provisioned from
    # (finding #10). The cwd→root recording happens in the ScopeResolver; here we
    # provision a project scope by name and seed its recorded root via the same
    # repo the resolver writes to, then assert GET surfaces it.
    import anyio

    from coffer.surfaces.http.knowledge.dependencies import get_project_root_repo

    app = _app(tmp_path, monkeypatch, 59740)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        scope = "project-01ABCDEF01ABCDEF01ABCDEF01"
        # Provision the project scope by writing an entry to it.
        r = c.post(
            f"/api/v1/knowledge/{scope}/entries",
            json={"text": "ships via make release", "name": "deploy"},
            headers=_USER,
        )
        assert r.status_code == 201, r.text
        # Record the project root exactly as the cwd-driven resolver would.
        repo = get_project_root_repo()
        anyio.run(repo.set, scope, "/work/my-repo")

        got = c.get(f"/api/v1/knowledge/{scope}", headers=_HEADERS)
        assert got.status_code == 200, got.text
        body = got.json()
        assert body["scope"] == "project"
        assert body["project_root"] == "/work/my-repo"
        # And the list endpoint carries it too.
        listed = c.get("/api/v1/knowledge", headers=_HEADERS).json()["scopes"]
        proj = next(s for s in listed if s["name"] == scope)
        assert proj["project_root"] == "/work/my-repo"


# --------------------------------------------------------------------------- #
# entries
# --------------------------------------------------------------------------- #


@pytest.mark.acceptance(spec="007-memory", scenario="user adds a fact")
def test_user_adds_an_entry(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59610)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "prefers tabs over spaces", "name": "tabs"},
            headers=_USER,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["actor"] == "user"
        assert body["text"] == "prefers tabs over spaces"
        assert body["scope"] == "global"
        assert body["scope_name"] == "global"
        assert body["path"].endswith(".md")


@pytest.mark.acceptance(spec="007-memory", scenario="user corrects a fact out-of-band")
def test_user_corrects_an_entry_via_write_api(tmp_path, monkeypatch):
    """The programmatic write path (REST PATCH) — the in-app viewer is
    read-only. (The external-edit-on-disk + lazy-reindex half of this scenario
    is covered at the service level in test_memory_service.py.)"""
    app = _app(tmp_path, monkeypatch, 59630)
    scope_dir = _scope_dir(tmp_path, "global")
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        created = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "old text", "name": "f"},
            headers=_USER,
        ).json()
        eid = created["id"]
        # The read-only viewer needs absolute paths for open/reveal:
        # the entry carries its file path + containing folder (the knowledge-lane
        # inbox, where freshly-remembered items live).
        inbox = scope_dir / "knowledge" / "inbox"
        assert created["path"].endswith(".md")
        assert created["folder_path"] == str(inbox)
        r = c.patch(
            f"/api/v1/knowledge/global/entries/{eid}",
            json={"text": "new corrected text"},
            headers=_USER,
        )
        assert r.status_code == 200, r.text
        assert r.json()["text"] == "new corrected text"
        assert r.json()["folder_path"] == str(inbox)
        got = c.get(f"/api/v1/knowledge/global/entries/{eid}", headers=_HEADERS)
        assert got.json()["text"] == "new corrected text"
        # The scope read carries the on-disk scope dir (reveal).
        scope = c.get("/api/v1/knowledge/global", headers=_HEADERS).json()
        assert scope["scope_dir"] == str(scope_dir)


@pytest.mark.acceptance(spec="007-memory", scenario="user deletes a fact")
def test_user_deletes_an_entry(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59640)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        eid = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "to be removed", "name": "x"},
            headers=_USER,
        ).json()["id"]
        r = c.request("DELETE", f"/api/v1/knowledge/global/entries/{eid}", headers=_USER)
        assert r.status_code == 204
        assert r.content == b""
        got = c.get(f"/api/v1/knowledge/global/entries/{eid}", headers=_HEADERS)
        assert got.status_code == 404
        _assert_envelope(got.json(), "MEMORY_NOT_FOUND")


@pytest.mark.acceptance(spec="007-memory", scenario="clear a memory scope")
def test_clear_a_scope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59650)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        for i in range(3):
            c.post(
                "/api/v1/knowledge/global/entries",
                json={"text": f"entry {i}", "name": f"f{i}"},
                headers=_USER,
            )
        r = c.request("DELETE", "/api/v1/knowledge/global/entries", headers=_USER)
        assert r.status_code == 200, r.text
        assert r.json()["cleared"] == 3
        # Scope preserved; entries gone.
        listed = c.get("/api/v1/knowledge/global/entries", headers=_HEADERS)
        assert listed.json()["total"] == 0
        assert c.get("/api/v1/knowledge/global", headers=_HEADERS).status_code == 200


@pytest.mark.acceptance(spec="007-memory", scenario="user renames a memory store")
def test_user_renames_a_scope(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59760)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # A fresh scope carries no display label.
        assert c.get("/api/v1/knowledge/global", headers=_HEADERS).json()["label"] is None
        # Setting a label trims surrounding whitespace and echoes it back.
        r = c.patch(
            "/api/v1/knowledge/global/label",
            json={"label": "  My notes  "},
            headers=_USER,
        )
        assert r.status_code == 200, r.text
        assert r.json()["label"] == "My notes"
        # It survives a re-read and shows up in the list.
        assert c.get("/api/v1/knowledge/global", headers=_HEADERS).json()["label"] == "My notes"
        listed = c.get("/api/v1/knowledge", headers=_HEADERS).json()["scopes"]
        assert any(s["name"] == "global" and s["label"] == "My notes" for s in listed)
        # An empty / whitespace label clears it (reverts to the fallback name).
        r = c.patch("/api/v1/knowledge/global/label", json={"label": "   "}, headers=_USER)
        assert r.status_code == 200, r.text
        assert r.json()["label"] is None
        # Renaming an unknown scope is a 404 envelope, not an autocreate.
        miss = c.patch(
            "/api/v1/knowledge/project-2K8S7KVJ0SJEZX0P0KSXWAN0KZ/label",
            json={"label": "x"},
            headers=_USER,
        )
        assert miss.status_code == 404
        _assert_envelope(miss.json(), "MEMORY_STORE_NOT_FOUND")


def test_empty_entry_text_rejected_by_schema(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59690)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": ""},
            headers=_USER,
        )
        assert r.status_code == 422, r.text


def test_too_long_entry_rejected(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59700)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # PATCH the scope down to a tiny limit, then exceed it (service emits
        # MEMORY_REJECTED → 422). Schema cap (32768) is not reached.
        c.get("/api/v1/knowledge/global", headers=_HEADERS)
        c.patch(
            "/api/v1/knowledge/global",
            json={"max_entry_chars": 64},
            headers=_HEADERS,
        )
        r = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "x" * 200},
            headers=_USER,
        )
        assert r.status_code == 422, r.text
        _assert_envelope(r.json(), "MEMORY_REJECTED")


def test_post_entries_to_unknown_scope_is_404_not_autocreate(tmp_path, monkeypatch):
    """The contract promises 404 for an unknown scope; POSTing to an arbitrary
    name must neither manufacture a Resource nor 500 on the mangled scope
    (review misalignment #5)."""
    app = _app(tmp_path, monkeypatch, 59960)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge/typo/entries",
            json={"text": "should not be stored"},
            headers=_USER,
        )
        assert r.status_code == 404, r.text

        # No orphan scope was created.
        listed = c.get("/api/v1/knowledge", headers=_HEADERS)
        assert "typo" not in {s["name"] for s in listed.json()["scopes"]}

        # A WELL-FORMED project scope name still lazily provisions, with the
        # scope/project_id derived correctly (no mangled prefix stripping).
        good = "project-01HZX5XKQW9YV3T8R2M4N6PABC"
        r2 = c.post(
            f"/api/v1/knowledge/{good}/entries",
            json={"text": "provisions lazily"},
            headers=_USER,
        )
        assert r2.status_code == 201, r2.text
        scope = c.get(f"/api/v1/knowledge/{good}", headers=_HEADERS).json()
        assert scope["scope"] == "project"
        assert scope["project_id"] == "01HZX5XKQW9YV3T8R2M4N6PABC"


def test_body_validation_failure_returns_error_envelope(tmp_path, monkeypatch):
    """Schema-level body failures (e.g. empty text) must return the standard
    ``{error:{code,message,details}}`` envelope, not FastAPI's raw ``detail``
    list (review misalignment: FR-005 error-shape break)."""
    app = _app(tmp_path, monkeypatch, 59970)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": ""},
            headers=_USER,
        )
        assert r.status_code == 422, r.text
        _assert_envelope(r.json(), "CONFIG_INVALID")


def test_entry_list_pagination_boundaries(tmp_path, monkeypatch):
    """offset past the total returns an empty page (total intact); limit/offset
    outside the declared ranges are 422 envelopes."""
    app = _app(tmp_path, monkeypatch, 59980)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        for i in range(3):
            c.post(
                "/api/v1/knowledge/global/entries",
                json={"text": f"boundary entry {i}"},
                headers=_USER,
            )
        past = c.get(
            "/api/v1/knowledge/global/entries",
            params={"limit": 50, "offset": 99},
            headers=_HEADERS,
        ).json()
        assert past["entries"] == []
        assert past["total"] == 3

        for params in [{"limit": 0}, {"limit": 201}, {"offset": -1}]:
            r = c.get("/api/v1/knowledge/global/entries", params=params, headers=_HEADERS)
            assert r.status_code == 422, (params, r.text)
            _assert_envelope(r.json(), "CONFIG_INVALID")


# --------------------------------------------------------------------------- #
# recall
# --------------------------------------------------------------------------- #


def test_recall_returns_hits_only(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59670)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "the api base path is /api/v2", "name": "api"},
            headers=_USER,
        )
        r = c.post(
            "/api/v1/knowledge/global/recall",
            json={"query": "api base path", "top_k": 5},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body["hits"], list)
        # One query → one answer: mode / fallback are no longer surfaced.
        assert "mode" not in body
        assert "fallback" not in body


def test_recall_rejects_mode_in_request_body(tmp_path, monkeypatch):
    """The external recall surface no longer accepts a ``mode`` — but extra keys
    are ignored by Pydantic (not 422); the call still succeeds and resolves the
    scope's default_mode internally."""
    app = _app(tmp_path, monkeypatch, 59680)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "fallback content", "name": "f"},
            headers=_USER,
        )
        r = c.post(
            "/api/v1/knowledge/global/recall",
            json={"query": "fallback", "mode": "vector", "top_k": 3},
            headers=_HEADERS,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "mode" not in body
        assert "fallback" not in body


def test_scope_scoped_recall_honours_scope(tmp_path, monkeypatch):
    # The scope-scoped REST recall reads RecallRequest.scope (finding #5):
    # ``both`` folds in the global scope; ``project`` stays in the named one.
    app = _app(tmp_path, monkeypatch, 59750)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        scope = "project-02ABCDEF02ABCDEF02ABCDEF02"
        c.post(
            f"/api/v1/knowledge/{scope}/entries",
            json={"text": "project deploy note about wombats", "name": "p"},
            headers=_USER,
        )
        c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "global deploy note about wombats", "name": "g"},
            headers=_USER,
        )

        # scope=both → both the project and global entries are recalled.
        both = c.post(
            f"/api/v1/knowledge/{scope}/recall",
            json={"query": "wombats", "scope": "both", "top_k": 10},
            headers=_HEADERS,
        ).json()
        texts_both = " ".join(h["text"] for h in both["hits"])
        assert "project deploy note" in texts_both
        assert "global deploy note" in texts_both

        # scope=project → only the project scope's entry, never the global one.
        proj = c.post(
            f"/api/v1/knowledge/{scope}/recall",
            json={"query": "wombats", "scope": "project", "top_k": 10},
            headers=_HEADERS,
        ).json()
        texts_proj = " ".join(h["text"] for h in proj["hits"])
        assert "project deploy note" in texts_proj
        assert "global deploy note" not in texts_proj


# --------------------------------------------------------------------------- #
# organize
# --------------------------------------------------------------------------- #


def test_organize_returns_no_model_noop_shape(tmp_path, monkeypatch):
    """The wired ``POST …/organize`` returns the OrganizeResult shape. On a fresh
    install no internal model is configured → a clean ``no_model`` no-op (the
    full wiring + route + schema are exercised without calling a real LLM)."""
    app = _app(tmp_path, monkeypatch, 59700)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        # An item to (not) organize — proves the no-op leaves the inbox untouched.
        c.post(
            "/api/v1/knowledge/global/entries",
            json={"text": "an entry awaiting organization"},
            headers=_USER,
        )
        r = c.post("/api/v1/knowledge/global/organize", headers=_HEADERS)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "no_model"
        assert body["items_processed"] == 0
        assert body["topics_created"] == 0
        assert body["topics_updated"] == 0
        assert body["skipped"] == 0
        assert body["model"] is None
        # The inbox item is untouched (still listed).
        entries = c.get("/api/v1/knowledge/global/entries", headers=_HEADERS).json()
        assert entries["total"] == 1


def test_organize_unknown_scope_404(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    with TestClient(app) as c:
        set_active_token(_TOKEN)
        r = c.post("/api/v1/knowledge/not-a-real-scope/organize", headers=_HEADERS)
        assert r.status_code == 404, r.text
