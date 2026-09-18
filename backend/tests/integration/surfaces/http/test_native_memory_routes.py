"""HTTP coverage for GET /api/v1/agents/{uid}/native-memory and .../files.

Boots the real app, registers an agent whose config_dir is a temp tree carrying
the agent's own native memory, and asserts the read-only listing plus the
read-only browse of one store (its tree and one of its files).

The agent is addressed by the immutable ``uid`` the registration minted (ADR
resource-identity-is-an-immutable-uid), never by its label, so every test takes
the uid off the ``POST /api/v1/agents`` response it already makes. The ``dir``
and ``path`` query parameters are untouched by that: they name a directory and a
file on disk, which the store listing itself handed back — they were never
resource identities.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-native-mem"

#: A well-formed uid that no resource in these tests was ever minted with. It is
#: uid-shaped on purpose: the route must 404 because nothing answers to this
#: identity, not because the string could not be an identity in the first place.
ABSENT_UID = "8c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f"


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _register_claude(c: TestClient, config_dir: pathlib.Path) -> str:
    """Register a claude_code agent labelled ``cc`` and return its uid.

    The uid — not the label — is what the native-memory routes are addressed
    by, so it is what this hands back.
    """
    # Registration requires the config dir to already exist.
    config_dir.mkdir(parents=True, exist_ok=True)
    r = c.post(
        "/api/v1/agents",
        json={"type": "claude_code", "name": "cc", "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


@pytest.mark.acceptance(
    spec="agent-registry/claude-code",
    scenario="the native memory scan lists an agent's own per-project stores",
)
def test_list_native_memory_returns_store(tmp_path, monkeypatch):
    config_dir = tmp_path / "cc-config"
    mem = config_dir / "projects" / "-X" / "memory"
    mem.mkdir(parents=True)
    (mem / "a.md").write_text("x", encoding="utf-8")
    (mem / "MEMORY.md").write_text("index", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59800)
    with _client(app) as c:
        uid = _register_claude(c, config_dir)

        r = c.get(f"/api/v1/agents/{uid}/native-memory")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["project"] == "X"
        assert item["path"] == "/X"
        assert item["memory_dir"] == str(mem)
        # MEMORY.md is excluded from the count.
        assert item["item_count"] == 1
        # The read-only surface carries no import status field.
        assert set(item) == {"project", "path", "memory_dir", "item_count"}


@pytest.mark.acceptance(
    spec="agent-registry/codex",
    scenario="the native memory scan lists Codex's global memory by project",
)
def test_list_native_memory_codex_global_by_project(tmp_path, monkeypatch):
    config_dir = tmp_path / "codex-config"
    memories = config_dir / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(
        "# Task Group: gw one\n\napplies_to: cwd=/p/account-gateway; reuse_rule=x\n\n"
        "## Task 1: a, success\n\n"
        "# Task Group: gw two\n\napplies_to: cwd=/p/account-gateway; reuse_rule=x\n\n"
        "## Task 1: b, success\n\n"
        "# Task Group: bff\n\napplies_to: cwd=/p/account-bff; reuse_rule=x\n\n"
        "## Task 1: c, success\n",
        encoding="utf-8",
    )

    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "cx", "config_dir": str(config_dir)},
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]

        r = c.get(f"/api/v1/agents/{uid}/native-memory")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # One row per distinct routed cwd, count desc; the shared global store.
        assert [(it["project"], it["item_count"]) for it in items] == [
            ("account-gateway", 2),
            ("account-bff", 1),
        ]
        assert all(it["memory_dir"] == str(memories) for it in items)
        assert items[0]["path"] == "/p/account-gateway"


def test_codex_store_tree_holds_only_the_memory_document(tmp_path, monkeypatch):
    """Codex's store is one file, and its directory holds a great deal else.

    ``~/.codex/memories`` is also where Codex keeps its automations, its
    extensions, its skills and a git checkout. Browsing the directory put all
    of that on a page that claims to show memory; the store is the
    ``MEMORY.md`` the layout names, and that is what the tree may list.
    """
    config_dir = tmp_path / "codex-config"
    memories = config_dir / "memories"
    (memories / ".git").mkdir(parents=True)
    (memories / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (memories / "skills").mkdir()
    (memories / "skills" / "unrelated.md").write_text("not memory\n", encoding="utf-8")
    (memories / "xcrun_db").write_text("binary-ish\n", encoding="utf-8")
    (memories / "MEMORY.md").write_text(
        "# Task Group: gw\n\napplies_to: cwd=/p/gw; reuse_rule=x\n\n## Task 1: a, success\n",
        encoding="utf-8",
    )

    app = _app(tmp_path, monkeypatch, 59834)
    with _client(app) as c:
        r = c.post(
            "/api/v1/agents",
            json={"type": "codex", "name": "cx", "config_dir": str(config_dir)},
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]

        r = c.get(f"/api/v1/agents/{uid}/native-memory/files", params={"dir": str(memories)})
        assert r.status_code == 200, r.text

    assert [c["name"] for c in r.json()["root"]["children"]] == ["MEMORY.md"]


def test_list_native_memory_empty_when_no_projects_dir(tmp_path, monkeypatch):
    config_dir = tmp_path / "cc-config"
    app = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        uid = _register_claude(c, config_dir)
        r = c.get(f"/api/v1/agents/{uid}/native-memory")
        assert r.status_code == 200, r.text
        assert r.json()["items"] == []


def test_list_native_memory_unknown_agent_404(tmp_path, monkeypatch):
    """A uid no agent answers to is 404, not an empty list of stores.

    Nothing is registered here, so the service's agent lookup is what answers —
    the distinction the empty-list test above would otherwise blur.
    """
    app = _app(tmp_path, monkeypatch, 59820)
    with _client(app) as c:
        r = c.get(f"/api/v1/agents/{ABSENT_UID}/native-memory")
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_list_native_memory_requires_token(tmp_path, monkeypatch):
    """The token is refused before the uid is looked up, so no agent is
    registered here: 401 must not depend on the uid naming anything."""
    app = _app(tmp_path, monkeypatch, 59840)
    set_active_token(TOKEN)
    with TestClient(app) as c:
        assert c.get(f"/api/v1/agents/{ABSENT_UID}/native-memory").status_code == 401


# ---------------------------------------------------------------------------
# Browsing ONE store — the tree + preview behind a row click
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(spec="agent-registry", scenario="browse one native memory store's files")
def test_store_files_tree_and_content(tmp_path, monkeypatch):
    """A store IS a directory, so its page shows the directory and its bytes."""
    config_dir = tmp_path / "cc-config"
    mem = config_dir / "projects" / "-X" / "memory"
    (mem / "notes").mkdir(parents=True)
    (mem / "MEMORY.md").write_text("# index\n", encoding="utf-8")
    (mem / "notes" / "a.md").write_text("alpha fact", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59850)
    with _client(app) as c:
        uid = _register_claude(c, config_dir)

        # ``dir`` is the memory_dir the listing gave — a path on disk, not an
        # identity, so it is spelled out in full while the agent is a uid.
        r = c.get(f"/api/v1/agents/{uid}/native-memory/files", params={"dir": str(mem)})
        assert r.status_code == 200, r.text
        root = r.json()["root"]
        assert root["path"] == ""
        # Directories first, then files; paths are relative to the store dir.
        assert [(n["name"], n["path"], n["type"]) for n in root["children"]] == [
            ("notes", "notes", "dir"),
            ("MEMORY.md", "MEMORY.md", "file"),
        ]
        assert [n["path"] for n in root["children"][0]["children"]] == ["notes/a.md"]

        r = c.get(
            f"/api/v1/agents/{uid}/native-memory/files/content",
            params={"dir": str(mem), "path": "notes/a.md"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["content"] == "alpha fact"
        assert body["binary"] is False
        assert body["truncated"] is False
        # The absolute path is what the viewer's open / reveal act on (spec agent-registry FR-047).
        assert body["abs_path"] == str(mem / "notes" / "a.md")


@pytest.mark.acceptance(spec="agent-registry", scenario="browse one native memory store's files")
def test_store_files_refuses_a_dir_that_is_not_a_store(tmp_path, monkeypatch):
    """The config dir also holds transcripts and settings; this reads neither."""
    config_dir = tmp_path / "cc-config"
    mem = config_dir / "projects" / "-X" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("i", encoding="utf-8")
    (config_dir / "projects" / "-X").joinpath("secret.jsonl").write_text("{}", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59860)
    with _client(app) as c:
        uid = _register_claude(c, config_dir)

        # The project dir is inside the config dir but is not a memory store.
        r = c.get(
            f"/api/v1/agents/{uid}/native-memory/files",
            params={"dir": str(config_dir / "projects" / "-X")},
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"

        # …and a path escaping the store is the same answer as one that is gone.
        escape = c.get(
            f"/api/v1/agents/{uid}/native-memory/files/content",
            params={"dir": str(mem), "path": "../secret.jsonl"},
        )
        assert escape.status_code == 404


def test_store_files_emit_no_audit_event(tmp_path, monkeypatch):
    """FR-009: workspace listings do not audit, and neither does opening one."""
    config_dir = tmp_path / "cc-config"
    mem = config_dir / "projects" / "-X" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("i", encoding="utf-8")

    app = _app(tmp_path, monkeypatch, 59870)
    with _client(app) as c:
        uid = _register_claude(c, config_dir)
        before = len(c.get("/api/v1/audit").json()["entries"])
        c.get(f"/api/v1/agents/{uid}/native-memory/files", params={"dir": str(mem)})
        c.get(
            f"/api/v1/agents/{uid}/native-memory/files/content",
            params={"dir": str(mem), "path": "MEMORY.md"},
        )
        assert len(c.get("/api/v1/audit").json()["entries"]) == before
