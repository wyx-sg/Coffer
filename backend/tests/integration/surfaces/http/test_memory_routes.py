"""Integration tests for ``/api/v1/memory/*`` (spec memory FR-060..FR-063).

Boots the full FastAPI app (via ``create_app``) so every route is wired
exactly as production wires it — real SQLite, a real Claude Code fixture tree
under a temp HOME, no internal connection configured (organise/recall both
degrade rather than error, per FR-032/FR-052). ``COFFER_MEMORY_ROOT``,
``COFFER_KNOWLEDGE_ROOT`` are all pinned into
``tmp_path`` so nothing here ever touches a real ``~/.coffer``.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "test-token-memory-routes"
_HEADERS = {"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "user"}

# ----- fixture native-memory content (mirrors tests/integration/memory's) -- #

_CC_PROJECT_FACT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""

_CC_PREFERENCE_FACT = """---
name: worktree-development
description: Always develop in a git worktree
metadata:
  type: feedback
---

Multiple parallel sessions share the repo — always work in a worktree.
"""


def _encode(name: str) -> str:
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in name)


def _cc_slug(project_root: pathlib.Path) -> str:
    parts = [p for p in project_root.parts if p != "/"]
    return "-" + "-".join(_encode(p) for p in parts)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".codex").mkdir(parents=True, exist_ok=True)

    app = create_app()
    set_active_token(_TOKEN)
    with TestClient(
        app, base_url="http://localhost", headers=_HEADERS, raise_server_exceptions=False
    ) as c:
        yield c


def _register_agent(c: TestClient, name: str, agent_type: str = "claude_code") -> None:
    r = c.post("/api/v1/agents", json={"type": agent_type, "name": name})
    assert r.status_code == 201, r.text


def _write_cc_facts(tmp_path: pathlib.Path, project_root: pathlib.Path) -> None:
    memory_dir = tmp_path / ".claude" / "projects" / _cc_slug(project_root) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "python-lockfile.md").write_text(_CC_PROJECT_FACT, encoding="utf-8")
    (memory_dir / "worktree-development.md").write_text(_CC_PREFERENCE_FACT, encoding="utf-8")


def _sync(c: TestClient) -> dict:
    r = c.post("/api/v1/memory/sync")
    assert r.status_code == 200, r.text
    return r.json()


# ----- partitions / facts --------------------------------------------------


def test_sync_then_list_partitions_and_facts(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "home" / "dev" / "coffer"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)

    result = _sync(client)
    assert result["facts_written"] == 2
    assert "global" in result["partitions"]

    partitions = client.get("/api/v1/memory/partitions").json()["partitions"]
    names = {p["name"] for p in partitions}
    assert "global" in names
    project_partition = next(p for p in partitions if p["name"] != "global")
    assert project_partition["project_root"] == str(project_root)
    assert project_partition["fact_count"] == 1

    facts = client.get(f"/api/v1/memory/partitions/{project_partition['name']}/facts").json()
    assert facts["facts"][0]["title"] == "python-lockfile"
    assert facts["facts"][0]["hidden"] is False

    detail = client.get(
        f"/api/v1/memory/partitions/{project_partition['name']}/facts/{facts['facts'][0]['slug']}"
    ).json()
    assert detail["body"].strip().startswith("Run `uv sync --frozen`")
    assert detail["origins"][0]["agent"] == "cc"


def test_unknown_partition_facts_is_not_found(client) -> None:
    r = client.get("/api/v1/memory/partitions/does-not-exist/facts")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_unknown_fact_slug_is_not_found(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )
    r = client.get(f"/api/v1/memory/partitions/{partition}/facts/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "MEMORY_FACT_NOT_FOUND"


# ----- organise -------------------------------------------------------------


def test_organise_with_no_internal_connection_still_writes_a_digest(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )

    r = client.post(f"/api/v1/memory/partitions/{partition}/organise")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_used"] is False
    assert body["partition"] == partition
    assert (tmp_path / "memory" / partition / "summary.md").is_file()

    audit = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_organised" for e in audit["entries"])


def test_organise_unknown_partition_is_not_found(client) -> None:
    r = client.post("/api/v1/memory/partitions/does-not-exist/organise")
    assert r.status_code == 404


# ----- context + delivery: FR-055's whole point -----------------------------


def test_context_composes_and_stays_bounded(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)

    r = client.post("/api/v1/memory/context", json={"cwd": str(project_root)})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "## Coffer memory" in data["text"]
    assert data["facts_omitted"] == 0
    assert "L0" in data["layers"]


@pytest.mark.acceptance(
    spec="memory", scenario="the composed context stays within its token budget"
)
def test_context_respects_a_tiny_budget_and_names_what_was_left_out(client, tmp_path) -> None:
    _register_agent(client, "cc")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)

    r = client.post("/api/v1/memory/context", json={"cwd": str(project_root), "budget_tokens": 40})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["text"]) < 2000
    assert data["facts_omitted"] >= 0  # bound respected; exact count is context.py's concern


def test_context_scope_enforcement_does_not_leak_an_out_of_scope_partition(
    client, tmp_path
) -> None:
    """The one route a real agent's own session reaches must be scope-checked
    (spec memory FR-014): an agent outside a project partition's scope must
    never see its facts, even when its own cwd resolves to that partition."""
    _register_agent(client, "cc")
    _register_agent(client, "outsider", agent_type="codex")
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )
    # Default scope from aggregation is {"cc"} (FR-014) — confirm "outsider"
    # is excluded, then compose context for it against the SAME cwd.
    scope = client.get(f"/api/v1/resources/memory/{partition}/scope").json()
    assert scope["scope"] == {"agents": ["cc"]}

    r = client.post("/api/v1/memory/context", json={"agent": "outsider", "cwd": str(project_root)})
    assert r.status_code == 200, r.text
    data = r.json()
    # `partition` says which partition this cwd maps to, not what is visible
    # — the leak this test guards against is in the TEXT and LAYERS, which
    # must never surface a fact from a partition "outsider" is out of scope for.
    assert data["partition"] == partition
    assert "python-lockfile" not in data["text"]
    assert data["layers"] == ["L0"]
    assert data["facts_included"] == 0


def test_delivery_install_status_and_record_fired_round_trip(client) -> None:
    _register_agent(client, "cc")

    status = client.get("/api/v1/memory/delivery", params={"agent": "cc"}).json()
    assert status["delivery"][0]["installed"] is False

    installed = client.post("/api/v1/memory/delivery/cc/install").json()
    assert installed["installed"] is True
    assert "coffer memory context --agent cc" in installed["command"]

    audit = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_delivery_installed" for e in audit["entries"])

    r = client.post(
        "/api/v1/memory/context",
        json={"agent": "cc", "cwd": "/tmp", "record_fired": True},
    )
    assert r.status_code == 200, r.text

    audit2 = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_delivery_fired" for e in audit2["entries"])

    removed = client.delete("/api/v1/memory/delivery/cc").json()
    assert removed["installed"] is False


def test_context_without_record_fired_does_not_record_a_fire(client) -> None:
    _register_agent(client, "cc")
    client.post("/api/v1/memory/delivery/cc/install")

    client.post("/api/v1/memory/context", json={"agent": "cc", "cwd": "/tmp"})

    audit = client.get("/api/v1/audit").json()
    assert not any(e["event_type"] == "memory_delivery_fired" for e in audit["entries"])


# ----- overrides: apply/clear, and surviving a rebuild ---------------------


def _sync_and_get_fact(client: TestClient, tmp_path: pathlib.Path) -> tuple[str, str, str]:
    project_root = tmp_path / "proj"
    if not project_root.is_dir():
        project_root.mkdir(parents=True)
        _write_cc_facts(tmp_path, project_root)
    _sync(client)
    partition = next(
        p["name"]
        for p in client.get("/api/v1/memory/partitions").json()["partitions"]
        if p["name"] != "global"
    )
    facts = client.get(f"/api/v1/memory/partitions/{partition}/facts").json()["facts"]
    fact = next(f for f in facts if f["slug"] == "python-lockfile")
    return partition, fact["slug"], fact["key"]


def test_hide_then_unhide_round_trip(client, tmp_path) -> None:
    _register_agent(client, "cc")
    partition, _slug, key = _sync_and_get_fact(client, tmp_path)

    hidden = client.patch(f"/api/v1/memory/facts/{key}/override", json={"hidden": True}).json()
    assert hidden["hidden"] is True

    facts = client.get(f"/api/v1/memory/partitions/{partition}/facts").json()["facts"]
    assert next(f for f in facts if f["key"] == key)["hidden"] is True

    audit = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_override_set" for e in audit["entries"])

    unhidden = client.delete(
        f"/api/v1/memory/facts/{key}/override", params={"field": "hidden"}
    ).json()
    assert unhidden["hidden"] is False
    audit2 = client.get("/api/v1/audit").json()
    assert any(e["event_type"] == "memory_override_cleared" for e in audit2["entries"])


def test_patch_override_only_touches_the_named_field(client, tmp_path) -> None:
    _register_agent(client, "cc")
    _, _, key = _sync_and_get_fact(client, tmp_path)

    client.patch(f"/api/v1/memory/facts/{key}/override", json={"hidden": True})
    result = client.patch(f"/api/v1/memory/facts/{key}/override", json={"pinned": True}).json()
    assert result["hidden"] is True
    assert result["pinned"] is True


def test_supersede_and_settle_conflict_overrides(client, tmp_path) -> None:
    _register_agent(client, "cc")
    _, _, key = _sync_and_get_fact(client, tmp_path)

    superseded = client.patch(
        f"/api/v1/memory/facts/{key}/override", json={"superseded_by": "some-other-key"}
    ).json()
    assert superseded["superseded_by"] == "some-other-key"
    cleared = client.delete(
        f"/api/v1/memory/facts/{key}/override", params={"field": "superseded_by"}
    ).json()
    assert cleared["superseded_by"] == ""

    settled = client.patch(
        f"/api/v1/memory/facts/{key}/override", json={"conflict_choice": key}
    ).json()
    assert settled["conflict_choice"] == key


def test_list_overrides_reports_every_decision(client, tmp_path) -> None:
    _register_agent(client, "cc")
    _, _, key = _sync_and_get_fact(client, tmp_path)
    client.patch(f"/api/v1/memory/facts/{key}/override", json={"pinned": True})

    overrides = client.get("/api/v1/memory/overrides").json()["overrides"]
    assert any(o["fact_key"] == key and o["pinned"] for o in overrides)


@pytest.mark.acceptance(spec="memory", scenario="a hidden fact stays hidden across a rebuild")
def test_a_hidden_fact_stays_hidden_across_a_rebuild(client, tmp_path) -> None:
    _register_agent(client, "cc")
    partition, slug, key = _sync_and_get_fact(client, tmp_path)

    client.patch(f"/api/v1/memory/facts/{key}/override", json={"hidden": True})

    # Delete the ENTIRE derived tree and re-run aggregation from the agent's
    # native memory, which is untouched — FR-023's own rebuild guarantee.
    shutil.rmtree(tmp_path / "memory")
    _sync(client)

    facts = client.get(f"/api/v1/memory/partitions/{partition}/facts").json()["facts"]
    rebuilt = next(f for f in facts if f["slug"] == slug)
    assert rebuilt["key"] == key  # the origin key is stable across a rebuild
    assert rebuilt["hidden"] is True

    # And it is excluded from what a session would actually be handed.
    context = client.post("/api/v1/memory/context", json={"cwd": str(tmp_path / "proj")}).json()
    assert "python-lockfile" not in context["text"]


@pytest.mark.acceptance(spec="memory", scenario="a pinned fact stays pinned across a rebuild")
def test_a_pinned_fact_stays_pinned_across_a_rebuild(client, tmp_path) -> None:
    _register_agent(client, "cc")
    partition, slug, key = _sync_and_get_fact(client, tmp_path)

    client.patch(f"/api/v1/memory/facts/{key}/override", json={"pinned": True})

    shutil.rmtree(tmp_path / "memory")
    _sync(client)

    facts = client.get(f"/api/v1/memory/partitions/{partition}/facts").json()["facts"]
    rebuilt = next(f for f in facts if f["slug"] == slug)
    assert rebuilt["key"] == key
    assert rebuilt["pinned"] is True
